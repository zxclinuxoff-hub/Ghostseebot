"""Правила еженедельного отчёта (без зависимостей)."""
from __future__ import annotations


def week_key(d) -> str:
    """Ключ недели по ISO, например 2026-W43."""
    return d.strftime("%G-W%V")


def should_send(now_local, last_key: str | None) -> bool:
    """Понедельник, не раньше 10:00 по местному времени, и отчёт за эту неделю ещё не отправляли."""
    return now_local.weekday() == 0 and now_local.hour >= 10 and week_key(now_local) != last_key
