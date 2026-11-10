from datetime import date

from mt5_exness_bot.state import BotState


def test_day_start_equity_resets_on_a_new_server_day(tmp_path):
    state = BotState(tmp_path / "state.json")
    assert state.day_start_equity(100, date(2026, 11, 10), 10_000) == 10_000
    assert state.day_start_equity(100, date(2026, 11, 10), 9_500) == 10_000
    assert state.day_start_equity(100, date(2026, 11, 11), 9_700) == 9_700

    reloaded = BotState(tmp_path / "state.json")
    assert reloaded.day_start_equity(100, date(2026, 11, 11), 1) == 9_700


def test_last_bar_survives_a_restart(tmp_path):
    state = BotState(tmp_path / "state.json")
    state.set_last_bar("EURUSDm", 1700000000)
    assert BotState(tmp_path / "state.json").last_bar("EURUSDm") == 1700000000
