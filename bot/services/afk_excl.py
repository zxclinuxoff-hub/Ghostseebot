"""Исключения для .afk: собеседники, которым бот НЕ отправляет AFK-ответ. Хранятся по владельцу в Supabase."""
from __future__ import annotations

import time

from ..db import DBError, db
from .logs import audit

TABLE = "gs_afk_exclusions"
_TTL = 20.0  # сек: короткий кэш, чтобы не дёргать базу на каждый AFK-ответ
_cache: dict[tuple[int, int], tuple[float, bool]] = {}


def _forget(owner_id: int, partner_id: int) -> None:
    _cache.pop((owner_id, partner_id), None)


async def is_excluded(owner_id: int, partner_id: int) -> bool:
    """Кэш на 20 сек. При ошибке базы возвращаем True (ошибки не кэшируем): лучше промолчать, чем ответить исключённому."""
    key = (owner_id, partner_id)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    try:
        rows = await db.select(TABLE, {"owner_id": f"eq.{owner_id}", "excluded_id": f"eq.{partner_id}"})
    except DBError as e:
        await audit("error", "afk_excl_check_failed", owner_id, err=str(e)[:200])
        return True
    value = bool(rows)
    if len(_cache) > 5000:  # защита памяти
        _cache.clear()
    _cache[key] = (time.time(), value)
    return value


async def add(owner_id: int, partner_id: int, name: str | None) -> bool:
    """True — добавлено; False — такое исключение уже есть (защита от дублей на уровне базы)."""
    rows = await db.insert(TABLE, {"owner_id": owner_id, "excluded_id": partner_id, "excluded_name": name},
                           upsert="owner_id,excluded_id", ignore=True, returning=True)
    _forget(owner_id, partner_id)
    return bool(rows)


async def remove(owner_id: int, partner_id: int) -> bool:
    existed = bool(await db.select(TABLE, {"owner_id": f"eq.{owner_id}", "excluded_id": f"eq.{partner_id}"}))
    if existed:
        await db.delete(TABLE, {"owner_id": f"eq.{owner_id}", "excluded_id": f"eq.{partner_id}"})
    _forget(owner_id, partner_id)
    return existed


async def count(owner_id: int) -> int:
    return await db.count(TABLE, {"owner_id": f"eq.{owner_id}"})


async def page(owner_id: int, offset: int, limit: int) -> list[dict]:
    return await db.select(TABLE, {
        "owner_id": f"eq.{owner_id}",
        "order": "created_at.desc,excluded_id.desc",
        "limit": str(limit), "offset": str(offset),
    })
