from __future__ import annotations


def ema(values: list[float], period: int) -> list[float | None]:
    """Exponential moving average aligned to ``values``.

    The seed is a simple average of the first ``period`` prices. Earlier slots
    are ``None`` because they do not have a full window yet.
    """
    if period < 1:
        raise ValueError("EMA period must be at least 1")
    if len(values) < period:
        return [None] * len(values)
    multiplier = 2 / (period + 1)
    seed = sum(values[:period]) / period
    out: list[float | None] = [None] * (period - 1)
    out.append(seed)
    previous = seed
    for price in values[period:]:
        previous = (price - previous) * multiplier + previous
        out.append(previous)
    return out


def atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int,
) -> list[float | None]:
    """Wilder average true range, aligned to the input bars."""
    count = len(closes)
    if not (len(highs) == count == len(lows)):
        raise ValueError("high, low, and close series must be the same length")
    if period < 1 or count < period + 1:
        return [None] * count
    true_ranges: list[float] = []
    for index in range(1, count):
        true_range = max(
            highs[index] - lows[index],
            abs(highs[index] - closes[index - 1]),
            abs(lows[index] - closes[index - 1]),
        )
        true_ranges.append(true_range)
    out: list[float | None] = [None] * count
    previous = sum(true_ranges[:period]) / period
    bar_index = period
    out[bar_index] = previous
    for true_range in true_ranges[period:]:
        previous = (previous * (period - 1) + true_range) / period
        bar_index += 1
        out[bar_index] = previous
    return out


def entry_signal(closes: list[float], fast: int, slow: int) -> str | None:
    """Return ``buy`` or ``sell`` when the fast EMA crosses the slow EMA."""
    if fast >= slow:
        raise ValueError("fast EMA period must be shorter than the slow period")
    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)
    if len(closes) < 2:
        return None
    previous_fast, current_fast = fast_ema[-2], fast_ema[-1]
    previous_slow, current_slow = slow_ema[-2], slow_ema[-1]
    if None in (previous_fast, current_fast, previous_slow, current_slow):
        return None
    if previous_fast <= previous_slow and current_fast > current_slow:
        return "buy"
    if previous_fast >= previous_slow and current_fast < current_slow:
        return "sell"
    return None
