from __future__ import annotations

from datetime import datetime, timezone

from mt5_exness_bot.config import Credentials
from mt5_exness_bot.models import Account, Bar, OrderResult, Position, Quote, SymbolSpec
from mt5_exness_bot.symbols import symbol_candidates

_TRADE_MODES = {
    0: "demo",
    1: "contest",
    2: "real",
}

_SYMBOL_TRADE_MODES = {
    0: "disabled",
    1: "long",
    2: "short",
    3: "close",
    4: "full",
}

_RETRYABLE = {10004, 10018, 10020, 10021}

_HINTS = {
    10016: "Stop loss or take profit is too close. Widen atr_sl_multiplier.",
    10017: "Trading is disabled for this account or symbol.",
    10018: "The market is closed.",
    10019: "Not enough free margin for this volume.",
    10027: "Algo Trading is off. Click the Algo Trading button in MT5.",
    10030: "This symbol rejected the filling mode.",
}


def _package():
    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        raise RuntimeError(
            "MetaTrader5 is not installed. From the project folder run: pip install -e ."
        ) from exc
    return mt5


class MT5Broker:
    """Thin wrapper around the official MetaTrader5 Python package."""

    def __init__(self, credentials: Credentials) -> None:
        self.credentials = credentials
        self._mt5 = None

    def connect(self) -> Account:
        mt5 = _package()
        self._mt5 = mt5
        kwargs = {}
        if self.credentials.path:
            kwargs["path"] = self.credentials.path
        if not mt5.initialize(**kwargs):
            code, message = mt5.last_error()
            raise ConnectionError(
                f"Could not attach to MT5 ({code}: {message}). "
                "Open the Exness MetaTrader 5 terminal and log in, or set MT5_PATH."
            )
        if self.credentials.login is not None:
            logged_in = mt5.login(
                self.credentials.login,
                password=self.credentials.password,
                server=self.credentials.server,
            )
            if not logged_in:
                code, message = mt5.last_error()
                raise ConnectionError(f"MT5 login failed ({code}: {message}). Check login, password, and server.")
        info = mt5.account_info()
        if info is None:
            raise ConnectionError(
                "MT5 is open but no account is logged in. Log in to the Exness demo, "
                "or set MT5_LOGIN, MT5_PASSWORD, and MT5_SERVER in .env."
            )
        terminal = mt5.terminal_info()
        if terminal is None or not terminal.connected:
            raise ConnectionError("MT5 terminal is not connected to the broker.")
        return _account_from(info)

    def account(self) -> Account:
        mt5 = self._mt5 or _package()
        info = mt5.account_info()
        if info is None:
            raise ConnectionError("MT5 account is no longer logged in.")
        return _account_from(info)

    def shutdown(self) -> None:
        if self._mt5 is not None:
            self._mt5.shutdown()

    def trading_enabled(self) -> bool:
        mt5 = self._mt5 or _package()
        terminal = mt5.terminal_info()
        return bool(terminal and terminal.trade_allowed and terminal.connected)

    def resolve_symbol(self, logical: str) -> str | None:
        mt5 = self._mt5 or _package()
        for candidate in symbol_candidates(logical):
            info = mt5.symbol_info(candidate)
            if info is None:
                continue
            if not info.visible and not mt5.symbol_select(candidate, True):
                continue
            return candidate
        return None

    def symbol_spec(self, symbol: str) -> SymbolSpec:
        mt5 = self._mt5 or _package()
        info = mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"Symbol {symbol} disappeared from MT5")
        return SymbolSpec(
            point=float(info.point),
            digits=int(info.digits),
            volume_min=float(info.volume_min),
            volume_max=float(info.volume_max),
            volume_step=float(info.volume_step),
            stops_level_points=int(info.trade_stops_level),
            freeze_level_points=int(info.trade_freeze_level),
            trade_mode=_SYMBOL_TRADE_MODES.get(int(info.trade_mode), "disabled"),
        )

    def quote(self, symbol: str) -> Quote | None:
        mt5 = self._mt5 or _package()
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if tick is None or info is None or tick.bid <= 0 or tick.ask <= 0:
            return None
        return Quote(
            bid=float(tick.bid),
            ask=float(tick.ask),
            spread_points=int(info.spread),
            time=int(tick.time),
        )

    def closed_bars(self, symbol: str, timeframe: str, count: int) -> list[Bar]:
        mt5 = self._mt5 or _package()
        rates = mt5.copy_rates_from_pos(symbol, getattr(mt5, f"TIMEFRAME_{timeframe}"), 0, count)
        if rates is None or len(rates) < 3:
            return []
        closed = rates[:-1]
        return [
            Bar(
                time=int(bar["time"]),
                open=float(bar["open"]),
                high=float(bar["high"]),
                low=float(bar["low"]),
                close=float(bar["close"]),
            )
            for bar in closed
        ]

    def positions(self, symbol: str, magic: int) -> list[Position]:
        mt5 = self._mt5 or _package()
        rows = mt5.positions_get(symbol=symbol) or []
        found: list[Position] = []
        for row in rows:
            if int(row.magic) != magic:
                continue
            side = "buy" if int(row.type) == mt5.POSITION_TYPE_BUY else "sell"
            found.append(
                Position(
                    ticket=int(row.ticket),
                    symbol=str(row.symbol),
                    side=side,
                    volume=float(row.volume),
                    magic=int(row.magic),
                    time=int(row.time),
                )
            )
        return found

    def loss_per_lot(self, symbol: str, side: str, entry: float, stop: float) -> float | None:
        mt5 = self._mt5 or _package()
        order_type = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL
        profit = mt5.order_calc_profit(order_type, symbol, 1.0, entry, stop)
        if profit is None:
            return None
        loss = abs(float(profit))
        if loss <= 0:
            return None
        return loss

    def server_now(self, symbol: str) -> datetime:
        quote = self.quote(symbol)
        if quote is None:
            raise ConnectionError(f"No tick for {symbol}, so the broker clock is unavailable")
        # MT5 encodes server time as a Unix timestamp. Reading it as UTC yields the server clock.
        return datetime.fromtimestamp(quote.time, tz=timezone.utc)

    def market_order(
        self,
        symbol: str,
        side: str,
        volume: float,
        stop: float,
        take_profit: float,
        magic: int,
        deviation: int,
        comment: str,
    ) -> OrderResult:
        mt5 = self._mt5 or _package()
        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if info is None or tick is None:
            return OrderResult(False, -1, "missing symbol quote", None, retryable=True)
        order_type = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL
        price = float(tick.ask if side == "buy" else tick.bid)
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": stop,
            "tp": take_profit,
            "deviation": deviation,
            "magic": magic,
            "comment": comment[:31],
            "type_time": mt5.ORDER_TIME_GTC,
        }
        return self._send(request, _filling_modes(mt5, int(info.filling_mode)))

    def close_position(self, position: Position, deviation: int) -> OrderResult:
        mt5 = self._mt5 or _package()
        info = mt5.symbol_info(position.symbol)
        tick = mt5.symbol_info_tick(position.symbol)
        if info is None or tick is None:
            return OrderResult(False, -1, "missing symbol quote", None, retryable=True)
        closing_buy = position.side == "sell"
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": mt5.ORDER_TYPE_BUY if closing_buy else mt5.ORDER_TYPE_SELL,
            "position": position.ticket,
            "price": float(tick.ask if closing_buy else tick.bid),
            "deviation": deviation,
            "magic": position.magic,
            "comment": "ema-cross-close",
            "type_time": mt5.ORDER_TIME_GTC,
        }
        return self._send(request, _filling_modes(mt5, int(info.filling_mode)))

    def _send(self, request: dict, filling_modes: list[int]) -> OrderResult:
        mt5 = self._mt5 or _package()
        last = OrderResult(False, -1, "order was not sent", None)
        for mode in filling_modes:
            attempt = dict(request)
            attempt["type_filling"] = mode
            result = mt5.order_send(attempt)
            if result is None:
                code, message = mt5.last_error()
                last = OrderResult(False, int(code), str(message), None, retryable=True)
                continue
            comment = str(result.comment)
            hint = _HINTS.get(int(result.retcode))
            if hint:
                comment = f"{comment}. {hint}"
            ticket = int(result.order or result.deal or 0) or None
            last = OrderResult(
                ok=int(result.retcode) in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_DONE_PARTIAL),
                retcode=int(result.retcode),
                comment=comment,
                ticket=ticket,
                retryable=int(result.retcode) in _RETRYABLE,
            )
            if last.ok or int(result.retcode) != 10030:
                return last
        return last


def _filling_modes(mt5, mask: int) -> list[int]:
    modes: list[int] = []
    if mask & 1:
        modes.append(mt5.ORDER_FILLING_FOK)
    if mask & 2:
        modes.append(mt5.ORDER_FILLING_IOC)
    if mt5.ORDER_FILLING_RETURN not in modes:
        modes.append(mt5.ORDER_FILLING_RETURN)
    return modes


def _account_from(info) -> Account:
    return Account(
        login=int(info.login),
        server=str(info.server),
        name=str(info.name),
        company=str(info.company),
        currency=str(info.currency),
        balance=float(info.balance),
        equity=float(info.equity),
        leverage=int(info.leverage),
        trade_mode=_TRADE_MODES.get(int(info.trade_mode), "unknown"),
        trade_allowed=bool(info.trade_allowed),
    )
