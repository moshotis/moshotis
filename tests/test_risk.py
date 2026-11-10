from mt5_exness_bot.models import SymbolSpec
from mt5_exness_bot.risk import orders_allowed, risk_budget, volume_for_risk

SPEC = SymbolSpec(
    point=0.00001,
    digits=5,
    volume_min=0.01,
    volume_max=100,
    volume_step=0.01,
    stops_level_points=0,
    freeze_level_points=0,
    trade_mode="full",
)


def test_demo_can_trade_and_a_real_account_cannot_until_enabled():
    assert orders_allowed("demo", False) is True
    assert orders_allowed("real", False) is False
    assert orders_allowed("real", True) is True
    assert orders_allowed("contest", True) is False


def test_daily_loss_caps_the_next_trade_and_then_blocks_it():
    assert risk_budget(10_000, 9_900, 0.5, 2) == 49.5
    assert risk_budget(10_000, 9_810, 1, 2) == 10
    assert risk_budget(10_000, 9_800, 0.5, 2) is None


def test_volume_rounds_down_and_skips_when_the_minimum_lot_risks_too_much():
    assert volume_for_risk(50, 100, SPEC) == 0.5
    assert volume_for_risk(1, 150, SPEC) is None
    assert volume_for_risk(10_000_000, 1, SPEC) == 100
