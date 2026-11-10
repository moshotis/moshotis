from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Bar:
    time: int
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class SymbolSpec:
    point: float
    digits: int
    volume_min: float
    volume_max: float
    volume_step: float
    stops_level_points: int
    freeze_level_points: int
    trade_mode: str


@dataclass(frozen=True)
class Quote:
    bid: float
    ask: float
    spread_points: int
    time: int


@dataclass(frozen=True)
class Account:
    login: int
    server: str
    name: str
    company: str
    currency: str
    balance: float
    equity: float
    leverage: int
    trade_mode: str
    trade_allowed: bool


@dataclass(frozen=True)
class Position:
    ticket: int
    symbol: str
    side: str
    volume: float
    magic: int
    time: int


@dataclass(frozen=True)
class OrderResult:
    ok: bool
    retcode: int
    comment: str
    ticket: int | None
    retryable: bool = False


@dataclass(frozen=True)
class Plan:
    action: str
    reason: str
    entry: float | None = None
    stop: float | None = None
    take_profit: float | None = None
    bar_time: int | None = None
