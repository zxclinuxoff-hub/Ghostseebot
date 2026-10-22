"""Правила «владелец в сети» (без зависимостей)."""
from __future__ import annotations

ACTIVE_WINDOW = 300.0  # сек: если владелец писал или нажимал что-то за последние 5 минут — он в сети


def is_recent(last_ts: float | None, now: float, window: float = ACTIVE_WINDOW) -> bool:
    return last_ts is not None and now - last_ts < window
