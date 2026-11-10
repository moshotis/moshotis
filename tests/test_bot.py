from datetime import datetime, timezone

import pytest

from mt5_exness_bot.bot import Bot
from mt5_exness_bot.config import Config
from mt5_exness_bot.indicators import entry_signal
from mt5_exness_bot.models import Account, Bar, OrderResult, Position, Quote, SymbolSpec
from mt5_exness_bot.state import BotState

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


def config() -> Config:
    return Config(
        live_trading=False,
        symbols=("EURUSD",),
        timeframe="M15",
        ema_fast=9,
        ema_slow=21,
        atr_period=14,
        atr_sl_multiplier=1.5,
        reward_risk=2.0,
        risk_percent=0.5,
        max_daily_loss_percent=2.0,
        max_spread_points=30,
        magic=260110,
        deviation_points=20,
        poll_seconds=5,
        bars_to_load=300,
    )


def buy_cross_closes() -> list[float]:
    closes = [100 - index * 0.3 for index in range(50)]
    for _ in range(80):
        closes.append(closes[-1] + 0.8)
        if entry_signal(closes, 9, 21) == "buy":
            return closes
    raise AssertionError("expected a buy cross")


def bars_from(closes: list[float], start: int = 1_700_000_000) -> list[Bar]:
    bars: list[Bar] = []
    previous = closes[0]
    for index, close in enumerate(closes):
        bars.append(
            Bar(
                time=start + index * 900,
                open=previous,
                high=max(previous, close) + 0.001,
                low=min(previous, close) - 0.001,
                close=close,
            )
        )
        previous = close
    return bars


class FakeBroker:
    def __init__(self, bars: list[Bar], account: Account | None = None):
        self.bars = bars
        self.account = account or Account(
            login=123,
            server="Exness-MT5Trial7",
            name="Demo",
            company="Exness",
            currency="USD",
            balance=10_000,
            equity=10_000,
            leverage=200,
            trade_mode="demo",
            trade_allowed=True,
        )
        self.enabled = True
        self.open_positions: list[Position] = []
        self.orders: list[dict] = []
        self.closed: list[int] = []
        self.loss = 100.0
        self.shutdowns = 0

    def connect(self) -> Account:
        return self.account

    def shutdown(self) -> None:
        self.shutdowns += 1

    def trading_enabled(self) -> bool:
        return self.enabled

    def resolve_symbol(self, logical: str) -> str:
        return "EURUSDm"

    def symbol_spec(self, symbol: str) -> SymbolSpec:
        return SPEC

    def quote(self, symbol: str) -> Quote:
        price = self.bars[-1].close
        return Quote(price, price + 0.0001, 10, self.bars[-1].time)

    def closed_bars(self, symbol: str, timeframe: str, count: int) -> list[Bar]:
        return self.bars

    def positions(self, symbol: str, magic: int) -> list[Position]:
        return list(self.open_positions)

    def loss_per_lot(self, symbol: str, side: str, entry: float, stop: float) -> float:
        return self.loss

    def market_order(self, symbol, side, volume, stop, take_profit, magic, deviation, comment) -> OrderResult:
        self.orders.append({"side": side, "volume": volume, "magic": magic, "comment": comment})
        return OrderResult(True, 10009, "done", 55)

    def close_position(self, position: Position, deviation: int) -> OrderResult:
        self.closed.append(position.ticket)
        return OrderResult(True, 10009, "done", position.ticket)

    def server_now(self, symbol: str) -> datetime:
        return datetime(2026, 11, 10, tzinfo=timezone.utc)


def test_startup_arms_and_the_next_cross_sends_one_sized_order(tmp_path):
    closes = buy_cross_closes()
    broker = FakeBroker(bars_from(closes[:-1]))
    bot = Bot(config(), broker, BotState(tmp_path / "state.json"))
    assert bot.handle_symbol("EURUSD", 10_000, 10_000) == "armed"
    assert broker.orders == []

    broker.bars = bars_from(closes)
    assert bot.handle_symbol("EURUSD", 10_000, 10_000) == "buy"
    assert broker.orders == [
        {"side": "buy", "volume": 0.5, "magic": 260110, "comment": "ema-cross"}
    ]
    assert bot.handle_symbol("EURUSD", 10_000, 10_000) == "idle"
    assert len(broker.orders) == 1


def test_opposite_position_is_closed_before_the_new_order(tmp_path):
    closes = buy_cross_closes()
    broker = FakeBroker(bars_from(closes[:-1]))
    bot = Bot(config(), broker, BotState(tmp_path / "state.json"))
    bot.handle_symbol("EURUSD", 10_000, 10_000)
    broker.bars = bars_from(closes)
    broker.open_positions = [
        Position(ticket=7, symbol="EURUSDm", side="sell", volume=0.1, magic=260110, time=1)
    ]
    assert bot.handle_symbol("EURUSD", 10_000, 10_000) == "buy"
    assert broker.closed == [7]
    assert broker.orders[0]["side"] == "buy"


def test_daily_loss_limit_does_not_open_a_trade(tmp_path):
    closes = buy_cross_closes()
    broker = FakeBroker(bars_from(closes[:-1]))
    bot = Bot(config(), broker, BotState(tmp_path / "state.json"))
    bot.handle_symbol("EURUSD", 10_000, 10_000)
    broker.bars = bars_from(closes)
    assert bot.handle_symbol("EURUSD", 9_800, 10_000) == "skip"
    assert broker.orders == []


def test_real_account_is_refused_when_live_trading_is_off(tmp_path):
    account = Account(
        login=999,
        server="Exness-MT5Real5",
        name="Live",
        company="Exness",
        currency="USD",
        balance=10_000,
        equity=10_000,
        leverage=200,
        trade_mode="real",
        trade_allowed=True,
    )
    broker = FakeBroker(bars_from(buy_cross_closes()), account)
    bot = Bot(config(), broker, BotState(tmp_path / "state.json"))
    with pytest.raises(SystemExit, match="real"):
        bot.ensure_account()
    assert broker.shutdowns == 1
