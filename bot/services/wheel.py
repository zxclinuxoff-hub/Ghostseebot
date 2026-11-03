"""Колесо фортуны (Mini App). Шанс считается только здесь, на сервере; в приложении только показ."""
import datetime as dt
import hashlib
import hmac
import json
import random
import time
from pathlib import Path
from urllib.parse import parse_qsl

from aiohttp import web
from aiogram.types import LabeledPrice

from ..config import cfg
from ..db import db
from . import users as U
from .logs import audit

PRICE = 1            # звёзд за прокрут
DAILY_LIMIT = 50     # платных прокрутов в сутки на человека
SHARDS_NEED = 10     # осколков до +3 дней
PACKS = {1: 1, 5: 4, 10: 8, 20: 16, 30: 24, 50: 40}  # пакеты: прокрутов -> звёзд (от 5 шт. скидка 20%)
STREAK_DAYS = 7      # дней подряд до бесплатного прокрута
FEED_PRIZES = ("d7", "d30", "bear")  # что показываем в ленте выигрышей
_feed_cache = (0.0, [])
ADMIN_CONTACT = "@morphynne"
# (код, шанс %, иконка, название). Порядок = порядок секторов на колесе.
PRIZES = [
    # Осколки и скидки — частые награды; мишка — редкий приз (0,05%, примерно 1 на 2000 прокрутов в среднем).
    ("shard", 60.0, "🔹", "Осколок"), ("free", 5.0, "🔁", "Ещё попытка"),
    ("disc_m3", 13.0, "🎫", "Скидка на 3 мес"), ("disc_y1", 8.0, "💎", "Скидка на год"),
    ("d1", 9.0, "🌙", "+1 день"), ("d2", 1.5, "🌗", "+2 дня"), ("d3", 2.5, "🌗", "+3 дня"), ("d7", 0.5, "🌕", "+7 дней"),
    ("d30", 0.05, "👑", "+30 дней"), ("bear", 0.05, "🧸", "Мишка"), ("vip", 0.4, "👻", "VIP на 7 дней"),
]
# 21% на скидки; 13% на +1 или +3 дня; 60% на осколки. Вероятности показываются в Mini App из этого же списка.
assert abs(sum(p[1] for p in PRIZES) - 100) < 1e-9
_rng = random.SystemRandom()
_PAGE = Path(__file__).resolve().parents[2] / "webapp" / "wheel.html"


def roll() -> str:
    return _rng.choices([p[0] for p in PRIZES], weights=[p[1] for p in PRIZES])[0]


def check_init(init_data: str, token: str, max_age: int = 86400):
    """Проверка подписи Telegram WebApp initData. Возвращает dict пользователя или None."""
    try:
        d = dict(parse_qsl(init_data, keep_blank_values=True))
        h = d.pop("hash", "")
        s = "\n".join(f"{k}={v}" for k, v in sorted(d.items()))
        key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        if not h or not hmac.compare_digest(hmac.new(key, s.encode(), hashlib.sha256).hexdigest(), h):
            return None
        if time.time() - int(d.get("auth_date", 0)) > max_age:
            return None
        return json.loads(d["user"])
    except Exception:
        return None


async def _row(uid: int) -> dict:
    rows = await db.select("gs_wheel", {"tg_id": f"eq.{uid}"})
    r = rows[0] if rows else {"tg_id": uid}
    for k in ("shards", "bonus_spins", "credits", "spins_today", "streak"):
        r[k] = int(r.get(k) or 0)
    today = U.now().date().isoformat()
    if r.get("day") != today:
        r["day"], r["spins_today"] = today, 0
    return r


async def _save(r: dict):
    keys = ("tg_id", "shards", "bonus_spins", "credits", "spins_today", "day", "vip_until", "streak", "last_visit")
    await db.insert("gs_wheel", {k: r.get(k) for k in keys}, upsert="tg_id", returning=False)


async def can_pay(uid: int) -> bool:
    u = await U.get_user(uid)
    return bool(u and not u.get("banned") and (await _row(uid))["spins_today"] < DAILY_LIMIT)


async def add_bonus(uid: int, n: int) -> int:
    r = await _row(uid)
    r["bonus_spins"] = max(0, int(r.get("bonus_spins") or 0) + n)
    await _save(r)
    return r["bonus_spins"]


async def _apply(uid: int, code: str) -> str:
    r = await _row(uid)
    if code == "shard":
        r["shards"] = int(r.get("shards") or 0) + 1
        txt = f"🔹 +1 осколок ({r['shards']}/{SHARDS_NEED})"
        if r["shards"] >= SHARDS_NEED:
            r["shards"] -= SHARDS_NEED
            await U.grant(uid, 3)
            txt += "\n🎉 Собрано 10 осколков: +3 дня подписки!"
    elif code == "free":
        r["bonus_spins"] = int(r.get("bonus_spins") or 0) + 1
        txt = "🔁 Ещё одна бесплатная попытка!"
    elif code in ("d1", "d2", "d3", "d7", "d30"):
        n = int(code[1:])
        await U.grant(uid, n)
        txt = f"🎉 +{n} дн. подписки!"
    elif code in ("disc_m3", "disc_y1"):
        plan = code[5:]
        pct = _rng.choice(range(10, 36, 5) if plan == "y1" else range(5, 21, 5))
        u = await U.get_user(uid, fresh=True) or {}
        pct = max(pct, int(u.get(f"disc_{plan}") or 0))
        until = U.now() + dt.timedelta(hours=2, minutes=30)
        await U.patch_user(uid, **{f"disc_{plan}": pct, f"disc_{plan}_until": U.iso(until)})
        txt = f"🏷 Скидка {pct}% на {'год' if plan == 'y1' else '3 месяца'} на 2,5 часа. Применится в разделе «Подписка»."
    elif code == "vip":
        base = max(U.now(), U.parse(r.get("vip_until")) or U.now())
        r["vip_until"] = U.iso(base + dt.timedelta(days=7))
        txt = "👻 VIP-статус на 7 дней!"
    else:  # bear
        txt = f"🧸 Вы выиграли мишку — 0,5%!\nНапишите администратору для выдачи — {ADMIN_CONTACT}"
    await _save(r)
    return txt


async def _finish(bot, uid: int, charge_id, paid: bool):
    """Крутит, пишет лог (charge_id уникален: повторная доставка платежа не даёт второй приз), выдаёт приз."""
    code = roll()
    rows = await db.insert("gs_wheel_log", {"tg_id": uid, "prize": code, "paid": paid, "charge_id": charge_id},
                           upsert="charge_id", ignore=True) if charge_id else \
        await db.insert("gs_wheel_log", {"tg_id": uid, "prize": code, "paid": paid})
    if not rows:
        return None  # этот платёж уже обработан
    if paid:
        r = await _row(uid)
        r["spins_today"] += 1
        await _save(r)
    txt = await _apply(uid, code)
    await db.update("gs_wheel_log", {"id": f"eq.{rows[0]['id']}"}, {"note": txt})
    await audit("info", "wheel_spin", uid, prize=code, paid=paid)
    try:
        await bot.send_message(uid, txt)
    except Exception:
        pass
    if code == "bear":
        u = await U.get_user(uid) or {}
        for aid in cfg.admin_ids:
            try:
                await bot.send_message(aid, f"🧸 Мишка выпал! <code>{uid}</code> {u.get('first_name', '')} "
                                            f"{('@' + u['username']) if u.get('username') else ''}")
            except Exception:
                pass
    return {"id": rows[0]["id"], "prize": code, "text": txt}


def _checkin(r: dict):
    """Серия дней подряд. None — сегодня уже заходил; True — серия закрыта, начислен прокрут; False — просто +1 день."""
    today = U.now().date()
    last = r.get("last_visit")
    if last == today.isoformat():
        return None
    r["streak"] = r["streak"] + 1 if last == (today - dt.timedelta(days=1)).isoformat() else 1
    r["last_visit"] = today.isoformat()
    if r["streak"] >= STREAK_DAYS:
        r["streak"], r["bonus_spins"] = 0, r["bonus_spins"] + 1
        return True
    return False


async def _feed() -> list:
    """Лента крупных выигрышей без имён; кэш 30 с, чтобы не плодить запросы."""
    global _feed_cache
    if time.time() - _feed_cache[0] < 30:
        return _feed_cache[1]
    rows = await db.select("gs_wheel_log", {"prize": f"in.({','.join(FEED_PRIZES)})", "order": "id.desc", "limit": 6})
    now, out = U.now(), []
    for x in rows:
        p = next(p for p in PRIZES if p[0] == x["prize"])
        out.append({"icon": p[2], "name": p[3], "ago": int((now - U.parse(x["ts"])).total_seconds())})
    _feed_cache = (time.time(), out)
    return out


async def can_pack(uid: int, n: int, amount: int) -> bool:
    u = await U.get_user(uid)
    return bool(u and not u.get("banned") and PACKS.get(n) == amount)


async def _pack_paid(bot, uid: int, n: int, charge_id: str):
    rows = await db.insert("gs_wheel_log", {"tg_id": uid, "prize": f"pack{n}", "paid": True, "charge_id": charge_id,
                                            "note": f"🎟 Пакет оплачен: +{n} прокрутов"}, upsert="charge_id", ignore=True)
    if not rows:
        return
    r = await _row(uid)
    r["credits"] += n
    await _save(r)
    await audit("info", "wheel_pack", uid, n=n)
    try:
        await bot.send_message(uid, f"🎟 Пакет оплачен: +{n} прокрутов. Открой «Колесо фортуны» в меню бота.")
    except Exception:
        pass


async def on_paid(bot, m):
    sp = m.successful_payment
    if sp.invoice_payload.startswith("wheelpack:"):
        n = int(sp.invoice_payload.split(":")[1])
        if PACKS.get(n) != sp.total_amount:
            return await audit("warn", "wheel_pack_mismatch", m.from_user.id, n=n, amount=sp.total_amount)
        return await _pack_paid(bot, m.from_user.id, n, sp.telegram_payment_charge_id)
    await _finish(bot, m.from_user.id, sp.telegram_payment_charge_id, True)


async def admin_text() -> str:
    single = await db.count("gs_wheel_log", {"paid": "eq.true", "charge_id": "not.is.null", "prize": "not.like.pack*"})
    cnt = {n: await db.count("gs_wheel_log", {"prize": f"eq.pack{n}"}) for n in PACKS}
    stars = single * PRICE + sum(cnt[n] * PACKS[n] for n in PACKS)
    packs_txt = " · ".join(f"{n}шт: <b>{c}</b>" for n, c in cnt.items())
    bears = await db.select("gs_wheel_log", {"prize": "eq.bear", "order": "id.desc", "limit": 10})
    b = "\n".join(f"• <code>{x['tg_id']}</code> ({U.fmt_dt(x['ts'])})" for x in bears) or "пока нет"
    return (f"🎡 <b>Колесо фортуны</b>\nПакеты: {packs_txt}\nВыручка: <b>{stars}⭐</b>\n\n"
            f"🧸 Последние выигравшие мишку (выдать вручную):\n{b}\n\n"
            "Выдать прокруты: <code>/spins ID 5</code> или <code>/spins @name 3</code>\n"
            "Забрать: <code>/spins ID -2</code>")


# ---------- HTTP API для Mini App ----------
async def _auth(request):
    body = await request.json()
    user = check_init(body.get("initData", ""), cfg.bot_token)
    if not user:
        raise web.HTTPUnauthorized(text="Открой приложение из бота")
    u = await U.get_user(user["id"])
    if not u or u.get("banned"):
        raise web.HTTPForbidden(text="Сначала запусти бота (/start)")
    return user["id"], body


async def h_state(request):
    uid, _ = await _auth(request)
    r = await _row(uid)
    gift = _checkin(r)
    if gift is not None:
        await _save(r)
    last = await db.select("gs_wheel_log", {"tg_id": f"eq.{uid}", "order": "id.desc", "limit": 1})
    return web.json_response({
        "price": PRICE, "limit": DAILY_LIMIT, "need": SHARDS_NEED, "shards": r["shards"], "bonus": r["bonus_spins"], "credits": r["credits"],
        "left": max(0, DAILY_LIMIT - r["spins_today"]), "vip_until": r.get("vip_until"),
        "streak": r["streak"], "streak_need": STREAK_DAYS, "streak_gift": gift is True,
        "packs": [{"n": n, "stars": st} for n, st in PACKS.items()], "feed": await _feed(),
        "last_id": last[0]["id"] if last else 0,
        "prizes": [{"code": c, "p": p, "icon": i, "name": n} for c, p, i, n in PRIZES],
    })


async def h_invoice(request):
    uid, body = await _auth(request)
    n = int(body.get("pack", 1))
    if n not in PACKS:
        return web.json_response({"error": "Неизвестный пакет"})
    link = await request.app["wheel_bot"].create_invoice_link(
        title=f"Прокрутов: {n}", description=f"{n} прокрутов колеса фортуны", payload=f"wheelpack:{n}:{uid}",
        currency="XTR", prices=[LabeledPrice(label=f"{n} прокрутов", amount=PACKS[n])])
    return web.json_response({"link": link})


async def h_credit(request):
    uid, _ = await _auth(request)
    r = await _row(uid)
    if r["credits"] <= 0:
        return web.json_response({"error": "Купленных прокрутов нет"})
    if r["spins_today"] >= DAILY_LIMIT:
        return web.json_response({"error": "Лимит прокрутов на сегодня исчерпан"})
    r["credits"] -= 1
    await _save(r)
    return web.json_response(await _finish(request.app["wheel_bot"], uid, None, True))


async def h_free(request):
    uid, _ = await _auth(request)
    r = await _row(uid)
    if int(r.get("bonus_spins") or 0) <= 0:
        return web.json_response({"error": "Бесплатных прокрутов нет"})
    r["bonus_spins"] -= 1
    await _save(r)
    return web.json_response(await _finish(request.app["wheel_bot"], uid, None, False))


async def h_last(request):
    uid, body = await _auth(request)
    rows = await db.select("gs_wheel_log", {"tg_id": f"eq.{uid}", "id": f"gt.{int(body.get('after', 0))}",
                                            "order": "id.asc", "limit": 1})
    if not rows or not rows[0].get("note"):
        return web.json_response({"found": False})
    return web.json_response({"found": True, "id": rows[0]["id"], "prize": rows[0]["prize"], "text": rows[0]["note"]})


async def h_page(_request):
    return web.FileResponse(_PAGE, headers={"Cache-Control": "no-store"})


def setup(app, bot):
    app["wheel_bot"] = bot
    app.router.add_get("/app", h_page)
    for name, h in (("state", h_state), ("invoice", h_invoice), ("free", h_free), ("credit", h_credit), ("last", h_last)):
        app.router.add_post(f"/api/wheel/{name}", h)
