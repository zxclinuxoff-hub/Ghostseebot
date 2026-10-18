"""Промокоды: дни подписки, лимит активаций, персональный, бонус рефереру."""
from __future__ import annotations

import datetime as dt

from ..db import db
from . import users as U
from .logs import audit


def _norm(code: str) -> str:
    return (code or "").strip().upper()


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
    }
    ok = await db.insert("gs_promos", row, upsert="code", returning=False)
    return "ok" if ok is not False else "err"


async def redeem(bot, uid: int, code: str) -> str:
    """ok / not_found / expired / exhausted / used / foreign / error"""
    code = _norm(code)
    rows = await db.select("gs_promos", {"code": f"eq.{code}"})
    if not rows:
        return "not_found"
    p = rows[0]
    if p.get("expires_at"):
        exp = U.parse(p["expires_at"])
        if exp and U.now() > exp:
            return "expired"
    if p.get("only_user") and int(p["only_user"]) != uid:
        return "foreign"
    if p.get("max_uses") is not None and int(p.get("used") or 0) >= int(p["max_uses"]):
        return "exhausted"
    already = await db.select("gs_promo_redemptions", {"code": f"eq.{code}", "tg_id": f"eq.{uid}"})
    if already:
        return "used"
    days = int(p.get("days") or 0)
    if days < 1:
        return "bad"
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
    return "ok"


async def list_recent(limit: int = 15) -> list:
    rows = await db.select_all("gs_promos", {})
    rows = sorted(rows or [], key=lambda x: x.get("created_at") or "", reverse=True)
    return rows[:limit]
