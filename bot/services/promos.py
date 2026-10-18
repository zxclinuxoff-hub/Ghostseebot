"""Промокоды: дни подписки, лимит активаций, персональный, бонус рефереру, ссылка, включение/отключение."""
from __future__ import annotations

import datetime as dt
import math

from ..config import cfg
from ..db import db
from . import users as U
from .logs import audit

ERROR_TEXT = {
    "not_found": "❌ Код не найден",
    "inactive": "❌ Промокод отключён",
    "expired": "❌ Код истёк",
    "exhausted": "❌ Лимит активаций исчерпан",
    "used": "❌ Ты уже использовал этот код",
    "foreign": "❌ Этот код персональный для другого",
    "bad": "❌ Некорректный код",
    "error": "❌ Ошибка",
}


def _norm(code: str) -> str:
    return (code or "").strip().upper()


def promo_link(code: str) -> str:
    """Ссылка, по которой промокод активируется в один клик (через /start)."""
    return f"https://t.me/{cfg.bot_username}?start=promo_{_norm(code)}"


async def success_text(uid: int, days: int) -> str:
    u = await U.get_user(uid, fresh=True)
    until = U.fmt_dt(u["sub_until"]) if u and u.get("sub_until") else "—"
    return (f"✅ <b>Промокод активирован!</b>\n"
            f"➕ Зачислено: <b>+{days} дн.</b>\n"
            f"📅 Подписка активна до {until}")


async def create(
    code: str,
    days: int,
    max_uses: int | None = None,
    only_user: int | None = None,
    ref_bonus_days: int = 0,
    expires_hours: int | None = None,
    created_by: int | None = None,
) -> str:
    code = _norm(code)
    if not code or days < 1:
        return "bad"
    expires = None
    if expires_hours and expires_hours > 0:
        expires = U.iso(U.now() + dt.timedelta(hours=expires_hours))
    row = {
        "code": code,
        "days": days,
        "max_uses": max_uses,
        "used": 0,
        "only_user": only_user,
        "ref_bonus_days": ref_bonus_days or 0,
        "expires_at": expires,
        "created_by": created_by,
        "active": True,
    }
    # при ошибке БД db.insert сам бросит исключение — его обработает вызывающий код
    await db.insert("gs_promos", row, upsert="code", returning=False)
    await audit("info", "promo_create", created_by, code=code, days=days, max_uses=max_uses)
    return "ok"


async def get(code: str):
    rows = await db.select("gs_promos", {"code": f"eq.{_norm(code)}"})
    return rows[0] if rows else None


async def set_active(code: str, active: bool) -> bool:
    rows = await db.update("gs_promos", {"code": f"eq.{_norm(code)}"}, {"active": active})
    return bool(rows)


async def delete(code: str) -> None:
    code = _norm(code)
    await db.delete("gs_promo_redemptions", {"code": f"eq.{code}"})
    await db.delete("gs_promos", {"code": f"eq.{code}"})


async def redemptions(code: str, limit: int = 30) -> list:
    return await db.select("gs_promo_redemptions",
                           {"code": f"eq.{_norm(code)}", "order": "created_at.desc", "limit": limit})


async def redeem(bot, uid: int, code: str) -> tuple[str, int]:
    """Активировать промокод. Возвращает (статус, зачисленные дни). Статус: ok или ключ из ERROR_TEXT."""
    code = _norm(code)
    rows = await db.select("gs_promos", {"code": f"eq.{code}"})
    if not rows:
        return "not_found", 0
    p = rows[0]
    if p.get("active") is False:
        return "inactive", 0
    if p.get("expires_at"):
        exp = U.parse(p["expires_at"])
        if exp and U.now() > exp:
            return "expired", 0
    if p.get("only_user") and int(p["only_user"]) != uid:
        return "foreign", 0
    if p.get("max_uses") is not None and int(p.get("used") or 0) >= int(p["max_uses"]):
        return "exhausted", 0
    already = await db.select("gs_promo_redemptions", {"code": f"eq.{code}", "tg_id": f"eq.{uid}"})
    if already:
        return "used", 0
    days = int(p.get("days") or 0)
    if days < 1:
        return "bad", 0
    await U.grant(uid, days)
    await db.insert("gs_promo_redemptions", {"code": code, "tg_id": uid}, ignore=True, returning=False)
    await db.update("gs_promos", {"code": f"eq.{code}"}, {"used": int(p.get("used") or 0) + 1})
    # бонус рефереру
    bonus = int(p.get("ref_bonus_days") or 0)
    if bonus > 0:
        refs = await db.select("gs_referrals", {"referred_id": f"eq.{uid}", "status": "eq.credited"})
        if refs:
            rid = refs[0]["referrer_id"]
            await U.grant(rid, bonus)
            try:
                await bot.send_message(rid, f"🎁 Твой реферал активировал промокод — тебе <b>+{bonus} дн.</b>")
            except Exception:
                pass
    await audit("info", "promo_redeem", uid, code=code, days=days)
    return "ok", days


async def list_page(page: int = 1, size: int = 6):
    """(строки, всего, страниц, текущая страница)"""
    total = await db.count("gs_promos")
    pages = max(1, math.ceil(total / size))
    page = min(max(1, page), pages)
    rows = await db.select("gs_promos", {"order": "created_at.desc", "limit": size,
                                         "offset": (page - 1) * size})
    return rows, total, pages, page


async def list_recent(limit: int = 15) -> list:
    rows = await db.select_all("gs_promos", {})
    rows = sorted(rows or [], key=lambda x: x.get("created_at") or "", reverse=True)
    return rows[:limit]
