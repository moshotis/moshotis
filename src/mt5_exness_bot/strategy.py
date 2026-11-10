from __future__ import annotations

from mt5_exness_bot.indicators import atr, entry_signal
from mt5_exness_bot.models import Bar, Plan, SymbolSpec
from mt5_exness_bot.risk import risk_budget


def _round_price(price: float, digits: int) -> float:
    return round(price, digits)


def _min_distance(spec: SymbolSpec) -> float:
    points = max(spec.stops_level_points, spec.freeze_level_points, 0)
    return points * spec.point


def build_plan(
    bars: list[Bar],
    *,
    bid: float,
    ask: float,
    spread_points: int,
    open_side: str | None,
    equity: float,
    day_start_equity: float,
    spec: SymbolSpec,
    ema_fast: int,
    ema_slow: int,
    atr_period: int,
    atr_sl_multiplier: float,
    reward_risk: float,
    risk_percent: float,
    max_daily_loss_percent: float,
    max_spread_points: int,
) -> Plan:
    """Decide what to do with the latest closed bar. Does not size the order."""
    needed = max(ema_slow, atr_period) + 2
    if len(bars) < needed:
        return Plan("skip", "not enough closed bars")
    bar_time = bars[-1].time
    budget = risk_budget(day_start_equity, equity, risk_percent, max_daily_loss_percent)
    if budget is None:
        return Plan("skip", "daily loss limit reached", bar_time=bar_time)
    if spread_points > max_spread_points:
        return Plan("skip", f"spread {spread_points} exceeds {max_spread_points}", bar_time=bar_time)
    if spec.trade_mode == "disabled":
        return Plan("skip", "symbol trading is disabled", bar_time=bar_time)
    if spec.trade_mode == "close":
        return Plan("skip", "symbol is close-only", bar_time=bar_time)

    signal = entry_signal([bar.close for bar in bars], ema_fast, ema_slow)
    if signal is None:
        return Plan("hold", "no EMA cross on this bar", bar_time=bar_time)
    if signal == "buy" and spec.trade_mode == "short":
        return Plan("skip", "symbol is short-only", bar_time=bar_time)
    if signal == "sell" and spec.trade_mode == "long":
        return Plan("skip", "symbol is long-only", bar_time=bar_time)
    if open_side == signal:
        return Plan("hold", f"already {signal}", bar_time=bar_time)

    ranges = atr(
        [bar.high for bar in bars],
        [bar.low for bar in bars],
        [bar.close for bar in bars],
        atr_period,
    )
    latest_atr = ranges[-1]
    if latest_atr is None or latest_atr <= 0:
        return Plan("skip", "ATR is not ready", bar_time=bar_time)

    distance = max(latest_atr * atr_sl_multiplier, _min_distance(spec))
    if signal == "buy":
        entry = ask
        stop = _round_price(entry - distance, spec.digits)
        take_profit = _round_price(entry + distance * reward_risk, spec.digits)
        if stop >= bid or take_profit <= ask:
            return Plan("skip", "buy stops do not clear the spread", bar_time=bar_time)
    else:
        entry = bid
        stop = _round_price(entry + distance, spec.digits)
        take_profit = _round_price(entry - distance * reward_risk, spec.digits)
        if stop <= ask or take_profit >= bid:
            return Plan("skip", "sell stops do not clear the spread", bar_time=bar_time)

    return Plan(signal, "EMA cross", entry, stop, take_profit, bar_time)
