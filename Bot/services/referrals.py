from aiogram import Bot

from ..config import cfg
from ..db import db
from . import users as U
from .logs import audit


def bonus_for(n: int) -> int:
    """Сколько дней добавить, когда подтверждённых рефералов стало n.
    2 человека → +3 дня; 5 человек → +8 дней всего (ещё +5); дальше +1 день за каждого."""
    if n == 2:
        return 3
    if n == 5:
        return 5
    if n > 5:
        return 1
    return 0


async def register(referred_id: int, referrer_id: int):
    await db.insert("gs_referrals", {"referred_id": referred_id, "referrer_id": referrer_id},
                    upsert="referred_id", ignore=True, returning=False)


async def pending_row(referred_id: int):
    rows = await db.select("gs_referrals", {"referred_id": f"eq.{referred_id}", "status": "eq.pending"})
    return rows[0] if rows else None


async def is_subscribed(bot: Bot, uid: int):
    try:
        m = await bot.get_chat_member(cfg.channel, uid)
    except Exception as e:
        await audit("warn", "channel_check_failed", uid, err=str(e)[:200])
        return None
    return m.status in ("creator", "administrator", "member") or (m.status == "restricted" and getattr(m, "is_member", False))


async def try_credit(bot: Bot, referred_id: int) -> str:
    """'none' нет ожидающего реферала · 'not_subscribed' · 'error' · 'ok'."""
    row = await pending_row(referred_id)
    if not row:
        return "none"
    sub = await is_subscribed(bot, referred_id)
    if sub is None:
        return "error"
    if not sub:
        return "not_subscribed"
    upd = await db.update("gs_referrals", {"referred_id": f"eq.{referred_id}", "status": "eq.pending"},
                          {"status": "credited", "credited_at": U.iso(U.now())})
    if not upd:
        return "none"
    referrer = row["referrer_id"]
    n = await db.count("gs_referrals", {"referrer_id": f"eq.{referrer}", "status": "eq.credited"})
    bonus = bonus_for(n)
    if bonus:
        await db.update("gs_referrals", {"referred_id": f"eq.{referred_id}"}, {"bonus_days": bonus})
        await U.grant(referrer, bonus)
    await audit("info", "referral_credited", referrer, referred=referred_id, n=n, bonus=bonus)
    try:
        txt = f"👥 Новый реферал подтверждён! Всего: <b>{n}</b>."
        txt += f"\n🎁 Бонус: <b>+{bonus} дн.</b> подписки" if bonus else "\nДо следующего бонуса ещё немного 😉"
        await bot.send_message(referrer, txt)
    except Exception:
        pass
    return "ok"


async def stats(uid: int) -> dict:
    rows = await db.select_all("gs_referrals", {"referrer_id": f"eq.{uid}"})
    credited = [r for r in rows if r["status"] == "credited"]
    return {"confirmed": len(credited), "pending": len(rows) - len(credited), "bonus": sum(r.get("bonus_days") or 0 for r in credited)}
