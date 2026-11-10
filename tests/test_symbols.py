from mt5_exness_bot.symbols import symbol_candidates


def test_exness_suffixes_are_tried_for_a_logical_forex_name():
    names = symbol_candidates("eurusd")
    assert names[0] == "EURUSD"
    assert "EURUSDm" in names
    assert "EURUSDc" in names


def test_an_already_suffixed_name_stays_first():
    assert symbol_candidates("EURUSDm")[0] == "EURUSDm"
