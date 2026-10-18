from __future__ import annotations

import datetime as dt
import re
import time

from ..config import cfg
from ..db import DBError, db

UTC = dt.timezone.utc
MSK = dt.timezone(dt.timedelta(hours=3))
_cache: dict[int, tuple[float, dict | None]] = {}


def now() -> dt.datetime:
    return dt.datetime.now(UTC)


def iso(d: dt.datetime) -> str:
    return d.astimezone(UTC).isoformat()


def parse(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def fmt_dt(s) -> str:
    d = parse(s) if isinstance(s, str) else s
    return d.astimezone(MSK).strftime("%d.%m.%Y %H:%M") if d else "—"


async def get_user(uid: int, fresh: bool = False):
    c = _cache.get(uid)
    if c and not fresh and time.time() - c[0] < 20:
        return c[1]
    rows = await db.select("gs_users", {"tg_id": f"eq.{uid}"})
    u = rows[0] if rows else None
    _cache[uid] = (time.time(), u)
    return u


async def patch_user(uid: int, **data):
    rows = await db.update("gs_users", {"tg_id": f"eq.{uid}"}, data)
    _cache.pop(uid, None)
    return rows[0] if rows else None


async def ensure_user(tg_user) -> tuple[dict, bool]:
    """Возвращает (user, is_new). Новому пользователю сразу даётся пробный период."""
    u = await get_user(tg_user.id)
    if u:
        if u.get("username") != tg_user.username or u.get("first_name") != (tg_user.first_name or ""):
            u = await patch_user(tg_user.id, first_name=tg_user.first_name or "", username=tg_user.username) or u
        return u, False
    try:
        rows = await db.insert("gs_users", {
            "tg_id": tg_user.id, "first_name": tg_user.first_name or "", "username": tg_user.username,
            "sub_until": iso(now() + dt.timedelta(days=cfg.trial_days)),
        })
        u, new = rows[0], True
    except DBError:
        u, new = await get_user(tg_user.id, fresh=True), False
    _cache[tg_user.id] = (time.time(), u)
    return u, new


def is_active(u) -> bool:
    if not u or u.get("banned"):
        return False
    s = parse(u.get("sub_until"))
    return bool(s and s > now())


def days_left(u) -> int:
    s = parse(u.get("sub_until")) if u else None
    return max(0, (s - now()).days + (1 if s and s > now() else 0)) if s else 0


def is_frozen(u) -> bool:
    s = (u or {}).get("settings") or {}
    fu = parse(s.get("freeze_until")) if isinstance(s.get("freeze_until"), str) else None
    return bool(fu and now() < fu)


async def start_freeze(uid: int, days: int):
    """Заморозка: бот выключен на days дней. Дни подписки НЕ добавляются — только ставятся на паузу."""
    until = now() + dt.timedelta(days=days)
    await set_settings(uid, freeze_start=iso(now()), freeze_until=iso(until))
    return until


async def end_freeze(uid: int):
    """Снять заморозку. Подписка продлевается ровно на время заморозки (пауза, а не подарок)."""
    u = await get_user(uid, fresh=True)
    if not u:
        return None
    s = u.get("settings") or {}
    fu = parse(s.get("freeze_until")) if isinstance(s.get("freeze_until"), str) else None
    fs = parse(s.get("freeze_start")) if isinstance(s.get("freeze_start"), str) else None
    if not fu:
        return u
    base = parse(u.get("sub_until"))
    new_sub = u.get("sub_until")
    if fs and base and base > fs:  # подписка была активна на момент заморозки — сдвигаем на время паузы
        paused = min(now(), fu) - fs
        new_sub = iso(base + paused)
    return await patch_user(uid, sub_until=new_sub,
                            settings={**s, "freeze_until": None, "freeze_start": None})


def setting(u, key, default=True):
    return (u.get("settings") or {}).get(key, default) if u else default


async def set_settings(uid: int, **kw):
    u = await get_user(uid, fresh=True)
    return await patch_user(uid, settings={**(u.get("settings") or {}), **kw})


async def grant(uid: int, days: int):
    u = await get_user(uid, fresh=True)
    if not u:
        raise ValueError("пользователь не найден")
    base = max(now(), parse(u.get("sub_until")) or now())
    return await patch_user(uid, sub_until=iso(base + dt.timedelta(days=days)), warned_exp=False, warned_3d=False)


async def take(uid: int, days: int | None = None):
    u = await get_user(uid, fresh=True)
    if not u:
        raise ValueError("пользователь не найден")
    if days is None:
        new = now()
    else:
        new = max(now(), (parse(u.get("sub_until")) or now()) - dt.timedelta(days=days))
    return await patch_user(uid, sub_until=iso(new))


async def resolve_target(arg: str):
    """ID или @username → запись пользователя (или None)."""
    arg = (arg or "").strip().lstrip("@")
    if not arg:
        return None
    if arg.isdigit():
        return await get_user(int(arg), fresh=True)
    rows = await db.select("gs_users", {"username": f"ilike.{re.sub(r'[%*,()]', '', arg)}"})
    return rows[0] if rows else None


_UNITS = {"d": 1, "д": 1, "w": 7, "н": 7, "m": 30, "м": 30, "y": 365, "г": 365, "л": 365}


def parse_period(s: str):
    """'7d', '3m', '1y', '2 мес', '10 дней' → дни."""
    m = re.match(r"^\s*(\d+)\s*([a-zа-я]*)\s*$", (s or "").lower())
    if not m:
        return None
    k = _UNITS.get((m[2] or "d")[0])
    return int(m[1]) * k if k else None


def elapsed(since: float) -> str:
    mins = int((time.time() - since) // 60)
    return f"{mins} мин." if mins < 60 else f"{mins // 60} ч {mins % 60} мин."
