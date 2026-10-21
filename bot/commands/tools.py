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
from ..services import afk_excl, biz
from ..services.logs import audit
from ..services import users as U
from .engine import Ctx, command, dur, esc, REG
from ..texts import HELP_CMDS

from aiogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup as M

# ================= форматирование =================
FMT = {
    "bold": ("<b>", "</b>"), "italic": ("<i>", "</i>"), "mono": ("<code>", "</code>"),
    "line": ("<u>", "</u>"), "crossed": ("<s>", "</s>"), "hidden": ("<tg-spoiler>", "</tg-spoiler>"),
    "quote": ("<blockquote>", "</blockquote>"), "code": ("<pre>", "</pre>"),
}


def _fmt(name, o, c):
    async def fn(ctx: Ctx):
        await ctx.chat_set(fmt=name)  # режим: каждое новое сообщение владельца в чате оформляется так же
        if ctx.src:
            await ctx.edit(o + esc(ctx.src) + c)
        else:
            await ctx.edit(f"✅ Режим <b>.{name}</b> включён в этом чате.\nКаждое твоё новое сообщение будет оформлено так же.\nВыключить: <code>.un{name}</code>")
    return fn


def _unfmt(name):
    async def fn(ctx: Ctx):
        st = await ctx.chat_get()
        if st.get("fmt") == name:
            await ctx.chat_set(fmt=None)
            await ctx.edit(f"✅ Режим <b>.{name}</b> выключен")
        else:
            await ctx.edit(f"ℹ️ Режим <b>.{name}</b> в этом чате не был включён")
    return fn


for _n, (_o, _c) in FMT.items():
    command(_n)(_fmt(_n, _o, _c))
    command("un" + _n)(_unfmt(_n))

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
async def frames(c: Ctx, items, delay=0.4):
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
    await frames(c, [esc(t[:i]) + "▌" for i in range(step, len(t), step)] + [esc(t)], 0.25)


@command("type")
async def type_(c: Ctx):
    w = c.src.split()[:40]
    await frames(c, [esc(" ".join(w[:i])) + (" ▌" if i < len(w) else "") for i in range(1, len(w) + 1)], 0.3)


def _tail(c): return (" " + esc(c.src)) if c.src else ""


@command("love")
async def love(c): await frames(c, ["🤍", "🩷", "❤️", "🧡", "💛", "💚", "💙", "💜", "💖💖💖", "❤️" + _tail(c)])
@command("fire")
async def fire(c): await frames(c, ["🔥", "🔥🔥", "🔥🔥🔥", "🔥🔥🔥🔥", "🔥" + _tail(c)])
@command("snow")
async def snow(c): await frames(c, ["❄️", "❄️❄️", "❄️☃️❄️", "☃️" + _tail(c)])
@command("boom")
async def boom(c): await frames(c, ["💣", "💣💨", "🧨", "💥", "💥💥💥", "☠️" + _tail(c)])



@command("exif")
async def exif_info(c: Ctx):
    """Разбирает EXIF только у фото, на которое владелец ответил командой."""
    r = c.reply
    if not r:
        raise ValueError("ответь командой .exif на фото или файл изображения")
    file_id = None
    if r.photo:
        file_id = r.photo[-1].file_id
    elif r.document and (r.document.mime_type or "").startswith("image/"):
        file_id = r.document.file_id
    if not file_id:
        raise ValueError("в ответе должно быть фото или оригинал изображения как файл")
    try:
        from PIL import Image, ExifTags
    except ImportError:
        raise ValueError("EXIF-модуль не установлен: добавь Pillow в requirements.txt и перезапусти бота")
    import io
    from fractions import Fraction

    f = await c.bot.get_file(file_id)
    buf = io.BytesIO()
    await c.bot.download_file(f.file_path, destination=buf)
    buf.seek(0)
    try:
        image = Image.open(buf)
        exif = image.getexif()
    except Exception as e:
        raise ValueError("не получилось прочитать изображение или его EXIF") from e

    tags = {ExifTags.TAGS.get(k, str(k)): v for k, v in exif.items()}
    lines = ["🧾 <b>EXIF-отчёт</b>", f"Формат: <code>{esc(image.format or 'unknown')}</code>",
             f"Размер: <code>{image.width}×{image.height}</code>"]
    for label, key in (("Устройство", "Model"), ("Производитель", "Make"),
                       ("Дата съёмки", "DateTimeOriginal"), ("Дата файла", "DateTime"),
                       ("ПО камеры", "Software")):
        if tags.get(key):
            value = tags[key]
            if isinstance(value, bytes):
                value = value.decode("utf-8", "replace")
            lines.append(f"{label}: <code>{esc(str(value)[:180])}</code>")

    gps = None
    try:
        raw_gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
        gps = {ExifTags.GPSTAGS.get(k, str(k)): v for k, v in raw_gps.items()}
    except Exception:
        gps = None

    def decimal(coords, ref):
        vals = [float(x) for x in coords]
        result = vals[0] + vals[1] / 60 + vals[2] / 3600
        return -result if str(ref).upper() in ("S", "W") else result

    coords = None
    if gps and gps.get("GPSLatitude") and gps.get("GPSLongitude"):
        try:
            lat = decimal(gps["GPSLatitude"], gps.get("GPSLatitudeRef", "N"))
            lon = decimal(gps["GPSLongitude"], gps.get("GPSLongitudeRef", "E"))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                coords = (lat, lon)
        except Exception:
            coords = None

    if coords:
        lines.append(f"GPS: <code>{coords[0]:.6f}, {coords[1]:.6f}</code>")
        lines.append("Координаты отправлены только владельцу Business-аккаунта в личный чат.")
    else:
        lines.append("GPS: не найдено (в Telegram фото могло быть сжато или геотеги удалены).")
    report = "\n".join(lines)
    await c.note(report)
    if coords:
        await c.bot.send_location(c.conn["user_chat_id"], latitude=coords[0], longitude=coords[1])
    await c.edit("🧾 EXIF-отчёт отправлен в личный чат владельца аккаунта.")


@command("canary")
async def canary(c: Ctx):
    """Создаёт прозрачную ссылку-маячок: фиксируется только факт и время клика."""
    import secrets
    from ..db import db
    from ..config import cfg
    if not cfg.webhook_base:
        raise ValueError("для ссылок-маячков нужен WEBHOOK_BASE_URL/RENDER_EXTERNAL_URL и webhook-режим")
    token = secrets.token_urlsafe(18)
    label = (c.src or "GhostSee click test").strip()[:120]
    await db.insert("gs_canary_tokens", {
        "token": token, "owner_id": c.conn["owner_id"], "label": label
    }, returning=False)
    url = f"{cfg.webhook_base}/canary/{token}"
    await c.note(
        "🪤 <b>Тестовая ссылка-маячок создана</b>\n"
        f"Название: <code>{esc(label)}</code>\n"
        f"Ссылка: <code>{esc(url)}</code>\n\n"
        "При открытии сохраняются только факт и время клика. IP, ОС, провайдер и отпечаток устройства не собираются."
    )
    await c.edit("🪤 Тестовая ссылка создана и отправлена владельцу в личный чат.")


@command("canary_stats")
async def canary_stats(c: Ctx):
    """Показывает события клика по последним созданным маячкам владельца."""
    from ..db import db
    tokens = await db.select("gs_canary_tokens", {
        "owner_id": f"eq.{c.conn['owner_id']}", "order": "created_at.desc", "limit": 10
    })
    if not tokens:
        return await c.edit("Пока нет созданных ссылок-маячков. Используй <code>.canary название</code>.")
    lines = ["🪤 <b>Последние ссылки-маячки</b>"]
    for item in tokens:
        hits = await db.count("gs_canary_events", {"token": f"eq.{item['token']}"})
        lines.append(f"• <b>{esc(item.get('label') or 'Без названия')}</b> — кликов: <b>{hits}</b>")
    await c.edit("\n".join(lines)[:4000])


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


@command("afk_ex")
async def afk_ex(c: Ctx):
    """Добавить собеседника этого чата в исключения .afk. Пишется прямо в диалоге с ним."""
    pid = c.chat_id
    if pid == c.conn["owner_id"]:
        return await c.edit("⚠️ Нельзя добавить себя в исключения")
    ch = c.m.chat
    name = " ".join(x for x in (ch.first_name, ch.last_name) if x) or None
    if ch.username:
        name = f"{name} (@{ch.username})" if name else f"@{ch.username}"
    try:
        added = await afk_excl.add(c.conn["owner_id"], pid, name)
    except Exception as e:
        await audit("error", "afk_ex_failed", c.conn["owner_id"], err=str(e)[:200])
        return await c.edit("⚠️ Не удалось сохранить исключение, попробуй позже")
    await c.edit(("✅ Добавлен в исключения .afk — ему не будет автоответа" if added
                  else "ℹ️ Он уже в исключениях .afk"))


@command("afk_unex")
async def afk_unex(c: Ctx):
    """Убрать собеседника этого чата из исключений .afk."""
    try:
        removed = await afk_excl.remove(c.conn["owner_id"], c.chat_id)
    except Exception as e:
        await audit("error", "afk_unex_failed", c.conn["owner_id"], err=str(e)[:200])
        return await c.edit("⚠️ Не удалось удалить, попробуй позже")
    await c.edit("✅ Удалён из исключений .afk" if removed else "ℹ️ Его нет в исключениях .afk")


@command("unafk")
async def unafk(c: Ctx):
    a = (c.user.get("settings") or {}).get("afk")
    await U.set_settings(c.user["tg_id"], afk=None)
    await c.edit(f"✅ Я вернулся{' (был в AFK ' + U.elapsed(a['since']) + ')' if a else ''}")


# ================= игры =================
BALL = ["Бесспорно", "Предрешено", "Никаких сомнений", "Определённо да", "Скорее всего", "Хорошие перспективы", "Да",
        "Пока не ясно, спроси позже", "Лучше не рассказывать", "Даже не думай", "Мой ответ — нет", "Перспективы не очень", "Весьма сомнительно"]


@command("flip")
async def flip(c): await c.edit(random.choice(["🦅 Орёл", "🪙 Решка"]))
RPS_BEATS = {"камень": "ножницы", "ножницы": "бумага", "бумага": "камень"}
RPS_EMO = {"камень": "🪨", "ножницы": "✂️", "бумага": "📄"}
RPS_ALIAS = {"камень": "камень", "к": "камень", "ножницы": "ножницы", "н": "ножницы", "бумага": "бумага", "б": "бумага"}


@command("rps")
async def rps(c: Ctx):
    me = RPS_ALIAS.get((c.args or "").strip().lower())
    if not me:
        return await c.edit("✂️ Выбери: <code>.rps камень</code> · <code>.rps ножницы</code> · <code>.rps бумага</code>")
    bot_ch = random.choice(list(RPS_BEATS))
    if me == bot_ch:
        res = "🤝 Ничья"
    elif RPS_BEATS[me] == bot_ch:
        res = "🏆 Ты выиграл"
    else:
        res = "🤖 Бот выиграл"
    await c.edit(f"{RPS_EMO[me]} ты · 🤖 {RPS_EMO[bot_ch]} бот\n<b>{res}</b>")


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
MAX_REPEAT = 35
LAUGH_PARTS = ["ХА", "ХВХА", "ХЫ", "ВХА", "ХАХ", "ХВ", "АХ", "ХЫХВ", "ХВХЫ", "ХАХА", "ХВА", "ВХВХ"]


def laugh() -> str:
    """Каждый раз новый смех вроде «ХВХАХАХВХАХВХЫХВХА»."""
    s = "".join(random.choice(LAUGH_PARTS) for _ in range(random.randint(4, 9)))
    return s + random.choice(["😂", "💀", "🤣"]) if random.random() < 0.15 else s


@command("spam")
async def spam(c: Ctx):
    m = re.match(r"^(\d+)\s+([\s\S]+)$", c.args)
    if not m:
        raise ValueError(f"формат: .spam 5 текст (максимум {MAX_REPEAT})")
    await c.delete()
    text = esc(m[2])
    for _ in range(min(MAX_REPEAT, int(m[1]))):  # по одному сообщению, как раньше
        await c.say(text)
        await asyncio.sleep(0.08)


MAX_SPAMG_WORDS = 100


@command("spamg")
async def spamg(c: Ctx):
    """Каждое слово — отдельным сообщением: «.spamg привет как дела» → 3 сообщения."""
    words = (c.args or "").split()
    if not words:
        raise ValueError(f"формат: .spamg привет как дела (максимум {MAX_SPAMG_WORDS} слов)")
    await c.delete()
    for w in words[:MAX_SPAMG_WORDS]:  # порядок важен — шлём по одному, но без лишней паузы
        await c.say(esc(w))
        await asyncio.sleep(0.4)


@command("haha")
async def haha(c: Ctx):
    await c.delete()
    for _ in range(min(MAX_REPEAT, int(c.args) if c.args.isdigit() else 5)):  # по одному сообщению
        await c.say(laugh())
        await asyncio.sleep(0.08)


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
    if sec:
        kb = M(inline_keyboard=[[B(text="Отключить", callback_data=f"unbchat:{c.bc}:{c.chat_id}")]])
        await c.note(f"🧹 Мои сообщения в этом чате удаляются через {esc(c.args)}", kb)
    else:
        await c.note("🧹 Автоудаление в чате выключено")
    await c.delete()

@command("unbchat")
async def unbchat(c: Ctx):
    await c.chat_set(bchat=0)
    await c.note("🧹 Автоудаление в чате выключено")
    await c.delete()


@command("mute")
async def mute(c: Ctx):
    await c.chat_set(muted=True)
    text = (
        "🤫 <b>Собеседник в муте</b>\n"
        "Сообщение восстанавливается не больше 5 раз подряд.\n"
        "⚠️ С юзерботом обход через <code>.nomute</code> не сработает.\n"
        "Размутить: кнопка или <code>.unmute</code>"
    )
    kb = unmute_kb(c.bc, c.chat_id)
    # в личке с ботом — прем-эмодзи; в чате — короткий статус (Telegram режет прем у аккаунтов без Premium)
    try:
        await c.note(text, kb)
    except Exception:
        pass
    try:
        await c.edit("🤫 Собеседник в муте.\nРазмутить: <code>.unmute</code>", kb)
    except Exception:
        await c.say("🤫 Собеседник в муте.\nРазмутить: <code>.unmute</code>", kb)


@command("unmute")
async def unmute(c: Ctx):
    await c.chat_set(muted=False, warns=0)
    try:
        await c.note("✅ Мут снят")
    except Exception:
        pass
    try:
        await c.edit("✅ Мут снят")
    except Exception:
        await c.say("✅ Мут снят")


@command("warn")
async def warn(c: Ctx):
    st = await c.chat_get()
    n = int(st.get("warns", 0)) + 1
    if n >= 3:
        await c.chat_set(warns=0, muted=True)
        return await c.edit("⚠️ Предупреждение 3/3\n🤫 Собеседник в муте. Снять: <code>.unmute</code>", unmute_kb(c.bc, c.chat_id))
    await c.chat_set(warns=n)
    await c.edit(f"⚠️ Предупреждение {n}/3" + (f": {esc(c.args)}" if c.args else ""))


@command("wsag")
async def wsag(c: Ctx):
    await c.chat_set(wsag=True)
    kb = M(inline_keyboard=[[B(text="Отключить", callback_data=f"unwsag:{c.bc}:{c.chat_id}")]])
    await c.note("🧽 Стикеры и гифки собеседника удаляются", kb)
    await c.delete()

@command("unwsag")
async def unwsag(c: Ctx):
    await c.chat_set(wsag=False)
    await c.note("🧽 Стикеры и гифки снова разрешены")
    await c.delete()


@command("wbl")
async def wbl(c: Ctx):
    await c.chat_set(wbl=True)
    kb = M(inline_keyboard=[[B(text="Отключить", callback_data=f"unwbl:{c.bc}:{c.chat_id}")]])
    await c.note("🧼 Мат собеседника удаляется", kb)
    await c.delete()

@command("unwbl")
async def unwbl(c: Ctx):
    await c.chat_set(wbl=False)
    await c.note("🧼 Фильтр мата выключен")
    await c.delete()


@command("clone")
async def clone(c: Ctx):
    await c.chat_set(clone=True)
    kb = M(inline_keyboard=[[B(text="Отключить", callback_data=f"unclone:{c.bc}:{c.chat_id}")]])
    await c.note("🪞 Эхо включено: повторяю сообщения собеседника", kb)
    await c.delete()

@command("unclone")
async def unclone(c: Ctx):
    await c.chat_set(clone=False)
    await c.note("🪞 Эхо выключено")
    await c.delete()


# Новый список троллинга
TROLL = [
    "Твой рот лучше открывать когда туда суют член, уебище.",
    "Соси.",
    "Твой рот нужен исключительно для того, чтобы принимать в него чужие биологические жидкости, пока ты стоишь на коленях посреди грязного коридора, мразь ебаная.",
    "Заткнись.",
    "Твоя тупость превосходит все мыслимые границы человеческого понимания, заставляя каждого нормального человека испытывать физическое отвращение от одного твоего присутствия рядом.",
    "Ты кусок дерьма.",
    "Каждый раз, когда ты открываешь свою пасть, из нее начинает нести такой лютой помойкой и безнадежной тупостью, что хочется надеть противогаз и сжечь этот чат вместе с тобой.",
    "Иди нахуй.",
    "Твой отец горько сожалеет, что в тот злосчастный вечер не прокончил мимо твоей матери, потому что мир получил абсолютное биомусорное недоразумение без единого признака мозгов.",
    "Сдохни.",
    "Ты выглядишь так, будто по твоей дурной башке регулярно прыгал табуном дикий скот, пока у тебя окончательно не вытекли последние остатки серого вещества.",
    "Мразь.",
    "Твое законное место — подрасти на панели, обслуживая дальнобойщиков за пачку дешевых сухариков, потому что на большее твоя никчемная дырявая тушка физически не способна.",
    "Тварь.",
    "У тебя в голове не извилины, а сплошной заброшенный склад протухшего дерьма, в котором копошатся голодные черви твоих убогих и никому не нужных фантазий.",
    "Пошел вон.",
    "Твоя мать по ночам плачет в подушку, вспоминая девять месяцев вынашивания этого ходячего аборта, который теперь сидит в интернете и позорит ее седые волосы.",
    "Конченый.",
    "Твой уровень интеллекта находится где-то на дне выгребной ямы, куда тебя поспешили спустить сразу после рождения, но даже там ты умудрился всплыть и завонять.",
    "Шлюха.",
    "Закрой свой отвратительный рот, от которого разит за версту протухшей селедкой и чужими членами, потому что слушать твой бред выше человеческих сил.",
    "Ублюдок.",
    "Тебя в детстве роняли головой об бетонный пол, причем делали это регулярно, с особым энтузиазмом и до тех пор, пока череп не принял форму твоего убогого характера.",
    "Чмо.",
    "Твои пальцы дрожащими судорогами набирают этот бессмысленный высер только потому, что в реальной жизни тебе давным-давно сломали бы челюсть за такие слова.",
    "Ничтожество.",
    "Посмотри на себя в зеркало и осознай, что ты — биологический тупик, ошибка природы и ходячее доказательство того, что презервативы иногда рвутся не зря.",
    "Свинья.",
    "Твое мнение ценится ровно столько же, сколько использованная туалетная бумага, валяющаяся возле общественного туалета на вокзале.",
    "Идиот.",
    "Каждая секунда твоего существования в этом мире — это чистое оскорбление для всех окружающих живых существ, включая дворовых бродячих собак.",
    "Днище.",
    "Ты даже не представляешь, насколько глубоко всем наплевать на твои высеры, потому что ты — пустое место с ником, кусок биомассы без лица и имени.",
    "Пидорас.",
    "Убирайся нахуй отсюда, пока тебе не разорвали пасть за излишнюю разговорчивость и полное отсутствие хотя бы зачатков мозговой активности.",
    "Мразь тупорылая.",
    "Твоя жизнь — это унылая череда унижений, побоев за гаражами и попыток хоть как-то самоутвердиться в интернете, потому что в реальности ты обычная половая тряпка.",
    "Закрой хайло, биомусор.",
    "Ты выродок больного сифилисом бомжа.",
    "Твоя рожа просит кирпича.",
    "Сгинь, недобитый аборт.",
    "Твое мнение спросить забыли, кусок мяса.",
    "Пасть порву, моргалы выколю.",
    "Иди поплачь в углу, омежка.",
    "Твой батя зря потратил на тебя презерватив.",
    "Ты ошибка эволюции.",
    "Глаза б мои тебя не видели, мразь.",
    "Завали ебало, от тебя смердит.",
    "Твоя голова забита калом.",
    "Уебывай отсюда пока живой.",
    "Ты ходячий парадокс: мозг размером с горошину, а самомнения на целый завод.",
    "Твои тексты вызывают кровотечение из глаз и непреодолимое желание проблеваться.",
    "Слышь, ослиное ты копыто, захлопни свою мусорку.",
    "Каждый раз, когда ты открываешь рот, в мире умирает один дельфин от стыда за человечество.",
    "Твоя мамаша знала, кого рожает — будущую половую тряпку всего района.",
    "Иди в будку, пёс шелудивый.",
    "Твой интеллектуальный багаж умещается в спичечный коробок, да и тот наполовину пустой.",
    "От тебя толку меньше, чем от мертвого грузчика на разгрузке вагонов с ватой.",
    "Тебе впору не в чатах сидеть, а бутылки собирать по теплотрассам, утырок.",
    "Твое присутствие здесь — чистой воды вредительство экологии планеты.",
    "Заткнись, животное бессловесное.",
    "Твоя харизма равна нулю, а дебильность стремится к бесконечности.",
    "Иди учебники отнеси обратно в школу, хотя тебе и десять классов не помогут.",
    "Ты выглядишь как жертва неудачного эксперимента по клонированию свиней.",
    "Твой рот — общая парковка для чужих органов.",
    "Кончай нести этот бред шизофреника, тошно смотреть.",
    "Твое погоняло в зоне будет «Швабра», не сомневайся.",
    "Идиот кусок, тебя учили думать или только жрать и сереть?",
    "Твоя тупость фонит так сильно, что дозиметр зашкаливает.",
    "Завали хлебало, выкидыш.",
    "Твой мозг ссохся до размеров грецкого ореха от бесконечного просмотра помоек.",
    "Мразь конченая, вали в закат.",
    "Твой ковыряющийся в носу пацанчик-сосед умнее тебя в три раза.",
    "Иди проспись, алкаш недобитый.",
    "Твое лицо излучает такую концентрацию дебилизма, что впору диссертации писать.",
    "Забейся под плинтус и не отсвечивай, урод.",
    "Твои пальцы пишут то, за что твоя жопа будет горько отвечать.",
    "Сдохни от зависти, моллюск безмозглый.",
    "Твой словесный поток — это диагноз для психиатра высшей категории.",
    "Иди на хутор бабочек ловить, долбоеб.",
    "Твое мнение никому не уперлось, кроме твоих воображаемых друзей.",
    "Заглоти и сиди тихо, убогий.",
    "Твой уровень развития застрял на стадии инфузории-туфельки.",
    "Мразь поганая, чтоб ты захлебнулся собственной желчью.",
    "Твой батя плачет водопадом, глядя на это недоразумение.",
    "Иди подмойся, от тебя разит за километр.",
    "Твое существование — оскорбление для всех здравомыслящих людей.",
    "Закрой варежку, олень.",
    "Твой мозг заплыл жиром и тупостью окончательно.",
    "Свободен, петушок комнатный.",
    "Твоя мать должна была сделать вакуум еще на первой неделе.",
    "Иди мусор вынеси, может за умного сойдешь.",
    "Твое словесное недержание лечится только лоботомией ржавой лопатой.",
    "Заткнись нахуй, жертва ЕГЭ.",
    "Твой уровень IQ ниже комнатной температуры в антарктическом морге.",
    "Мразь тупоголовая, сгинь с глаз долой.",
    "Твой рот — не помойка, но ты упорно продолжаешь в него сереть словами.",
    "Иди лечись, шизоид ебаный.",
    "Твое лицо — прямое доказательство того, что обезьяны эволюционировали обратно.",
    "Завали едало, уебок.",
    "Твой котелок не варит вообще никак, пусто там.",
    "Сдохни в канаве, биомусор.",
    "Твоя глупость оскорбляет законы физики.",
    "Иди нахуй, долбоящер.",
    "Твое мнение — плевок в вечность, который никому не интересен.",
    "Заткни пасть, шавка помойная.",
    "Твой мозг работает со скрипом ржавой телеги.",
    "Мразь портовая, вали отсюда.",
    "Твой батя — сапожник, а ты — сапог тупой.",
    "Иди сдохни под забором, ничтожество.",
    "Твое присутствие здесь токсичнее чернобыльского реактора.",
    "Заглоти язык, выблядок.",
    "Твой уровень аргументации держится на честном слове и соплях.",
    "Свободен, ничтожный клоун.",
    "Твоя жизнь — сплошной баг матрицы.",
    "Иди в пень, дурак кусок.",
    "Твое лицо просит кирпича без регистрации.",
    "Завали будку, псина.",
    "Твой разум покинул чат навсегда.",
    "Мразь сутулая, исчезни.",
    "Твой словесный понос утомил планету.",
    "Иди проспись, синяк.",
    "Твое мнение отправлено в унитаз.",
    "Заткнись, убогий.",
    "Твой мозг пропил еще твой дед.",
    "Сдохни молча, шваль.",
    "Твоя тупость легендарна в узких кругах дебилов.",
    "Иди нахер, утырок.",
    "Твое лицо — боль пластического хирурга.",
    "Завали хлебало, чучело.",
    "Твой уровень жизни — дно выгребной ямы.",
    "Мразь уличная, василек.",
    "Твой батя разочарован.",
    "Иди лесом, дятел.",
    "Твое существование бессмысленно.",
    "Заткнись нахрен.",
    "Твой мозг — пустота.",
    "Свободен нахуй."
]


@command("troll")
async def troll(c: Ctx):
    await c.chat_set(troll=True)
    kb = M(inline_keyboard=[[B(text="Отключить", callback_data=f"untroll:{c.bc}:{c.chat_id}")]])
    await c.note("🧌 Режим троллинга включен", kb)
    await c.delete()

@command("untroll")
async def untroll(c: Ctx):
    await c.chat_set(troll=False)
    await c.note("🧌 Режим троллинга отключен")
    await c.delete()


@command("nomute")
async def nomute(c: Ctx):
    await c.chat_set(nomute=True)
    kb = M(inline_keyboard=[[B(text="Отключить", callback_data=f"unnomute:{c.bc}:{c.chat_id}")]])
    await c.note("🔓 Обход мута включён (лимит 5 восстановлений подряд).\nЕсли у собеседника юзербот — обход не сработает.", kb)
    await c.delete()

@command("unnomute")
async def unnomute(c: Ctx):
    await c.chat_set(nomute=False)
    await c.note("🔓 Обход мута выключен")
    await c.delete()


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


@command("dox")
async def dox(c: Ctx):
    """Шуточный «пробив»: ничего не ищет, просто анимация и розыгрыш."""
    u = c.reply.from_user if c.reply and c.reply.from_user else c.m.chat
    handle = f"@{u.username}" if getattr(u, "username", None) else esc(u.first_name or "аноним")
    spoil = lambda t: f"<tg-spoiler>{t}</tg-spoiler>"
    bar = lambda n: "▰" * n + "▱" * (10 - n)
    await frames(c, [
        f"🔎 <b>Подключаюсь к базе…</b>\n{bar(1)} 10%",
        f"🛰 <b>Ищу {handle}…</b>\n{bar(3)} 30%",
        f"📡 <b>Перехватываю данные…</b>\n{bar(5)} 50%",
        f"🧬 <b>Расшифровываю…</b>\n{bar(7)} 70%",
        f"🗂 <b>Собираю досье…</b>\n{bar(9)} 90%",
        f"✅ <b>Пробив завершён</b>\n{bar(10)} 100%",
    ], 0.8)
    await c.edit(
        f"📂 <b>Информация о {handle} | <code>{u.id}</code></b>\n\n"
        f"🌍 Страна: {spoil('сам(а) знаешь')}\n"
        f"🏙 Город: {spoil('сам(а) знаешь')}\n"
        f"📱 Номер: {spoil('сам(а) знаешь')}\n"
        f"👩 Номер мамы: {spoil('сам(а) знаешь')}\n"
        f"🛣 Улица: {spoil('сам(а) знаешь куда ехать :)')}\n"
        f"🚪 Квартира: {spoil('сам(а) знаешь')}\n\n"
        "━━━━━━━━━━━━━━\n👻 <b>Вы были пробиты ghostseebot</b> 👻"
    )


@command("cum")
async def cum(c: Ctx):
    await frames(c, [
        "8=D",
        "8==D",
        "8===D",
        "8====D",
        "8=====D",
        "8=====D✊",
        "8====✊=D",
        "8===✊==D",
        "8==✊===D",
        "8=✊====D",
        "8✊=====D💦",
        "8=✊====D💦",
        "8==✊===D💦",
        "8===✊==D💦",
        "8====✊=D💦😫",
        "8=====D💦💦😩",
        "8=====D💦💦💦🥵",
        "8=====D💦💦💦💦💀",
    ], 0.45)
    if c.src:
        await asyncio.sleep(0.5)
        await c.edit(esc(c.src))


# ================= НОВЫЕ КОМАНДЫ =================

@command("antispam")
async def antispam(c: Ctx):
    await c.chat_set(antispam=True)
    kb = M(inline_keyboard=[[B(text="Отключить", callback_data=f"unantispam:{c.bc}:{c.chat_id}")]])
    await c.note("🛡 Антиспам включен: удаляю сообщения с множеством ссылок, капсом и повторами", kb)
    await c.delete()

@command("unantispam")
async def unantispam(c: Ctx):
    await c.chat_set(antispam=False)
    await c.note("🛡 Антиспам выключен")
    await c.delete()


@command("autoreply")
async def autoreply(c: Ctx):
    if not c.args or c.args == "off":
        await c.chat_set(autoreply=None)
        await c.note("🤖 Автоответчик выключен")
        return await c.delete()
    # Формат: .autoreply фраза1 | фраза2 | фраза3
    phrases = [p.strip() for p in c.args.split("|") if p.strip()]
    if not phrases:
        raise ValueError("формат: .autoreply фраза1 | фраза2 | фраза3 (или .autoreply off)")
    await c.chat_set(autoreply=phrases)
    kb = M(inline_keyboard=[[B(text="Отключить", callback_data=f"unautoreply:{c.bc}:{c.chat_id}")]])
    await c.note(f"🤖 Автоответчик включен: {len(phrases)} фраз", kb)
    await c.delete()

@command("unautoreply")
async def unautoreply(c: Ctx):
    await c.chat_set(autoreply=None)
    await c.note("🤖 Автоответчик выключен")
    await c.delete()


@command("react")
async def react(c: Ctx):
    await c.chat_set(react=True)
    kb = M(inline_keyboard=[[B(text="Отключить", callback_data=f"unreact:{c.bc}:{c.chat_id}")]])
    await c.note("❤️ Автореакция включена: буду ставить ❤️ на каждое сообщение собеседника", kb)
    await c.delete()

@command("unreact")
async def unreact(c: Ctx):
    await c.chat_set(react=False)
    await c.note("❤️ Автореакция выключена")
    await c.delete()


@command("translate")
async def translate(c: Ctx):
    await c.chat_set(translate=True)
    kb = M(inline_keyboard=[[B(text="Отключить", callback_data=f"untranslate:{c.bc}:{c.chat_id}")]])
    await c.note("🌐 Автоперевод включен: иностранные сообщения будут переводиться на русский", kb)
    await c.delete()

@command("untranslate")
async def untranslate(c: Ctx):
    await c.chat_set(translate=False)
    await c.note("🌐 Автоперевод выключен")
    await c.delete()


@command("cold")
async def cold(c: Ctx):
    await c.chat_set(cold=True)
    kb = M(inline_keyboard=[[B(text="Отключить", callback_data=f"uncold:{c.bc}:{c.chat_id}")]])
    await c.note("🧊 Режим «холод» включен: отвечаю на каждое сообщение собеседника ледяными фразами", kb)
    await c.delete()

@command("uncold")
async def uncold(c: Ctx):
    await c.chat_set(cold=False)
    await c.note("🧊 Режим «холод» выключен")
    await c.delete()


# ========== ДОП. РАБОЧИЕ КОМАНДЫ (сетка Traceon) ==========

@command("echo")
async def echo_cmd(c: Ctx):
    t = c.src or "..."
    await c.edit(esc(t))


@command("emojis", "emoji")
async def emojis_cmd(c: Ctx):
    base = c.src or "👻"
    await c.edit(" ".join(base[i % len(base)] for i in range(min(40, max(8, len(base) * 4)))))


@command("rp")
async def rp_cmd(c: Ctx):
    act = c.args or "смотрит в пустоту"
    name = esc((c.m.from_user.first_name if c.m.from_user else "Кто-то") or "Кто-то")
    await c.edit(f"🎭 <b>{name}</b> {esc(act)}")


@command("typing")
async def typing_cmd(c: Ctx):
    sec = 5
    if c.args.isdigit():
        sec = max(1, min(30, int(c.args)))
    await c.edit(f"⌨️ Печатаю {sec} сек…")
    try:
        await c.bot.send_chat_action(c.chat_id, action="typing", business_connection_id=c.bc)
    except Exception:
        pass
    import asyncio
    await asyncio.sleep(sec)
    await c.edit("⌨️ Готово")


@command("bomb")
async def bomb_cmd(c: Ctx):
    """Самоудаление сообщения через N сек. .bomb 10 текст"""
    import asyncio
    parts = c.args.split(maxsplit=1)
    sec = 5
    text = c.src
    if parts and parts[0].isdigit():
        sec = max(1, min(120, int(parts[0])))
        text = parts[1] if len(parts) > 1 else (c.reply.text if c.reply else "💣")
    text = text or "💣"
    await c.edit(f"💣 {esc(text)}\n<i>удалится через {sec}с</i>")
    await asyncio.sleep(sec)
    try:
        await c.delete()
    except Exception:
        pass


@command("timer")
async def timer_cmd(c: Ctx):
    """Таймер. .timer 30 [текст]"""
    import asyncio
    parts = c.args.split(maxsplit=1)
    if not parts or not parts[0].isdigit():
        return await c.edit("⏱ Использование: <code>.timer 30 [текст]</code>")
    sec = max(1, min(600, int(parts[0])))
    label = parts[1] if len(parts) > 1 else "время вышло"
    await c.edit(f"⏱ Таймер <b>{sec}с</b>…")
    await asyncio.sleep(sec)
    await c.say(f"⏱ <b>Таймер:</b> {esc(label)}")


@command("check")
async def check_cmd(c: Ctx):
    t = (c.args or c.src or "").strip()
    if not t:
        t0 = time.perf_counter()
        await c.edit("🏓 Проверяю…")
        ms = int((time.perf_counter() - t0) * 1000)
        from .engine import lat_summary
        return await c.edit(f"🏓 <b>Пинг</b>: ответ Telegram за <b>{ms} мс</b>\n⏱ Задержка команд: {lat_summary()}\n\nПроверка пользователя: <code>.check @user</code>")
    t = t.lstrip("@")
    if t.startswith("http"):
        await c.edit(f"🔗 Ссылка: <code>{esc(t)}</code>\nПроверь вручную — автоматический скан ограничен.")
    else:
        await c.edit(f"👤 Цель: <code>@{esc(t)}</code>\nID/статус смотри через <code>.info</code> ответом на сообщение.")


@command("save")
async def save_cmd(c: Ctx):
    r = c.reply
    if not r:
        return await c.edit("💾 Ответь на сообщение, которое нужно сохранить")
    body = r.text or r.caption or "(медиа)"
    await c.note(f"💾 <b>Сохранено</b>\n\n{esc(body)[:3500]}")
    await c.edit("💾 Отправил тебе в личку с ботом")


@command("wth")
async def wth_cmd(c: Ctx):
    r = c.reply
    if not r:
        return await c.edit("❓ Ответь на сообщение")
    bits = [f"ID: <code>{r.message_id}</code>"]
    if r.from_user:
        bits.append(f"От: <code>{r.from_user.id}</code> @{esc(r.from_user.username or '—')}")
    bits.append(f"Тип: text={bool(r.text)} media={bool(r.photo or r.video or r.document or r.sticker)}")
    await c.edit("❓ <b>Что это</b>\n" + "\n".join(bits))


@command("core")
async def core_cmd(c: Ctx):
    st = await c.chat_get()
    await c.edit(
        "🧬 <b>Core</b>\n"
        f"muted: {st.get('muted')}\n"
        f"nomute: {st.get('nomute')}\n"
        f"afk: {st.get('afk')}\n"
        f"warns: {st.get('warns', 0)}"
    )


@command("calc")
async def calc_cmd(c: Ctx):
    expr = (c.args or c.src or "").strip()
    if not expr:
        return await c.edit("🧮 <code>.calc 2+2*3</code>")
    allowed = set("0123456789+-*/().% eE")
    if not all(ch in allowed or ch.isspace() for ch in expr):
        return await c.edit("🧮 Только числа и + - * / ( )")
    try:
        val = eval(expr, {"__builtins__": {}}, {})  # noqa: S307 — ограниченный алфавит
        await c.edit(f"🧮 <code>{esc(expr)}</code> = <b>{val}</b>")
    except Exception:
        await c.edit("🧮 Ошибка выражения")


@command("encrypt")
async def encrypt_cmd(c: Ctx):
    t = c.src
    if not t:
        return await c.edit("🔐 <code>.encrypt текст</code>")
    # простой сдвиг
    out = []
    for ch in t:
        if "a" <= ch <= "z":
            out.append(chr((ord(ch) - 97 + 3) % 26 + 97))
        elif "A" <= ch <= "Z":
            out.append(chr((ord(ch) - 65 + 3) % 26 + 65))
        elif "а" <= ch <= "я":
            out.append(chr((ord(ch) - 1072 + 3) % 32 + 1072))
        elif "А" <= ch <= "Я":
            out.append(chr((ord(ch) - 1040 + 3) % 32 + 1040))
        else:
            out.append(ch)
    await c.edit(f"🔐 <code>{esc(''.join(out))}</code>\n<i>шифр Цезаря +3 · .decrypt</i>")


@command("decrypt")
async def decrypt_cmd(c: Ctx):
    t = c.src
    if not t:
        return await c.edit("🔓 <code>.decrypt текст</code>")
    out = []
    for ch in t:
        if "a" <= ch <= "z":
            out.append(chr((ord(ch) - 97 - 3) % 26 + 97))
        elif "A" <= ch <= "Z":
            out.append(chr((ord(ch) - 65 - 3) % 26 + 65))
        elif "а" <= ch <= "я":
            out.append(chr((ord(ch) - 1072 - 3) % 32 + 1072))
        elif "А" <= ch <= "Я":
            out.append(chr((ord(ch) - 1040 - 3) % 32 + 1040))
        else:
            out.append(ch)
    await c.edit(f"🔓 <code>{esc(''.join(out))}</code>")


@command("date")
async def date_cmd(c: Ctx):
    import datetime as dt
    now = dt.datetime.now()
    await c.edit(f"📅 <b>{now.strftime('%d.%m.%Y')}</b>\n🕒 {now.strftime('%H:%M:%S')}\n{now.strftime('%A')}")


@command("links")
async def links_cmd(c: Ctx):
    import re as _re
    t = c.src or ""
    found = _re.findall(r"https?://[^\s]+", t)
    if not found:
        return await c.edit("🔗 Ссылок не найдено. Пришли текст или reply.")
    await c.edit("🔗 Найдено:\n" + "\n".join(f"• {esc(u)}" for u in found[:20]))


@command("safety")
async def safety_cmd(c: Ctx):
    t = (c.args or c.src or "").strip()
    if not t:
        return await c.edit("🛡 <code>.safety url</code>")
    bad = any(x in t.lower() for x in ("bit.ly", "tinyurl", "t.cn", "login", "password", "wallet", "seed"))
    await c.edit("🛡 " + ("⚠️ Похоже на фишинг/сокращатель — осторожно" if bad else "✅ Явных красных флагов нет (это не полный аудит)"))


@command("stats")
async def stats_cmd(c: Ctx):
    st = await c.chat_get()
    await c.edit(
        "📊 <b>Стата чата</b>\n"
        f"muted: {bool(st.get('muted'))}\n"
        f"warns: {st.get('warns', 0)}\n"
        f"bw words: {len(st.get('bw') or [])}\n"
        f"nomute: {bool(st.get('nomute'))}"
    )


_TTT_LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


def _ttt_winner(b):
    for x, y, z in _TTT_LINES:
        if b[x] and b[x] == b[y] == b[z]:
            return b[x]
    return None


def _ttt_bot_move(b):
    """Бот: сначала выигрывает, если может, затем блокирует, затем центр, углы, остальное."""
    empty = [i for i, v in enumerate(b) if not v]
    for mark in ("O", "X"):
        for i in empty:
            t = list(b)
            t[i] = mark
            if _ttt_winner(t) == mark:
                return i
    if 4 in empty:
        return 4
    for i in (0, 2, 6, 8):
        if i in empty:
            return i
    return empty[0]


def _ttt_render(b, status):
    sym = {"X": "❌", "O": "⭕"}
    cells = [sym.get(v, str(i + 1)) for i, v in enumerate(b)]
    rows = ["  ".join(cells[r * 3:r * 3 + 3]) for r in range(3)]
    return "🎮 <b>Крестики-нолики</b>\n\n" + "\n".join(rows) + "\n\n" + status


@command("ttt")
async def ttt_cmd(c: Ctx):
    arg = (c.args or "").strip()
    st = await c.chat_get()
    g = st.get("ttt")
    if not arg.isdigit():  # новая игра: это сообщение становится доской
        b = [""] * 9
        await c.chat_set(ttt={"b": b, "mid": c.mid, "over": False})
        return await c.edit(_ttt_render(b, "Твой ход: <code>.ttt НОМЕР</code> (1–9)"))
    if not g or g.get("over"):
        return await c.edit("Сначала начни игру: <code>.ttt</code>")
    n = int(arg)
    if not 1 <= n <= 9:
        return await c.note("Номер клетки — от 1 до 9")
    b = list(g["b"])
    if b[n - 1]:
        return await c.note(f"Клетка {n} уже занята")
    b[n - 1] = "X"
    over = False
    if _ttt_winner(b):
        status, over = "🏆 Ты победил!", True
    elif all(b):
        status, over = "🤝 Ничья!", True
    else:
        b[_ttt_bot_move(b)] = "O"
        if _ttt_winner(b):
            status, over = "🤖 Победа бота!", True
        elif all(b):
            status, over = "🤝 Ничья!", True
        else:
            status = "Твой ход: <code>.ttt НОМЕР</code> (1–9)"
    await c.chat_set(ttt={"b": b, "mid": g["mid"], "over": over})
    await c.delete()
    await biz.edit(c.bc, c.chat_id, g["mid"],
                   _ttt_render(b, status + ("\n\nНовая игра: <code>.ttt</code>" if over else "")))


@command("wordle")
async def wordle_cmd(c: Ctx):
    import random
    words = ["ghost", "trace", "night", "smoke", "blade", "cyber", "pixel", "shade"]
    w = random.choice(words)
    await c.chat_set(wordle=w, wordle_tries=0)
    await c.edit("📗 Wordle: слово из 5 букв (en). Пиши <code>.guess слово</code>")


@command("guess")
async def guess_cmd(c: Ctx):
    st = await c.chat_get()
    w = st.get("wordle")
    if not w:
        return await c.edit("Сначала <code>.wordle</code>")
    g = (c.args or "").strip().lower()
    if len(g) != 5:
        return await c.edit("Ровно 5 букв")
    tries = int(st.get("wordle_tries") or 0) + 1
    res = []
    for i, ch in enumerate(g):
        if i < len(w) and ch == w[i]:
            res.append(f"🟩{ch}")
        elif ch in w:
            res.append(f"🟨{ch}")
        else:
            res.append(f"⬛{ch}")
    await c.chat_set(wordle_tries=tries)
    msg = " ".join(res) + f"\nПопытка {tries}/6"
    if g == w:
        await c.chat_set(wordle=None)
        msg += "\n✅ Угадал!"
    elif tries >= 6:
        await c.chat_set(wordle=None)
        msg += f"\n❌ Слово было <b>{w}</b>"
    await c.edit(msg)


_MS_SIZE, _MS_MINES = 5, 5
_MS_NUM = ["🟩", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]


def _ms_adj(idx: int, mines) -> int:
    r, c = divmod(idx, _MS_SIZE)
    return sum(1 for dr in (-1, 0, 1) for dc in (-1, 0, 1)
               if (dr or dc) and 0 <= r + dr < _MS_SIZE and 0 <= c + dc < _MS_SIZE
               and (r + dr) * _MS_SIZE + (c + dc) in mines)


def _ms_open(g: dict, idx: int):
    """Открыть клетку; если вокруг нет мин — открыть соседей (как в сапёре)."""
    mines, opened, todo = set(g["mines"]), set(g["open"]), [idx]
    while todo:
        i = todo.pop()
        if i in opened or i in mines:
            continue
        opened.add(i)
        if _ms_adj(i, mines) == 0:
            r, c = divmod(i, _MS_SIZE)
            todo += [(r + dr) * _MS_SIZE + (c + dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                     if (dr or dc) and 0 <= r + dr < _MS_SIZE and 0 <= c + dc < _MS_SIZE]
    g["open"] = sorted(opened)


def _ms_render(g: dict, status: str) -> str:
    mines, opened = set(g["mines"]), set(g["open"])
    lines = ["  " + " ".join("ABCDE")]
    for r in range(_MS_SIZE):
        cells = []
        for col in range(_MS_SIZE):
            i = r * _MS_SIZE + col
            if i == g.get("hit"):
                cells.append("💥")
            elif g["over"] and i in mines:
                cells.append("💣")
            elif i in opened:
                cells.append(_MS_NUM[_ms_adj(i, mines)])
            else:
                cells.append("⬜")
        lines.append(f"{r + 1} " + "".join(cells))
    return "💣 <b>Сапёр 5×5</b> · мин: " + str(_MS_MINES) + "\n" + "\n".join(lines) + f"\n\n{status}"


def _ms_parse(arg: str):
    m = re.fullmatch(r"([a-eA-E])\s*([1-5])", arg.strip())
    if m:
        return (int(m[2]) - 1) * _MS_SIZE + (ord(m[1].lower()) - 97)
    return None


@command("ms")
async def ms_cmd(c: Ctx):
    arg = (c.args or "").strip()
    if not arg:  # новая игра
        g = {"mines": random.sample(range(_MS_SIZE * _MS_SIZE), _MS_MINES), "open": [], "hit": None,
             "over": False, "mid": c.mid}
        await c.chat_set(ms=g)
        return await c.edit(_ms_render(g, "Открой клетку: <code>.ms B3</code> (буква — колонка, цифра — строка)"))
    st = await c.chat_get()
    g = st.get("ms")
    if not g or g.get("over"):
        return await c.note("Начни новую игру: <code>.ms</code>")
    idx = _ms_parse(arg)
    if idx is None:
        return await c.note("Клетка вида <code>.ms B3</code> (A–E и 1–5)")
    if idx in g["open"]:
        return await c.note("Эта клетка уже открыта")
    if idx in set(g["mines"]):
        g["hit"], g["over"] = idx, True
        status = "💥 Подрыв! Игра окончена. Новая: <code>.ms</code>"
    else:
        _ms_open(g, idx)
        if len(g["open"]) == _MS_SIZE * _MS_SIZE - _MS_MINES:
            g["over"] = True
            status = "🎉 Победа! Все безопасные клетки открыты. Новая: <code>.ms</code>"
        else:
            status = "Открой клетку: <code>.ms B3</code>"
    await c.chat_set(ms=g)
    await c.delete()
    await biz.edit(c.bc, c.chat_id, g["mid"], _ms_render(g, status))


# алиасы сетки
@command("tr")
async def tr_alias(c: Ctx):
    await tl(c)

@command("ex", "meta")
async def ex_alias(c: Ctx):
    await exif_info(c)

@command("rul")
async def rul_alias(c: Ctx):
    await revo(c)

@command("mb")
async def mb_alias(c: Ctx):
    await ball(c)

@command("rd")
async def rd_alias(c: Ctx):
    await roll(c)

async def fake_react(c: Ctx):
    """Макет реакции в личке владельца. Настоящую реакцию собеседник не увидит."""
    raw = (c.args or "").split()
    emoji = raw[0][:8] if raw else "❤️"
    target = c.reply
    preview = (target.text or target.caption or "") if target else ""
    await c.delete()
    body = f"«{esc(preview[:200])}»" if preview else "<i>(без текста)</i>"
    await c.note(f"{esc(emoji)} <i>макет реакции</i>\n{body}\n\n"
                 "<i>Это только макет в личке: реакция никому не ставится и собеседник её не видит.</i>")


@command("fake_react")
async def fake_react_cmd(c: Ctx):
    await fake_react(c)


@command("fake")
async def fake_alias(c: Ctx):
    await fake_react(c)


@command("last")
async def last_cmd(c: Ctx):
    st = await c.chat_get()
    last = st.get("last_deleted")
    if not last:
        return await c.edit("🗑 В этом чате ещё нет сохранённых удалений")
    body = last.get("text") or last.get("caption") or "(медиа)"
    when = last.get("time") or "—"
    name = last.get("name") or "—"
    await c.edit(f"🗑 <b>Последнее удалённое</b>\n{when} · {esc(str(name))}\n\n{esc(str(body))[:3500]}")


@command("promo")
async def promo_cmd(c: Ctx):
    from ..services import promos
    from ..services import users as U
    code = (c.args or "").strip()
    if not code:
        return await c.edit("🎟 <code>.promo КОД</code>")
    res, days = await promos.redeem(c.bot, c.conn["owner_id"], code)
    if res == "ok":
        await U.set_settings(c.conn["owner_id"], last_promo=code.upper())
        return await c.edit(await promos.success_text(c.conn["owner_id"], days))
    await c.edit(promos.ERROR_TEXT.get(res, promos.ERROR_TEXT["error"]))


@command("freeze")
async def freeze_cmd(c: Ctx):
    """Заморозка: бот полностью выключен на N дней (до 30). Дни подписки не добавляются, а ставятся на паузу."""
    from ..services import users as U
    days = 7
    if c.args and c.args.split()[0].isdigit():
        days = max(1, min(30, int(c.args.split()[0])))
    u = await U.get_user(c.conn["owner_id"], fresh=True) or {}
    if U.is_frozen(u):
        return await c.edit("❄️ Бот уже заморожен. Снять — кнопкой в сообщении выше.")
    until = await U.start_freeze(c.conn["owner_id"], days)
    kb = M(inline_keyboard=[[B(text="❄️ Разморозить", callback_data="unfreeze")]])
    await c.note(f"❄️ <b>Бот заморожен</b> на {days} дн. (до {until.strftime('%d.%m %H:%M')} МСК)\n"
                 "Пока заморожено: команды не работают, удалённые и изменённые сообщения не присылаются.\n"
                 "Дни подписки на паузе — после разморозки они вернутся.", kb=kb)
    await c.delete()


@command("unfreeze")
async def unfreeze_cmd(c: Ctx):
    """Работает только когда заморозки нет (во время заморозки команды не выполняются — снимай кнопкой)."""
    from ..services import users as U
    u = await U.get_user(c.conn["owner_id"], fresh=True) or {}
    if not U.is_frozen(u):
        return await c.edit("❄️ Заморозки нет")
    await U.end_freeze(c.conn["owner_id"])
    await c.edit("✅ Заморозка снята — бот снова работает")
