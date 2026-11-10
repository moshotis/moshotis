from mt5_exness_bot.indicators import atr, ema, entry_signal


def test_ema_seeds_with_a_simple_average():
    values = ema([1, 2, 3, 4, 5, 6], 3)
    assert values[:2] == [None, None]
    assert values[2:] == [2, 3, 4, 5]


def test_wilder_atr_aligns_to_the_bar_that_completed_the_window():
    values = atr(
        [10, 12, 11, 13],
        [8, 9, 7, 10],
        [9, 11, 8, 12],
        2,
    )
    assert values[0] is None
    assert values[1] is None
    assert values[2] == 3.5
    assert values[3] == 4.25


def test_entry_signal_detects_a_cross_and_then_stays_quiet():
    closes = [100 - index * 0.3 for index in range(50)]
    crossed = None
    for _ in range(80):
        closes.append(closes[-1] + 0.8)
        signal = entry_signal(closes, 9, 21)
        if signal == "buy":
            crossed = list(closes)
            break
    assert crossed is not None
    assert entry_signal(crossed[:-1], 9, 21) != "buy"
    assert entry_signal(crossed + [crossed[-1] + 0.01], 9, 21) != "buy"
