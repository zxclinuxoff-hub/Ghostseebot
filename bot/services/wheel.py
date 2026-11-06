"""Колесо фортуны (Mini App). Шанс считается только здесь, на сервере; в приложении только показ."""
import asyncio
import datetime as dt
import math
from collections import Counter
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
# Самолётик: ставка прокрутами (любыми: бесплатными или купленными), выигрыш осколками, они суммируются с осколками колеса.
CRASH_EDGE = 0.07   # преимущество заведения: при любой стратегии игроки в среднем получают 93% ставки
CRASH_CAP = 50.0    # потолок множителя
CRASH_K = 0.09      # рост множителя: m(t) = e^(K·t), ×2 примерно за 7,7 с, ×10 за 26 с
CRASH_MAX_BET = 10
CRASH_SHARDS = 1.5  # осколков за каждый прокрут ставки при ×1.00: на множителе x выплата = ставка·x·1,5 осколка
ADMIN_CONTACT = "@morphynne"
# (код, шанс %, иконка, название). Порядок = порядок секторов на колесе.
PRIZES = [
    # Осколки и скидки — частые награды; мишка — редкий приз (0,05%, примерно 1 на 2000 прокрутов в среднем).
    ("shard", 59.5, "🔹", "Осколок"), ("free", 5.0, "🔁", "Ещё попытка"),
    ("disc_m3", 13.0, "🎫", "Скидка на 3 мес"), ("disc_y1", 8.0, "💎", "Скидка на год"),
    ("d1", 10.0, "🌙", "+1 день"), ("d2", 1.2, "🌗", "+2 дня"), ("d3", 2.0, "🌗", "+3 дня"), ("d7", 0.8, "🌕", "+7 дней"),
    ("d30", 0.05, "👑", "+30 дней"), ("bear", 0.05, "🧸", "Мишка"), ("vip", 0.4, "👻", "VIP на 7 дней"),
]
# 21% на скидки; ~16% на +1…+3 дня; 56,5% на осколки. Вероятности показываются в Mini App из этого же списка.
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
    result = await db.rpc("gs_wheel_admin_add", {"p_tg_id": uid, "p_amount": n})
    return int(result["bonus_spins"] if isinstance(result, dict) else result)


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


async def _finish(bot, uid: int, charge_id, paid: bool, count_daily: bool = True):
    """Крутит, пишет лог (charge_id уникален: повторная доставка платежа не даёт второй приз), выдаёт приз."""
    code = roll()
    rows = await db.insert("gs_wheel_log", {"tg_id": uid, "prize": code, "paid": paid, "charge_id": charge_id},
                           upsert="charge_id", ignore=True) if charge_id else \
        await db.insert("gs_wheel_log", {"tg_id": uid, "prize": code, "paid": paid})
    if not rows:
        return None  # этот платёж уже обработан
    if paid and count_daily:
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
        out.append({"code": x["prize"], "icon": p[2], "name": p[3], "ago": int((now - U.parse(x["ts"])).total_seconds())})
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
        "crash": {"k": CRASH_K, "cap": CRASH_CAP, "max_bet": CRASH_MAX_BET, "shards_per": CRASH_SHARDS, "rtp": round((1 - CRASH_EDGE) * 100),
                  "active": await _crash_active(uid)},
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
    try:
        await db.rpc("gs_wheel_spend", {"p_tg_id": uid, "p_kind": "credit", "p_n": 1})
    except Exception as e:
        msg = str(e)
        if "NO_CREDITS" in msg:
            return web.json_response({"error": "Купленных прокрутов нет"})
        if "DAILY_LIMIT" in msg:
            return web.json_response({"error": "Лимит прокрутов на сегодня исчерпан"})
        raise
    return web.json_response(await _finish(request.app["wheel_bot"], uid, None, True, count_daily=False))


async def h_free(request):
    uid, _ = await _auth(request)
    try:
        await db.rpc("gs_wheel_spend", {"p_tg_id": uid, "p_kind": "free", "p_n": 1})
    except Exception as e:
        if "NO_BONUS" in str(e):
            return web.json_response({"error": "Бесплатных прокрутов нет"})
        raise
    return web.json_response(await _finish(request.app["wheel_bot"], uid, None, False))


def _effects(r: dict, codes: list):
    """Суммарный эффект пачки прокрутов (меняет r). Возвращает (счётчик, дни, скидки, осколков->дни)."""
    cnt = Counter(codes)
    days = sum(cnt[f"d{n}"] * n for n in (1, 2, 3, 7, 30))
    r["shards"] += cnt["shard"]
    conv, r["shards"] = divmod(r["shards"], SHARDS_NEED)
    days += conv * 3
    r["bonus_spins"] += cnt["free"]
    if cnt["vip"]:
        base = max(U.now(), U.parse(r.get("vip_until")) or U.now())
        r["vip_until"] = U.iso(base + dt.timedelta(days=7 * cnt["vip"]))
    disc = {}
    for plan in ("m3", "y1"):
        if cnt[f"disc_{plan}"]:
            disc[plan] = max(_rng.choice(range(10, 36, 5) if plan == "y1" else range(5, 21, 5)) for _ in range(cnt[f"disc_{plan}"]))
    return cnt, days, disc, conv


async def h_multi(request):
    """Открыть 5 или 10 прокрутов за раз: сначала бесплатные, потом купленные. Всего ~5 запросов к БД на пачку."""
    uid, body = await _auth(request)
    n = int(body.get("n", 0))
    if n not in (5, 10):
        return web.json_response({"error": "Можно открыть 5 или 10 за раз"})
    try:
        spent = await db.rpc("gs_wheel_spend", {"p_tg_id": uid, "p_kind": "multi", "p_n": n})
    except Exception as e:
        msg = str(e)
        if "NO_CREDITS" in msg:
            return web.json_response({"error": "Не хватает прокрутов"})
        if "DAILY_LIMIT" in msg:
            return web.json_response({"error": "Дневной лимит платных прокрутов исчерпан"})
        raise
    use_free = int(spent["free_used"])
    r = await _row(uid)
    codes = [roll() for _ in range(n)]
    cnt, days, disc, conv = _effects(r, codes)
    await _save(r)
    await db.insert("gs_wheel_log", [{"tg_id": uid, "prize": c, "paid": i >= use_free} for i, c in enumerate(codes)], returning=False)
    patch = {}
    if disc:
        u = await U.get_user(uid, fresh=True) or {}
        until = U.iso(U.now() + dt.timedelta(hours=2, minutes=30))
        for plan, pct in disc.items():
            patch[f"disc_{plan}"] = max(pct, int(u.get(f"disc_{plan}") or 0))
            patch[f"disc_{plan}_until"] = until
        await U.patch_user(uid, **patch)
    if days:
        await U.grant(uid, days)
    lines = [f"{p[2]} {p[3]} ×{cnt[p[0]]}" for p in PRIZES if cnt[p[0]]]
    if days:
        lines.append(f"🎉 Итого +{days} дн. подписки")
    for plan in disc:
        lines.append(f"🏷 Скидка {patch['disc_' + plan]}% на {'год' if plan == 'y1' else '3 мес'} (2,5 часа)")
    if cnt["bear"]:
        lines.append(f"🧸 Мишка ×{cnt['bear']}! Напишите администратору для выдачи — {ADMIN_CONTACT}")
    text = "\n".join(lines)
    bot = request.app["wheel_bot"]
    try:
        await bot.send_message(uid, f"🎡 Открыто {n}:\n{text}")
    except Exception:
        pass
    if cnt["bear"]:
        u = await U.get_user(uid) or {}
        for aid in cfg.admin_ids:
            try:
                await bot.send_message(aid, f"🧸 Мишка выпал ({cnt['bear']} шт.)! <code>{uid}</code> {u.get('first_name', '')} "
                                            f"{('@' + u['username']) if u.get('username') else ''}")
            except Exception:
                pass
    await audit("info", "wheel_multi", uid, n=n, days=days)
    return web.json_response({"results": codes, "counts": dict(cnt), "text": text, "days": days})


def _stoch(x: float) -> int:
    """Несмещённое округление: 2,4 прокрута = 2 или 3 с вероятностью 60/40, среднее сохраняется."""
    f = math.floor(x)
    return f + (1 if _rng.random() < x - f else 0)


def _crash_point() -> float:
    u = 1.0 - _rng.random()  # (0; 1]
    return max(1.0, min(CRASH_CAP, math.floor((1 - CRASH_EDGE) / u * 100) / 100))


def _mult_at(row: dict, now) -> float:
    return math.exp(CRASH_K * max(0.0, (now - U.parse(row["started_at"])).total_seconds()))


async def _crash_finish(row: dict, status: str, mult: float, payout: int = 0):
    """Закрывает раунд один раз (фильтр status=active защищает от двойной выплаты). Возвращает (закрыт ли, дней подписки)."""
    done = await db.update("gs_crash", {"id": f"eq.{row['id']}", "status": "eq.active"},
                           {"status": status, "mult": mult, "payout": payout})
    days = 0
    if done and payout:
        try:
            r = await _row(row["tg_id"])
            conv, r["shards"] = divmod(r["shards"] + payout, SHARDS_NEED)  # осколки суммируются; 10 штук = +3 дня
            await _save(r)
            if conv:
                days = conv * 3
                await U.grant(row["tg_id"], days)
        except Exception as e:
            await audit("error", "crash_payout_failed", row["tg_id"], id=row["id"], payout=payout, err=str(e)[:200])
            raise
    return bool(done), days


async def _crash_check(row: dict):
    """Сверка раунда со временем: (статус, множитель, осколков, дней); статус active|crashed|cashed|done."""
    point, m = float(row["point"]), _mult_at(row, U.now())
    if m < point:
        return "active", math.floor(m * 100) / 100, 0, 0
    if point >= CRASH_CAP:  # дошёл до потолка: авто-вывод
        pay = _stoch(row["bet"] * CRASH_CAP * CRASH_SHARDS)
        ok, days = await _crash_finish(row, "cashed", CRASH_CAP, pay)
        return ("cashed", CRASH_CAP, pay, days) if ok else ("done", point, 0, 0)
    ok, _ = await _crash_finish(row, "crashed", point)
    return ("crashed", point, 0, 0) if ok else ("done", point, 0, 0)


async def _crash_row(uid: int):
    rows = await db.select("gs_crash", {"tg_id": f"eq.{uid}", "status": "eq.active", "order": "id.desc", "limit": 1})
    return rows[0] if rows else None


async def _crash_active(uid: int):
    row = await _crash_row(uid)
    if not row or (await _crash_check(row))[0] != "active":
        return None
    return {"id": row["id"], "bet": row["bet"], "start_ms": int(U.parse(row["started_at"]).timestamp() * 1000),
            "now_ms": int(time.time() * 1000)}


async def h_crash_start(request):
    uid, body = await _auth(request)
    bet = int(body.get("bet", 1))
    if not 1 <= bet <= CRASH_MAX_BET:
        return web.json_response({"error": f"Ставка от 1 до {CRASH_MAX_BET} прокрутов"})
    point, started = _crash_point(), U.now()
    try:
        rows = await db.rpc("gs_crash_start", {"p_tg_id": uid, "p_bet": bet, "p_point": point, "p_started_at": U.iso(started)})
    except Exception as e:
        msg = str(e)
        if "ROUND_ACTIVE" in msg:
            act = await _crash_active(uid)
            return web.json_response({"error": "Раунд уже идёт", "active": act})
        if "NO_SPINS" in msg:
            return web.json_response({"error": "Не хватает прокрутов"})
        raise
    row = rows[0] if isinstance(rows, list) else rows
    if point <= 1.0:
        return web.json_response({"crashed": True, "mult": 1.0, "bet": bet})
    return web.json_response({"id": rows[0]["id"], "bet": bet, "start_ms": int(started.timestamp() * 1000),
                              "now_ms": int(time.time() * 1000)})


def _crash_json(st, row):
    status, mult, pay, days = st
    return web.json_response({"status": status, "mult": mult, "shards": pay, "days": days, "bet": row["bet"]})


async def h_crash_cash(request):
    uid, _ = await _auth(request)
    row = await _crash_row(uid)
    if not row:
        return web.json_response({"status": "none"})
    m = math.floor(_mult_at(row, U.now()) * 100) / 100
    if m >= float(row["point"]):            # опоздал: самолёт уже улетел
        return _crash_json(await _crash_check(row), row)
    pay = _stoch(row["bet"] * m * CRASH_SHARDS)
    ok, days = await _crash_finish(row, "cashed", m, pay)
    return _crash_json(("cashed", m, pay, days) if ok else ("done", m, 0, 0), row)


async def h_crash_wait(request):
    """Долгий запрос: держится до момента краха и сообщает результат (клиент не знает точку заранее)."""
    uid, _ = await _auth(request)
    row = await _crash_row(uid)
    if not row:
        return web.json_response({"status": "none"})
    left = math.log(float(row["point"])) / CRASH_K - (U.now() - U.parse(row["started_at"])).total_seconds()
    if left > 0:
        await asyncio.sleep(min(left + 0.05, 75))
    row = await _crash_row(uid)
    if not row:                              # клиент уже забрал выигрыш
        return web.json_response({"status": "none"})
    return _crash_json(await _crash_check(row), row)


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
    for name, h in (("state", h_state), ("invoice", h_invoice), ("free", h_free), ("credit", h_credit), ("multi", h_multi), ("crash_start", h_crash_start), ("crash_cash", h_crash_cash), ("crash_wait", h_crash_wait), ("last", h_last)):
        app.router.add_post(f"/api/wheel/{name}", h)
