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


@command("fake_react", "mockreact")
async def fake_react(c: Ctx):
    """Отправляет владельцу явно помеченный макет реакции, не подделывая событие Telegram."""
    parts = (c.args or "❤️").split(maxsplit=1)
    emoji = parts[0]
    allowed = {"❤️", "🔥", "😂", "👍", "👎", "😮", "😢", "🎉", "🤡", "💀", "🤔", "👀"}
    if emoji not in allowed:
        raise ValueError("эмодзи: ❤️ 🔥 😂 👍 👎 😮 😢 🎉 🤡 💀 🤔 👀")
    note = parts[1] if len(parts) > 1 else ""
    await c.note(
        "🎭 <b>Макет реакции GhostSee</b>\n"
        f"Реакция: {emoji}\n"
        f"{('Комментарий: ' + esc(note)) if note else ''}\n\n"
        "<i>Это демонстрация в личке владельца, не настоящая реакция Telegram и не уведомление от собеседника.</i>"
    )
    await c.edit("🎭 Макет реакции отправлен владельцу в личку. Настоящую реакцию это не подделывает.")


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
MAX_REPEAT = 25
LAUGH_PARTS = ["ХА", "ХВХА", "ХЫ", "ВХА", "ХАХ", "ХВ", "АХ", "ХЫХВ", "ХВХЫ", "ХАХА", "ХВА", "ВХВХ"]


def laugh() -> str:
    """Каждый раз новый смех вроде «ХВХАХАХАХВХАХВХЫХВХА»."""
    s = "".join(random.choice(LAUGH_PARTS) for _ in range(random.randint(4, 9)))
    return s + random.choice(["😂", "💀", "🤣"]) if random.random() < 0.15 else s


@command("spam")
async def spam(c: Ctx):
    m = re.match(r"^(\d+)\s+([\s\S]+)$", c.args)
    if not m:
        raise ValueError(f"формат: .spam 5 текст (максимум {MAX_REPEAT})")
    await c.delete()
    text = esc(m[2])
    for _ in range(min(MAX_REPEAT, int(m[1]))):
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
    for w in words[:MAX_SPAMG_WORDS]:
        await c.say(esc(w))
        await asyncio.sleep(0.8)


@command("haha")
async def haha(c: Ctx):
    await c.delete()
    for _ in range(min(MAX_REPEAT, int(c.args) if c.args.isdigit() else 5)):
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
    await c.note(f"🧹 Мои сообщения в этом чате удаляются через {esc(c.args)}" if sec else "🧹 Автоудаление в чате выключено")
    await c.delete()


@command("mute")
async def mute(c: Ctx):
    await c.chat_set(muted=True)
    await c.edit("🤫 Собеседник в муте навсегда. Чтобы размутить нажмите кнопку ниже или напишите <code>.unmute</code>",
                 unmute_kb(c.bc, c.chat_id))


@command("unmute")
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
async def troll(c): await _toggle(c, "troll", "🗿 Троллинг включён: отвечаю на каждое сообщение собеседника", "🗿 Троллинг выключен")
@command("nomute")
async def nomute(c): await _toggle(c, "nomute", "🔓 Обход мута включён: если твоё сообщение удалят сразу после отправки, отправлю его ещё раз", "🔓 Обход мута выключен")


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
        f"🌍 Страна: {spoil('знаешь')}\n"
        f"🏙 Город: {spoil('сам знаешь')}\n"
        f"📱 Номер: {spoil('сам знаешь')}\n"
        f"👩 Номер мамы: {spoil('сам знаешь')}\n"
        f"🛣 Улица: {spoil('сам знаешь куда ехать :)')}\n"
        f"🚪 Квартира: {spoil('00')}\n\n"
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
