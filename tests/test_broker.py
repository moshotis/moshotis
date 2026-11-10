from mt5_exness_bot.broker import _filling_modes


class _Modes:
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2


def test_ioc_symbols_try_ioc_before_return():
    assert _filling_modes(_Modes(), 2) == [1, 2]


def test_fok_and_ioc_keep_both_before_the_return_fallback():
    assert _filling_modes(_Modes(), 3) == [0, 1, 2]
