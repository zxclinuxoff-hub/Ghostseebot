"""Фоновые задачи: отложенные удаления, напоминания, время в имени, предупреждения об окончании, чистка."""
import asyncio
import datetime as dt
import time
from zoneinfo import ZoneInfo

from aiogram import Bot

from ..db import db
from . import biz, gate
from . import users as U
from .logs import audit


async def run_jobs(bot: Bot):
    rows = await db.select("gs_jobs", {"run_at": f"lte.{U.iso(U.now())}", "order": "run_at.asc", "limit": 50})
    for j in rows:
        await db.delete("gs_jobs", {"id": f"eq.{j['id']}"})  # сначала удаляем: не зацикливаемся при ошибке
        p = j["payload"]
        try:
            if j["kind"] == "del":
                await biz.delete(p["bc"], p["ids"])
            elif j["kind"] == "remind":
                if p.get("to") == "chat":
                    await biz.send(p["bc"], p["chat_id"], "⏰ " + p["text"])
                else:
                    await bot.send_message(p["owner_chat"], "⏰ <b>Напоминание:</b> " + p["text"])
        except Exception as e:
            await audit("warn", "job_failed", None, kind=j["kind"], err=str(e)[:200])


async def update_names(bot: Bot):
    for u in await db.select("gs_users", {"settings->>time_on": "eq.true"}):
        s = u["settings"]
        if not U.is_active(u) or not await gate.allowed(bot, u["tg_id"]):
            continue
        try:
            hhmm = dt.datetime.now(ZoneInfo(s.get("time_tz", "Europe/Moscow"))).strftime("%H:%M")
        except Exception:
            continue
        if s.get("time_cur") == hhmm:
            continue
        try:
            await biz.set_name(s["time_bc"], f"{s['time_first']} | {hhmm}"[:64], s.get("time_last") or None)
            await U.set_settings(u["tg_id"], time_cur=hhmm)
        except Exception as e:
            await audit("warn", "time_name_failed", u["tg_id"], err=str(e)[:200])


async def warn_expiring(bot: Bot):
    n, nxt = U.now(), U.now() + dt.timedelta(days=1)
    rows = await db.select("gs_users", {"warned_exp": "eq.false", "banned": "eq.false",
                                        "and": f"(sub_until.gt.{U.iso(n)},sub_until.lt.{U.iso(nxt)})"})
    from ..keyboards import buy_shortcut
    for u in rows:
        try:
            await bot.send_message(u["tg_id"], "⏳ Через сутки закончится подписка. Продли, чтобы бот не вставал на паузу.", reply_markup=buy_shortcut())
        except Exception:
            pass
        await U.patch_user(u["tg_id"], warned_exp=True)


async def cleanup():
    await db.delete("gs_msgs", {"ts": f"lt.{U.iso(U.now() - dt.timedelta(days=7))}"})
    await db.delete("gs_logs", {"ts": f"lt.{U.iso(U.now() - dt.timedelta(days=30))}"})


async def run(bot: Bot):
    last_min = last_clean = 0.0
    while True:
        try:
            await run_jobs(bot)
            t = time.time()
            if t - last_min >= 60:
                last_min = t
                await update_names(bot)
                await warn_expiring(bot)
            if t - last_clean >= 900:
                last_clean = t
                await cleanup()
        except Exception as e:
            await audit("error", "scheduler", None, err=str(e)[:300])
        await asyncio.sleep(5)
