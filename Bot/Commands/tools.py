"""Реализации точка-команд."""
from __future__ import annotations

import asyncio
import random
import re
import time
import urllib.parse

import httpx

from ..config import cfg
from ..db import db
from ..keyboards import unmute_kb
from ..services import biz
from ..services import users as U
from .engine import Ctx, command, dur, esc, REG
from ..texts import HELP_CMDS

# ================= форматирование =================
FMT = {
    "bold": ("<b>", "</b>"), "italic": ("<i>", "</i>"), "mono": ("<code>", "</code>"),
    "line": ("<u>", "</u>"), "crossed": ("<s>", "</s>"), "hidden": ("<tg-spoiler>", "</tg-spoiler>"),
    "quote": ("<blockquote>", "</blockquote>"), "code": ("<pre>", "</pre>"),
}


def _fmt(o, c):
    async def fn(ctx: Ctx):
        await ctx.edit(o + esc(ctx.src) + c)
    return fn


for _n, (_o, _c) in FMT.items():
    command(_n)(_fmt(_o, _c))

RU = dict(zip("абвгдежзийклмнопрстуфхцчшщъыьэюя", ".- -... .-- --. -.. . ...- --.. .. .--- -.- .-.. -- -. --- .--. .-. ... - ..- ..-. .... -.-. ---. ---- --.- --.-- -.-- -..- ..-.. ..-- .-.-".split()))
EN = dict(zip("abcdefghijklmnopqrstuvwxyz", ".- -... -.-. -.. . ..-. --. .... .. .--- -.- .-.. -- -. --- .--. --.- .-. ... - ..- ...- .-- -..- -.-- --..".split()))
DG = dict(zip("0123456789", "----- .---- ..--- ...-- ....- ..... -.... --... ---.. ----.".split()))


@command("morse")
async def morse(c: Ctx):
    en = bool(re.match(r"^en\s", c.args, re.I))
    t = c.args[3:] if en else c.src
    if re.fullmatch(r"[.\-/\s]+", t):
        rev = {v: k for k, v in {**(EN if en else RU), **DG}.items()}
        out = " ".join("".join(rev.get(x, "?") for x in w.split()) for w in re.split(r"\s*/\s*", t.strip()))
    else:
        out = " ".join("/" if ch == " " else (RU.get(ch) or EN.get(ch) or DG.get(ch) or "") for ch in t.lower()).replace("  ", " ")
    await c.edit(f"<code>{esc(out)}</code>")


EN_L = "qwertyuiop[]asdfghjkl;'zxcvbnm,./`QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>?~"
RU_L = "йцукенгшщзхъфывапролджэячсмитьбю.ёЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,Ё"


@command("sw")
async def sw(c: Ctx):
    s = c.src
    a, b = (RU_L, EN_L) if re.search(r"[а-яё]", s, re.I) else (EN_L, RU_L)
    await c.edit(esc("".join(b[a.index(ch)] if ch in a else ch for ch in s)))


# ================= анимации =================
async def frames(c: Ctx, items, delay=0.6):
    for f in items:
        try:
            await c.edit(f)
        except Exception:
            pass
        await asyncio.sleep(delay)


@command("anim")
async def anim(c: Ctx):
    t = c.src
    step = max(1, len(t) // 15)
    await frames(c, [esc(t[:i]) + "▌" for i in range(step, len(t), step)] + [esc(t)], 0.5)


@command("type")
async def type_(c: Ctx):
    w = c.src.split()[:40]
    await frames(c, [esc(" ".join(w[:i])) + (" ▌" if i < len(w) else "") for i in range(1, len(w) + 1)], 0.45)


def _tail(c): return (" " + esc(c.src)) if c.src else ""


@command("love")
async def love(c): await frames(c, ["🤍", "🩷", "❤️", "🧡", "💛", "💚", "💙", "💜", "💖💖💖", "❤️" + _tail(c)])
@command("fire")
async def fire(c): await frames(c, ["🔥", "🔥🔥", "🔥🔥🔥", "🔥🔥🔥🔥", "🔥" + _tail(c)])
@command("snow")
async def snow(c): await frames(c, ["❄️", "❄️❄️", "❄️☃️❄️", "☃️" + _tail(c)])
@command("boom")
async def boom(c): await frames(c, ["💣", "💣💨", "🧨", "💥", "💥💥💥", "☠️" + _tail(c)])


# ================= утилиты =================
@command("ai")
async def ai(c: Ctx):
    if not cfg.ai_key:
        raise ValueError("AI_API_KEY не задан")
    if not c.src:
        raise ValueError("пустой вопрос")
    async with httpx.AsyncClient(timeout=60) as h:
        r = await h.post("https://api.anthropic.com/v1/messages",
                         headers={"x-api-key": cfg.ai_key, "anthropic-version": "2023-06-01"},
                         json={"model": cfg.ai_model, "max_tokens": 700, "messages": [{"role": "user", "content": c.src}]})
    j = r.json()
    out = "".join(x.get("text", "") for x in j.get("content", [])) or j.get("error", {}).get("message", "пусто")
    await c.edit(f"❓ {esc(c.src)}\n\n🤖 {esc(out)}")


@command("tl")
async def tl(c: Ctx):
    lang, txt = "ru", c.src
    mm = re.match(r"^([a-z]{2}(?:-[a-z]{2})?)(?:\s+([\s\S]+))?$", c.args, re.I)
    if mm and (mm[2] or c.reply):
        lang = mm[1]
        txt = mm[2] or (c.reply.text or c.reply.caption or "")
    async with httpx.AsyncClient(timeout=20) as h:
        r = await h.get("https://translate.googleapis.com/translate_a/single",
                        params={"client": "gtx", "sl": "auto", "tl": lang, "dt": "t", "q": txt})
    await c.edit(esc("".join(x[0] for x in r.json()[0])))


@command("rates")
async def rates(c: Ctx):
    async with httpx.AsyncClient(timeout=20) as h:
        R = (await h.get("https://open.er-api.com/v6/latest/USD")).json()["rates"]
    m = re.match(r"^([\d.,]+)\s*([a-z]{3})\s*(?:to|в|->)?\s*([a-z]{3})$", c.args, re.I)
    if m:
        a, f, t = float(m[1].replace(",", ".")), m[2].upper(), m[3].upper()
        if f not in R or t not in R:
            raise ValueError("неизвестная валюта")
        return await c.edit(f"💱 {a:g} {f} = <b>{a * R[t] / R[f]:.2f} {t}</b>")
    lines = [f"{x}: <b>{R['RUB'] / R[x]:.2f} ₽</b>" for x in ("USD", "EUR", "CNY", "GBP", "UAH", "KZT", "TRY")]
    await c.edit("💱 Курс к рублю\n" + "\n".join(lines))


@command("short")
async def short(c: Ctx):
    async with httpx.AsyncClient(timeout=20) as h:
        r = await h.get("https://is.gd/create.php", params={"format": "simple", "url": c.src})
    await c.edit(esc(r.text))


@command("unshort")
async def unshort(c: Ctx):
    url = c.src.strip()
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as h:
        for _ in range(6):
            r = await h.head(url)
            loc = r.headers.get("location")
            if not loc:
                break
            url = urllib.parse.urljoin(url, loc)
    await c.edit(esc(url))


@command("link")
async def link(c: Ctx):
    t, _, u = c.args.partition("|")
    if not u.strip():
        raise ValueError("формат: .link текст | https://...")
    await c.edit(f'<a href="{esc(u.strip())}">{esc(t.strip())}</a>')


@command("qr")
async def qr(c: Ctx):
    await c.delete()
    await biz.api("sendPhoto", business_connection_id=c.bc, chat_id=c.chat_id,
                  photo="https://api.qrserver.com/v1/create-qr-code/?size=500x500&data=" + urllib.parse.quote(c.src))


@command("geo")
async def geo(c: Ctx):
    m = re.search(r"(-?\d+(?:\.\d+)?)[,\s]+(-?\d+(?:\.\d+)?)", c.args)
    if not m:
        raise ValueError("формат: .geo 55.75 37.61")
    await c.delete()
    await biz.api("sendLocation", business_connection_id=c.bc, chat_id=c.chat_id, latitude=float(m[1]), longitude=float(m[2]))


@command("info")
async def info(c: Ctx):
    u = c.reply.from_user if c.reply and c.reply.from_user else c.m.chat
    name = " ".join(x for x in (u.first_name, getattr(u, "last_name", None)) if x)
    await c.edit("\n".join(x for x in (f"🆔 <code>{u.id}</code>", f"👤 {esc(name)}",
                                       f"🔗 @{u.username}" if getattr(u, "username", None) else "") if x))


@command("del")
async def del_(c: Ctx):
    n = min(100, int(c.args) if c.args.isdigit() else 1)
    rows = await db.select("gs_msgs", {"bc": f"eq.{c.bc}", "chat_id": f"eq.{c.chat_id}", "data->>out": "eq.true",
                                       "order": "msg_id.desc", "limit": n + 1})
    ids = [r["msg_id"] for r in rows] or [c.mid]
    if c.mid not in ids:
        ids.append(c.mid)
    await biz.delete(c.bc, ids)


@command("remind", "remindf")
async def remind(c: Ctx):
    t, _, text = c.args.partition(" ")
    sec = dur(t)
    if not sec or not text.strip():
        raise ValueError("формат: .remind 10m текст (s/m/h/d или с/м/ч/д)")
    to_chat = c.cmd == "remindf"
    await biz.schedule("remind", sec, to="chat" if to_chat else "owner", bc=c.bc, chat_id=c.chat_id,
                       owner_chat=c.conn["user_chat_id"], text=text.strip())
    await c.delete()
    await c.note(f"⏰ Напомню через {esc(t)}: {esc(text.strip())}")


@command("time")
async def time_(c: Ctx):
    if c.args == "off":
        s = c.user.get("settings") or {}
        await U.set_settings(c.user["tg_id"], time_on=False)
        try:
            await biz.set_name(c.bc, s.get("time_first") or c.conn["first_name"], s.get("time_last") or None)
        except Exception:
            pass
        await c.note("🕒 Время в имени выключено")
    else:
        tz = re.sub(r"^on\s*", "", c.args, flags=re.I) or "Europe/Moscow"
        await U.set_settings(c.user["tg_id"], time_on=True, time_tz=tz, time_bc=c.bc, time_cur="",
                             time_first=c.conn["first_name"], time_last=c.conn.get("last_name") or "")
        await c.note(f"🕒 Время в имени включено ({esc(tz)}). Нужно право «менять имя» у бота.")
    await c.delete()


# ================= AFK / авто =================
@command("afk")
async def afk(c: Ctx):
    text = c.args or "Я сейчас не в сети, отвечу позже."
    await U.set_settings(c.user["tg_id"], afk={"text": text, "since": time.time()})
    await c.edit(f"🌙 <b>AFK:</b> {esc(text)}\n⏱ Прошло: 0 мин.")


@command("unafk")
async def unafk(c: Ctx):
    a = (c.user.get("settings") or {}).get("afk")
    await U.set_settings(c.user["tg_id"], afk=None)
    await c.edit(f"✅ Я вернулся{' (был в AFK ' + U.elapsed(a['since']) + ')' if a else ''}")


@command("auto")
async def auto(c: Ctx):
    if not c.args or c.args == "off":
        await c.chat_set(auto=None)
        await c.note("🤖 Автоответчик в этом чате выключен")
    else:
        await c.chat_set(auto=c.args)
        await c.note("🤖 Автоответчик в этом чате включён")
    await c.delete()


# ================= игры =================
BALL = ["Бесспорно", "Предрешено", "Никаких сомнений", "Определённо да", "Скорее всего", "Хорошие перспективы", "Да",
        "Пока не ясно, спроси позже", "Лучше не рассказывать", "Даже не думай", "Мой ответ — нет", "Перспективы не очень", "Весьма сомнительно"]


@command("flip")
async def flip(c): await c.edit(random.choice(["🦅 Орёл", "🪙 Решка"]))
@command("rps")
async def rps(c): await c.edit(random.choice(["🪨 Камень", "✂️ Ножницы", "📄 Бумага"]))
@command("ball")
async def ball(c): await c.edit(f"🎱 {esc(c.src) + chr(10) if c.src else ''}<b>{random.choice(BALL)}</b>")


@command("roll")
async def roll(c: Ctx):
    n = [int(x) for x in re.findall(r"-?\d+", c.args)]
    a, b = (n[0], n[1]) if len(n) >= 2 else (1, n[0] if n else 100)
    await c.edit(f"🎲 {random.randint(min(a, b), max(a, b))}")


@command("revo")
async def revo(c: Ctx):
    await frames(c, ["🔫 Крутим барабан…", "🔫 …", "💥 <b>БАХ!</b> Не повезло" if random.randint(1, 6) == 1 else "😮‍💨 Щёлк. Жив"], 1.0)


@command("duel")
async def duel(c: Ctx):
    o = esc((c.reply.from_user.first_name if c.reply and c.reply.from_user else None) or c.m.chat.first_name or "Соперник")
    await frames(c, [f"🤠 Дуэль: Я vs {o}", "🔫 3…", "🔫 2…", "🔫 1…", f"💥 Победил: <b>{random.choice(['Я', o])}</b>"], 0.9)


# ================= действия с собеседником =================
@command("spam")
async def spam(c: Ctx):
    m = re.match(r"^(\d+)\s+([\s\S]+)$", c.args)
    if not m:
        raise ValueError("формат: .spam 5 текст (максимум 10)")
    await c.delete()
    for _ in range(min(10, int(m[1]))):
        await c.say(esc(m[2]))
        await asyncio.sleep(0.4)


@command("haha")
async def haha(c: Ctx):
    await c.delete()
    for _ in range(min(10, int(c.args) if c.args.isdigit() else 5)):
        await c.say(random.choice(["ахахах", "ХАХАХА", "хахахаха😂", "ахпхахпх", "😂😂😂"]))
        await asyncio.sleep(0.4)


@command("burn")
async def burn(c: Ctx):
    t, _, text = c.args.partition(" ")
    sec = dur(t)
    if not sec or not text.strip():
        raise ValueError("формат: .burn 30 текст (или 1m)")
    await c.edit("🔥 " + esc(text.strip()))
    await biz.schedule("del", sec, bc=c.bc, ids=[c.mid])


@command("bchat")
async def bchat(c: Ctx):
    sec = dur(c.args)
    await c.chat_set(bchat=sec or 0)
    await c.note(f"🧹 Мои сообщения в этом чате удаляются через {esc(c.args)}" if sec else "🧹 Автоудаление в чате выключено")
    await c.delete()


@command("mute")
async def mute(c: Ctx):
    await c.chat_set(muted=True)
    await c.edit("🤫 Собеседник в муте навсегда. Чтобы размутить нажмите кнопку ниже или напишите <code>.unmute</code>",
                 unmute_kb(c.bc, c.chat_id))


@command("unmute", "nomute")
async def unmute(c: Ctx):
    await c.chat_set(muted=False, warns=0)
    await c.edit("😃 Мут снят")


@command("warn")
async def warn(c: Ctx):
    st = await c.chat_get()
    n = int(st.get("warns", 0)) + 1
    if n >= 3:
        await c.chat_set(warns=0, muted=True)
        return await c.edit("⚠️ Предупреждение 3/3\n🤫 Собеседник в муте. Снять: <code>.unmute</code>", unmute_kb(c.bc, c.chat_id))
    await c.chat_set(warns=n)
    await c.edit(f"⚠️ Предупреждение {n}/3" + (f": {esc(c.args)}" if c.args else ""))


async def _toggle(c: Ctx, key: str, on: str, off: str):
    st = await c.chat_get()
    new = not st.get(key)
    await c.chat_set(**{key: new})
    await c.note(on if new else off)
    await c.delete()


@command("wsag")
async def wsag(c): await _toggle(c, "wsag", "🧽 Стикеры и гифки собеседника удаляются", "🧽 Стикеры и гифки снова разрешены")
@command("wbl")
async def wbl(c): await _toggle(c, "wbl", "🧼 Мат собеседника удаляется", "🧼 Фильтр мата выключен")
@command("clone")
async def clone(c): await _toggle(c, "clone", "🪞 Эхо включено: повторяю сообщения собеседника", "🪞 Эхо выключено")
@command("troll")
async def troll(c): await _toggle(c, "troll", "🗿 Троллинг включён", "🗿 Троллинг выключен")


@command("bw")
async def bw(c: Ctx):
    st = await c.chat_get()
    if c.args == "off":
        await c.chat_set(bw=[])
        await c.note("🚫 Список слов очищен")
    elif c.args:
        words = sorted(set(st.get("bw", [])) | {w.lower() for w in c.args.split()})
        await c.chat_set(bw=words)
        await c.note("🚫 Удаляю сообщения со словами: " + ", ".join(esc(w) for w in words))
    else:
        await c.note("🚫 Слова: " + (", ".join(esc(w) for w in st.get("bw", [])) or "—"))
    await c.delete()


@command("imit")
async def imit(c: Ctx):
    acts = {"typing": "typing", "voice": "record_voice", "video": "record_video", "photo": "upload_photo",
            "file": "upload_document", "round": "record_video_note"}
    parts = c.args.split()
    act = acts.get(parts[0] if parts else "typing")
    if not act:
        raise ValueError("варианты: " + ", ".join(acts))
    secs = min(60, int(parts[1])) if len(parts) > 1 and parts[1].isdigit() else 10
    await c.delete()
    for _ in range(max(1, secs // 4)):
        await biz.chat_action(c.bc, c.chat_id, act)
        await asyncio.sleep(4)


@command("help", "cmds")
async def help_(c: Ctx):
    await c.delete()
    await c.note(HELP_CMDS)
