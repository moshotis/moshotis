from __future__ import annotations

import math

from mt5_exness_bot.models import SymbolSpec


def orders_allowed(trade_mode: str, live_trading: bool) -> bool:
    """Demo accounts can trade. Real accounts trade only when explicitly enabled."""
    if trade_mode == "demo":
        return True
    return trade_mode == "real" and live_trading


def risk_budget(
    start_equity: float,
    equity: float,
    risk_percent: float,
    max_daily_loss_percent: float,
) -> float | None:
    """Money that may be lost on the next stop, capped by today's remaining loss budget.

    Returns ``None`` when the daily loss limit is already reached.
    """
    if start_equity <= 0 or equity <= 0:
        return None
    lost = start_equity - equity
    allowed = start_equity * max_daily_loss_percent / 100
    remaining = allowed - lost
    if remaining <= 0:
        return None
    planned = equity * risk_percent / 100
    if planned <= 0:
        return None
    return min(planned, remaining)


def volume_for_risk(risk_money: float, loss_per_lot: float, spec: SymbolSpec) -> float | None:
    """Largest volume step that keeps a full stop inside ``risk_money``.

    Returns ``None`` instead of rounding up to the minimum lot. Rounding up
    would risk more than the configured percent.
    """
    if risk_money <= 0 or loss_per_lot <= 0 or spec.volume_step <= 0:
        return None
    raw = risk_money / loss_per_lot
    steps = math.floor(raw / spec.volume_step + 1e-8)
    volume = round(steps * spec.volume_step, 8)
    if volume + 1e-8 < spec.volume_min:
        return None
    if volume > spec.volume_max:
        steps = math.floor(spec.volume_max / spec.volume_step + 1e-8)
        volume = round(steps * spec.volume_step, 8)
    return volume
