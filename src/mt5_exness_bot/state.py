from __future__ import annotations

import json
from datetime import date
from pathlib import Path


class BotState:
    """Persists the daily equity anchor and the last bar already handled."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict = {"last_bar": {}}
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                loaded.setdefault("last_bar", {})
                self._data = loaded

    def day_start_equity(self, login: int, today: date, equity: float) -> float:
        same_day = (
            self._data.get("login") == login and self._data.get("date") == today.isoformat()
        )
        if same_day:
            return float(self._data["start_equity"])
        self._data["login"] = login
        self._data["date"] = today.isoformat()
        self._data["start_equity"] = equity
        self._save()
        return equity

    def last_bar(self, symbol: str) -> int | None:
        value = self._data.get("last_bar", {}).get(symbol)
        return None if value is None else int(value)

    def set_last_bar(self, symbol: str, bar_time: int) -> None:
        self._data.setdefault("last_bar", {})[symbol] = bar_time
        self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        temporary.replace(self.path)
