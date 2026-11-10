from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

_TIMEFRAMES = {"M1", "M5", "M15", "M30", "H1", "H4", "D1"}


@dataclass(frozen=True)
class Config:
    live_trading: bool
    symbols: tuple[str, ...]
    timeframe: str
    ema_fast: int
    ema_slow: int
    atr_period: int
    atr_sl_multiplier: float
    reward_risk: float
    risk_percent: float
    max_daily_loss_percent: float
    max_spread_points: int
    magic: int
    deviation_points: int
    poll_seconds: int
    bars_to_load: int


@dataclass(frozen=True)
class Credentials:
    login: int | None
    password: str | None
    server: str | None
    path: str | None


def _require(raw: dict, key: str, kind: type):
    if key not in raw:
        raise ValueError(f"config.yaml is missing {key}")
    value = raw[key]
    if kind is float and isinstance(value, int) and not isinstance(value, bool):
        value = float(value)
    if kind is int and isinstance(value, bool):
        raise ValueError(f"{key} must be a number")
    if not isinstance(value, kind):
        raise ValueError(f"{key} must be {kind.__name__}")
    return value


def load_config(path: Path) -> Config:
    if not path.exists():
        raise ValueError(f"Config file not found: {path}")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError("config.yaml must be a mapping")
    symbols = loaded.get("symbols")
    if not isinstance(symbols, list) or not symbols or not all(isinstance(item, str) for item in symbols):
        raise ValueError("symbols must be a non-empty list of names, for example [EURUSD]")
    timeframe = str(_require(loaded, "timeframe", str)).upper()
    if timeframe not in _TIMEFRAMES:
        allowed = ", ".join(sorted(_TIMEFRAMES))
        raise ValueError(f"timeframe must be one of {allowed}")
    ema_fast = _require(loaded, "ema_fast", int)
    ema_slow = _require(loaded, "ema_slow", int)
    if ema_fast < 2 or ema_slow <= ema_fast:
        raise ValueError("ema_fast must be at least 2 and shorter than ema_slow")
    risk_percent = _require(loaded, "risk_percent", float)
    max_daily = _require(loaded, "max_daily_loss_percent", float)
    if not 0 < risk_percent <= 5:
        raise ValueError("risk_percent must be greater than 0 and at most 5")
    if not 0 < max_daily <= 20:
        raise ValueError("max_daily_loss_percent must be greater than 0 and at most 20")
    multiplier = _require(loaded, "atr_sl_multiplier", float)
    reward = _require(loaded, "reward_risk", float)
    if multiplier <= 0 or reward <= 0:
        raise ValueError("atr_sl_multiplier and reward_risk must be greater than 0")
    atr_period = _require(loaded, "atr_period", int)
    if atr_period < 2:
        raise ValueError("atr_period must be at least 2")
    poll_seconds = _require(loaded, "poll_seconds", int)
    bars = _require(loaded, "bars_to_load", int)
    if poll_seconds < 1:
        raise ValueError("poll_seconds must be at least 1")
    if bars < ema_slow + atr_period + 5:
        raise ValueError("bars_to_load is too small for the EMA and ATR periods")
    return Config(
        live_trading=bool(_require(loaded, "live_trading", bool)),
        symbols=tuple(item.strip() for item in symbols),
        timeframe=timeframe,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        atr_period=atr_period,
        atr_sl_multiplier=multiplier,
        reward_risk=reward,
        risk_percent=risk_percent,
        max_daily_loss_percent=max_daily,
        max_spread_points=_require(loaded, "max_spread_points", int),
        magic=_require(loaded, "magic", int),
        deviation_points=_require(loaded, "deviation_points", int),
        poll_seconds=poll_seconds,
        bars_to_load=bars,
    )


def load_credentials() -> Credentials:
    load_dotenv()
    login_text = os.environ.get("MT5_LOGIN", "").strip()
    password = os.environ.get("MT5_PASSWORD", "").strip() or None
    server = os.environ.get("MT5_SERVER", "").strip() or None
    path = os.environ.get("MT5_PATH", "").strip() or None
    login = int(login_text) if login_text else None
    if login is not None and (not password or not server):
        raise ValueError("MT5_LOGIN is set, so MT5_PASSWORD and MT5_SERVER are required")
    if login is None and (password or server):
        raise ValueError("Set MT5_LOGIN, MT5_PASSWORD, and MT5_SERVER together, or leave all three blank")
    return Credentials(login=login, password=password, server=server, path=path)
