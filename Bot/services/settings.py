"""Глобальные настройки бота — быстрый доступ с кэшем."""
from __future__ import annotations

import time

from ..db import db

_cache: dict[str, tuple[float, object]] = {}
_TTL = 10.0


async def get(key: str, default=None):
    c = _cache.get(key)
    if c and time.time() - c[0] < _TTL:
        return c[1]
    rows = await db.select("gs_settings", {"key": f"eq.{key}"})
    value = rows[0]["value"] if rows else default
    _cache[key] = (time.time(), value)
    return value


async def set(key: str, value, updated_by: int | None = None):
    await db.insert("gs_settings", {
        "key": key, "value": value, "updated_by": updated_by,
    }, upsert="key", returning=False)
    _cache[key] = (time.time(), value)
    return value


async def forum_logging_enabled() -> bool:
    return bool(await get("forum_logging", True))
