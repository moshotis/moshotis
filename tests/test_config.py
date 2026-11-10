from pathlib import Path

import pytest

from mt5_exness_bot.config import load_config


def _write(path, text):
    path.write_text(text, encoding="utf-8")


def test_config_rejects_a_risk_percent_above_five(tmp_path):
    path = tmp_path / "config.yaml"
    _write(
        path,
        """
live_trading: false
symbols: [EURUSD]
timeframe: M15
ema_fast: 9
ema_slow: 21
atr_period: 14
atr_sl_multiplier: 1.5
reward_risk: 2
risk_percent: 10
max_daily_loss_percent: 2
max_spread_points: 30
magic: 1
deviation_points: 20
poll_seconds: 5
bars_to_load: 300
""",
    )
    with pytest.raises(ValueError, match="risk_percent"):
        load_config(path)


def test_project_config_loads():
    config = load_config(Path("config.yaml"))
    assert config.timeframe == "M15"
    assert config.live_trading is False
    assert config.symbols == ("EURUSD",)
