from __future__ import annotations

import html
import io
import random
import re
import time
from types import SimpleNamespace

from aiogram import Bot, F, Router
from aiogram.types import BufferedInputFile, BusinessConnection, CallbackQuery, BusinessMessagesDeleted, Message

from ..commands import engine
from ..commands import tools  # noqa: F401  (регистрирует команды)
from ..keyboards import buy_shortcut
from ..services import biz
from ..services import users as U
from ..services.logs import audit

router = Router(name="business")
esc = html.escape

MAT = re.compile(r"(хуй|хуе|хуё|хуя|пизд|ебан|ёбан|ебат|ебал|ебну|заеб|сука|сучк|бляд|блят|мудак|мудил|залуп|пидор|пидар|пидр)", re.I)
TROLL = ["а ты уверен?", "ну допустим 🗿", "интересно…", "и что дальше?", "хм 🤔", "ага, конечно", "😏", "записал"]
SEND = {"photo": "send_photo", "video": "send_video", "video_note": "send_video_note", "voice": "send_voice",
        "audio": "send_audio", "animation": "send_animation", "document": "send_document", "sticker": "send_sticker"}


def media_of(m: Message):
    if m.photo:
        return {"type": "photo", "file_id": m.photo[-1].file_id}
    for t in ("video", "video_note", "voice", "audio", "animation", "document", "sticker"):
        obj = getattr(m, t, None)
        if obj:
            return {"type": t, "file_id": obj.file_id}
    return None


def name_of(u) -> str:
    if not u:
        return "—"
    n = " ".join(x for x in (u.first_name, getattr(u, "last_name", None)) if x) or "—"
    return esc(n + (f" (@{u.username})" if getattr(u, "username", None) else ""))


async def send_media(bot: Bot, chat_id: int, media: dict, silent: bool = False):
    meth = getattr(bot, SEND[media["type"]])
    try:
        return await meth(chat_id, media["file_id"], disable_notification=silent)
    except Exception:
        f = await bot.get_file(media["file_id"])
        buf = io.BytesIO()
        await bot.download_file(f.file_path, buf)
        return await meth(chat_id, BufferedInputFile(buf.getvalue(), filename=f.file_path.split("/")[-1]), disable_notification=silent)


async def owner_user(conn: dict):
    u = await U.get_user(conn["owner_id"])
    if u:
        return u
    u, _ = await U.ensure_user(SimpleNamespace(id=conn["owner_id"], first_name=conn.get("first_name") or "", username=conn.get("username")))
    return u


async def upsell(bot: Bot, u: dict, conn: dict, text: str):
    last = U.parse(u.get("last_notice"))
    if last and (U.now() - last).total_seconds() < 86400:
        return
    await U.patch_user(u["tg_id"], last_notice=U.iso(U.now()))
    await bot.send_message(conn["user_chat_id"], text, reply_markup=buy_shortcut())


EXPIRED = "⏸ Подписка закончилась, бот на паузе. Продли — и всё продолжит работать."


# ---------------- подключение ----------------
@router.business_connection()
async def on_connection(c: BusinessConnection, bot: Bot):
    await biz.save_conn({"id": c.id, "owner_id": c.user.id, "user_chat_id": c.user_chat_id, "enabled": c.is_enabled,
                         "first_name": c.user.first_name or "", "last_name": c.user.last_name or "", "username": c.user.username})
    if c.is_enabled:
        u, _ = await U.ensure_user(c.user)
        await audit("info", "connect", c.user.id)
        st = f"✅ Подписка до {U.fmt_dt(u['sub_until'])}" if U.is_active(u) else EXPIRED
        await bot.send_message(c.user_chat_id, f"✅ <b>Бот подключён к аккаунту.</b>\n{st}\n\nКоманды: <code>.help</code> · временное фото: ответь «сии».")
    else:
        await audit("info", "disconnect", c.user.id)


# ---------------- сообщения ----------------
@router.business_message()
async def on_message(m: Message, bot: Bot):
    bc = m.business_connection_id
    conn = await biz.get_conn(bc)
    if not conn or not m.from_user:
        return
    u = await owner_user(conn)
    if u.get("banned"):
        return
    active = U.is_active(u)
    chat = m.chat.id
    owner = m.from_user.id == conn["owner_id"]
    text = (m.text or "").strip()
    snap = {"name": name_of(m.from_user), "text": m.text, "caption": m.caption, "media": media_of(m), "out": owner}

    if owner:
        if re.fullmatch(r"(сии|сий|сиии|sii)", text, re.I) and m.reply_to_message:
            if not active:
                return await upsell(bot, u, conn, EXPIRED)
            media = media_of(m.reply_to_message)
            if not media:
                return await bot.send_message(conn["user_chat_id"], "⚠️ В сообщении, на которое ты ответил, нет медиа (или Telegram его не отдал боту).")
            silent = U.setting(u, "silent", False)
            await bot.send_message(conn["user_chat_id"], f"👁 <b>Временное медиа</b> от {name_of(m.reply_to_message.from_user)}", disable_notification=silent)
            try:
                await send_media(bot, conn["user_chat_id"], media, silent)
                await audit("info", "timer_reveal", conn["owner_id"], type=media["type"])
            except Exception as e:
                await audit("error", "timer_fail", conn["owner_id"], err=str(e)[:200])
                await bot.send_message(conn["user_chat_id"], "⚠️ Не удалось получить медиа: " + str(e)[:200])
            try:
                await biz.delete(bc, [m.message_id])
            except Exception:
                pass
            return
        if not active:
            if text.startswith("."):
                await upsell(bot, u, conn, EXPIRED)
            return
        await biz.cache_msg(bc, chat, m.message_id, conn["owner_id"], snap)
        sec = (await biz.chat_get(bc, chat)).get("bchat")
        if sec:
            await biz.schedule("del", sec, bc=bc, ids=[m.message_id])
        if text.startswith((".", "/")):
            ran = await engine.run(bot, m, conn, u)
            if ran:
                await audit("info", "cmd", conn["owner_id"], cmd=ran)
        return

    # ---- входящее от собеседника ----
    if not active:
        return
    await biz.cache_msg(bc, chat, m.message_id, conn["owner_id"], snap)
    st = await biz.chat_get(bc, chat)
    body = (m.text or m.caption or "")
    bw = st.get("bw") or []
    if (st.get("muted") or (st.get("wsag") and (m.sticker or m.animation))
            or (st.get("wbl") and MAT.search(body)) or any(w in body.lower() for w in bw)):
        try:
            await biz.delete(bc, [m.message_id])
        except Exception as e:
            await audit("warn", "delete_failed", conn["owner_id"], err=str(e)[:150])
        return
    if m.from_user.is_bot:
        return

    now = time.time()
    if st.get("clone") and m.text and now - st.get("last_clone", 0) > 2:
        await biz.chat_set(bc, chat, last_clone=now)
        return await biz.send(bc, chat, esc(m.text))
    if st.get("troll") and now - st.get("last_troll", 0) > 20:
        await biz.chat_set(bc, chat, last_troll=now)
        return await biz.send(bc, chat, random.choice(TROLL))
    afk = (u.get("settings") or {}).get("afk")
    if st.get("auto") and now - st.get("last_auto", 0) > 60:
        await biz.chat_set(bc, chat, last_auto=now)
        return await biz.send(bc, chat, esc(st["auto"]))
    if afk and now - st.get("last_afk", 0) > 180:
        await biz.chat_set(bc, chat, last_afk=now)
        await biz.send(bc, chat, f"🌙 <b>AFK:</b> {esc(afk['text'])}\n⏱ Прошло: {U.elapsed(afk['since'])}")


@router.edited_business_message()
async def on_edited(m: Message, bot: Bot):
    bc = m.business_connection_id
    conn = await biz.get_conn(bc)
    if not conn or not m.from_user:
        return
    u = await owner_user(conn)
    if u.get("banned") or not U.is_active(u):
        return
    owner = m.from_user.id == conn["owner_id"]
    old = await biz.get_msg(bc, m.chat.id, m.message_id)
    new_text = m.text or m.caption or ""
    if not owner and old and U.setting(u, "notify_edited", True):
        was = old.get("text") or old.get("caption") or ""
        silent = U.setting(u, "silent", False)
        await bot.send_message(conn["user_chat_id"], (f"✏️ <b>Изменено</b> • {name_of(m.from_user)}\n\n<b>Было:</b>\n{esc(was) or '<i>(медиа/пусто)</i>'}"
                                                      f"\n\n<b>Стало:</b>\n{esc(new_text) or '<i>(медиа/пусто)</i>'}")[:4000], disable_notification=silent)
        nm = media_of(m)
        if nm and old.get("media") and nm["file_id"] != old["media"]["file_id"]:
            try:
                await send_media(bot, conn["user_chat_id"], old["media"], silent)
            except Exception:
                pass
        await audit("info", "edited_fwd", conn["owner_id"])
    await biz.cache_msg(bc, m.chat.id, m.message_id, conn["owner_id"],
                        {"name": name_of(m.from_user), "text": m.text, "caption": m.caption, "media": media_of(m), "out": owner})


@router.deleted_business_messages()
async def on_deleted(d: BusinessMessagesDeleted, bot: Bot):
    bc = d.business_connection_id
    conn = await biz.get_conn(bc)
    if not conn:
        return
    u = await owner_user(conn)
    if u.get("banned"):
        return
    if not U.is_active(u):
        return await upsell(bot, u, conn, "⏸ Тебе удалили сообщение, но бот на паузе (подписка закончилась).")
    notify = U.setting(u, "notify_deleted", True)
    silent = U.setting(u, "silent", False)
    n = 0
    for mid in d.message_ids:
        rec = await biz.get_msg(bc, d.chat.id, mid)
        if not rec:
            continue
        await biz.drop_msg(bc, d.chat.id, mid)
        if rec.get("out") or not notify:
            continue
        body = rec.get("text") or rec.get("caption") or ""
        await bot.send_message(conn["user_chat_id"], (f"🗑 <b>Удалено</b> • {rec['name']}\n\n"
                                                      + (esc(body) or ("<i>(медиа ниже)</i>" if rec.get("media") else "<i>(пусто)</i>")))[:4000],
                               disable_notification=silent)
        if rec.get("media"):
            try:
                await send_media(bot, conn["user_chat_id"], rec["media"], silent)
            except Exception as e:
                await audit("warn", "deleted_media_failed", conn["owner_id"], err=str(e)[:150])
        n += 1
    if n:
        await audit("info", "deleted_fwd", conn["owner_id"], count=n)


# ---------------- кнопка «Размутить» ----------------
@router.callback_query(F.data.startswith("unmute:"))
async def cb_unmute(cb: CallbackQuery):
    _, bc, chat = cb.data.split(":", 2)
    conn = await biz.get_conn(bc)
    if not conn or cb.from_user.id != conn["owner_id"]:
        return await cb.answer("Только владелец аккаунта", show_alert=True)
    await biz.chat_set(bc, int(chat), muted=False, warns=0)
    await cb.answer("😃 Мут снят")
    try:
        await biz.edit(bc, int(chat), cb.message.message_id, "😃 Мут снят")
    except Exception:
        pass
