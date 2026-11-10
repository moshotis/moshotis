from __future__ import annotations

import logging
import time

from mt5_exness_bot.config import Config
from mt5_exness_bot.models import Account, OrderResult, Plan
from mt5_exness_bot.risk import orders_allowed, risk_budget, volume_for_risk
from mt5_exness_bot.state import BotState
from mt5_exness_bot.strategy import build_plan

logger = logging.getLogger(__name__)


class Bot:
    def __init__(self, config: Config, broker, state: BotState) -> None:
        self.config = config
        self.broker = broker
        self.state = state
        self._last_notice = 0.0

    def ensure_account(self) -> Account:
        account = self.broker.connect()
        if not account.trade_allowed:
            self.broker.shutdown()
            raise SystemExit(
                "This login cannot send trades. Use the Exness trading password, not the investor password."
            )
        if not self.broker.trading_enabled():
            self.broker.shutdown()
            raise SystemExit(
                "Algo Trading is off in MT5, or the terminal is disconnected. "
                "Turn on the Algo Trading button and confirm the connection icon is green."
            )
        if not orders_allowed(account.trade_mode, self.config.live_trading):
            self.broker.shutdown()
            raise SystemExit(
                f"Connected to a {account.trade_mode} account ({account.login} on {account.server}). "
                "Orders stay off. This build sends orders on demo accounts. "
                "A real account also needs live_trading: true in config.yaml."
            )
        if "exness" not in account.server.lower() and "exness" not in account.company.lower():
            logger.warning(
                "Server %s / company %s does not look like Exness. Symbol names may not match.",
                account.server,
                account.company,
            )
        mode = "REAL ACCOUNT — live_trading is on" if account.trade_mode == "real" else "demo account"
        logger.info(
            "Connected to %s %s on %s. Balance %.2f %s, equity %.2f, leverage 1:%s. %s.",
            mode,
            account.login,
            account.server,
            account.balance,
            account.currency,
            account.equity,
            account.leverage,
            account.company,
        )
        return account

    def run(self) -> None:
        account = self.ensure_account()
        logger.info(
            "Watching %s on %s. The bar already closed at startup is skipped. "
            "Next new bar can send a demo order.",
            ", ".join(self.config.symbols),
            self.config.timeframe,
        )
        try:
            while True:
                if not self.broker.trading_enabled():
                    self._notice("Algo Trading is off or MT5 is disconnected. Waiting.")
                else:
                    account = self.broker.account()
                    now = self.broker.server_now(self._clock_symbol(account))
                    day_start = self.state.day_start_equity(account.login, now.date(), account.equity)
                    for logical in self.config.symbols:
                        try:
                            self.handle_symbol(logical, account.equity, day_start)
                        except Exception:
                            logger.exception("Failed while handling %s", logical)
                time.sleep(self.config.poll_seconds)
        finally:
            self.broker.shutdown()

    def describe(self) -> list[str]:
        """Read-only plan for the latest closed bar. Does not send orders or arm the bot."""
        account = self.broker.connect()
        try:
            now = self.broker.server_now(self._clock_symbol(account))
            day_start = self.state.day_start_equity(account.login, now.date(), account.equity)
            lines = [
                f"{account.trade_mode} {account.login} on {account.server} "
                f"equity {account.equity:.2f} {account.currency}"
            ]
            if not account.trade_allowed:
                lines.append("This login cannot send trades.")
            elif not orders_allowed(account.trade_mode, self.config.live_trading):
                lines.append("Orders are blocked on this account.")
            for logical in self.config.symbols:
                lines.append(self._describe_symbol(logical, account.equity, day_start))
            return lines
        finally:
            self.broker.shutdown()

    def handle_symbol(self, logical: str, equity: float, day_start_equity: float) -> str:
        symbol = self.broker.resolve_symbol(logical)
        if symbol is None:
            self._notice(f"No MT5 symbol found for {logical}. Add it in Market Watch or edit config.yaml.")
            return "unresolved"
        previous = self.state.last_bar(symbol)
        bars = self.broker.closed_bars(symbol, self.config.timeframe, self.config.bars_to_load)
        if len(bars) < self.config.ema_slow + 2:
            return "wait"
        current = bars[-1].time
        if previous is None:
            self.state.set_last_bar(symbol, current)
            logger.info("Armed %s. Waiting for the next %s close before trading.", symbol, self.config.timeframe)
            return "armed"
        if previous == current:
            return "idle"
        quote = self.broker.quote(symbol)
        if quote is None:
            return "wait"
        positions = self.broker.positions(symbol, self.config.magic)
        sides = {position.side for position in positions}
        open_side = next(iter(sides)) if len(sides) == 1 else None
        plan = self._plan(bars, quote, open_side, equity, day_start_equity, symbol)
        if plan.action in ("hold", "skip"):
            self.state.set_last_bar(symbol, current)
            logger.info("%s %s: %s", symbol, plan.action, plan.reason)
            return plan.action
        if any(position.side == plan.action for position in positions):
            self._flatten(positions, plan.action)
            self.state.set_last_bar(symbol, current)
            logger.info("%s hold: already %s", symbol, plan.action)
            return "hold"
        close_result = self._flatten(positions, plan.action)
        if close_result is not None and not close_result.ok:
            if not close_result.retryable:
                self.state.set_last_bar(symbol, current)
            return "close_failed"
        result = self._enter(symbol, plan, equity, day_start_equity)
        if result.ok or not result.retryable:
            self.state.set_last_bar(symbol, current)
        if result.ok:
            logger.info(
                "%s %s %.2f at %.5f sl %.5f tp %.5f ticket %s",
                symbol,
                plan.action,
                self._last_volume,
                plan.entry,
                plan.stop,
                plan.take_profit,
                result.ticket,
            )
            return plan.action
        self._notice(f"{symbol} order failed ({result.retcode}): {result.comment}")
        return "order_failed"

    def _describe_symbol(self, logical: str, equity: float, day_start_equity: float) -> str:
        symbol = self.broker.resolve_symbol(logical)
        if symbol is None:
            return f"{logical}: symbol not found on this Exness account"
        bars = self.broker.closed_bars(symbol, self.config.timeframe, self.config.bars_to_load)
        quote = self.broker.quote(symbol)
        if quote is None or not bars:
            return f"{symbol}: no quote or bars yet"
        positions = self.broker.positions(symbol, self.config.magic)
        open_side = positions[0].side if positions else None
        plan = self._plan(bars, quote, open_side, equity, day_start_equity, symbol)
        if plan.action not in ("buy", "sell") or plan.entry is None or plan.stop is None:
            return f"{symbol}: {plan.action} — {plan.reason}"
        loss = self.broker.loss_per_lot(symbol, plan.action, plan.entry, plan.stop)
        spec = self.broker.symbol_spec(symbol)
        budget = risk_budget(
            day_start_equity,
            equity,
            self.config.risk_percent,
            self.config.max_daily_loss_percent,
        )
        volume = None if loss is None or budget is None else volume_for_risk(budget, loss, spec)
        volume_text = "below minimum lot" if volume is None else f"volume {volume}"
        return (
            f"{symbol}: would {plan.action} {volume_text} "
            f"entry {plan.entry} sl {plan.stop} tp {plan.take_profit}"
        )

    def _plan(self, bars, quote, open_side, equity, day_start_equity, symbol: str) -> Plan:
        return build_plan(
            bars,
            bid=quote.bid,
            ask=quote.ask,
            spread_points=quote.spread_points,
            open_side=open_side,
            equity=equity,
            day_start_equity=day_start_equity,
            spec=self.broker.symbol_spec(symbol),
            ema_fast=self.config.ema_fast,
            ema_slow=self.config.ema_slow,
            atr_period=self.config.atr_period,
            atr_sl_multiplier=self.config.atr_sl_multiplier,
            reward_risk=self.config.reward_risk,
            risk_percent=self.config.risk_percent,
            max_daily_loss_percent=self.config.max_daily_loss_percent,
            max_spread_points=self.config.max_spread_points,
        )

    def _flatten(self, positions, new_side: str) -> OrderResult | None:
        """Close positions that face the new signal. None means every close succeeded."""
        for position in positions:
            if position.side == new_side:
                continue
            result = self.broker.close_position(position, self.config.deviation_points)
            if not result.ok:
                self._notice(
                    f"Could not close {position.symbol} {position.side} #{position.ticket} "
                    f"({result.retcode}): {result.comment}"
                )
                return result
            logger.info("Closed %s %s ticket %s", position.symbol, position.side, position.ticket)
        return None

    def _enter(self, symbol: str, plan: Plan, equity: float, day_start_equity: float) -> OrderResult:
        self._last_volume = 0.0
        assert plan.entry is not None and plan.stop is not None and plan.take_profit is not None
        loss = self.broker.loss_per_lot(symbol, plan.action, plan.entry, plan.stop)
        spec = self.broker.symbol_spec(symbol)
        budget = risk_budget(
            day_start_equity,
            equity,
            self.config.risk_percent,
            self.config.max_daily_loss_percent,
        )
        if loss is None or budget is None:
            return OrderResult(False, -1, "could not size the position", None)
        volume = volume_for_risk(budget, loss, spec)
        if volume is None:
            return OrderResult(
                False,
                -1,
                "risk budget does not cover the minimum lot",
                None,
            )
        self._last_volume = volume
        return self.broker.market_order(
            symbol,
            plan.action,
            volume,
            plan.stop,
            plan.take_profit,
            self.config.magic,
            self.config.deviation_points,
            "ema-cross",
        )

    def _clock_symbol(self, account: Account) -> str:
        for logical in self.config.symbols:
            resolved = self.broker.resolve_symbol(logical)
            if resolved:
                return resolved
        raise ConnectionError(
            f"None of {list(self.config.symbols)} exist on account {account.login}. "
            "Open Market Watch in the Exness terminal and copy the symbol name into config.yaml."
        )

    def _notice(self, message: str) -> None:
        now = time.monotonic()
        if now - self._last_notice >= 60:
            logger.warning(message)
            self._last_notice = now

