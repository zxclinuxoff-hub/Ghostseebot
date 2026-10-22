"""Еженедельный отчёт админам: понедельник, с 10:00 по Москве. Отправляется один раз за неделю."""
from __future__ import annotations

import datetime as dt
import time
from collections import Counter
from zoneinfo import ZoneInfo

from aiogram import Bot

from ..config import PLANS, cfg
from ..db import DBError, db
from . import users as U
from .logs import audit
from .weekly_rules import should_send, week_key

TZ = ZoneInfo("Europe/Moscow")
SETTING = "weekly_report_last"
_last_check = 0.0
_sent_key: str | None = None


async def build_report(now: dt.datetime) -> str:
    iso = U.iso(now - dt.timedelta(days=7))
    new_users = await db.count("gs_users", {"created_at": f"gte.{iso}"})
    pays = await db.select_all("gs_payments", {"created_at": f"gte.{iso}"})
    dons = await db.select_all("gs_donations", {"created_at": f"gte.{iso}"})
    gifts_bought = await db.count("gs_gifts", {"created_at": f"gte.{iso}"})
    gifts_used = await db.count("gs_gifts", {"redeemed_at": f"gte.{iso}"})
    errors = await db.count("gs_logs", {"level": "eq.error", "ts": f"gte.{iso}"})
    active = await db.count("gs_users", {"sub_until": f"gte.{U.iso(now)}"})

    pay_stars = sum(p["stars"] or 0 for p in pays)
    by_plan = Counter(p["plan"] for p in pays)
    plans_txt = ", ".join(f"{PLANS[k]['title']}: {v}" for k, v in by_plan.items() if k in PLANS) or "—"
    don_stars = sum(d["stars"] or 0 for d in dons)
    return (
        "📊 <b>Отчёт за неделю</b>\n━━━━━━━━━━━━━━\n"
        f"👥 Новых пользователей: <b>{new_users}</b>\n"
        f"💳 Тарифы: <b>{len(pays)}</b> шт. · <b>{pay_stars}⭐</b>\n   {plans_txt}\n"
        f"🖤 Донаты: <b>{len(dons)}</b> шт. · <b>{don_stars}⭐</b>\n"
        f"🎁 Подарки: куплено <b>{gifts_bought}</b>, активировано <b>{gifts_used}</b>\n"
        f"✅ Активных подписок сейчас: <b>{active}</b>\n"
        f"🔴 Ошибок в логах: <b>{errors}</b>"
    )


async def maybe_send(bot: Bot) -> None:
    """Вызывается из планировщика. Проверка не чаще раза в 10 минут; при ошибке попробует снова позже."""
    global _last_check, _sent_key
    now_local = dt.datetime.now(dt.timezone.utc).astimezone(TZ)
    if now_local.weekday() != 0 or now_local.hour < 10:
        return
    if time.time() - _last_check < 600:
        return
    _last_check = time.time()
    key = week_key(now_local)
    if _sent_key == key:
        return
    try:
        rows = await db.select("gs_settings", {"key": f"eq.{SETTING}"})
        if rows and rows[0].get("value") == key:
            _sent_key = key
            return
        if not should_send(now_local, rows[0].get("value") if rows else None):
            return
        text = await build_report(dt.datetime.now(dt.timezone.utc))
    except DBError as e:
        await audit("error", "weekly_report_failed", None, err=str(e)[:200])
        return
    for aid in cfg.admin_ids:
        try:
            await bot.send_message(aid, text)
        except Exception:
            pass
    _sent_key = key
    try:
        await db.insert("gs_settings", {"key": SETTING, "value": key}, upsert="key", returning=False)
    except DBError as e:
        await audit("error", "weekly_mark_failed", None, err=str(e)[:200])
