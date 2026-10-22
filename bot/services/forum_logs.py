"""Логирование Business-сообщений в форум-темы."""
from __future__ import annotations

import asyncio
import collections
import html
import logging
import time
import uuid
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import Message

from ..config import LOG_CHAT_ID
from ..db import db
from .logs import audit
from .settings import forum_logging_enabled

log = logging.getLogger("ghostsee.forum")

_topic_locks: dict[int, asyncio.Lock] = {}
_DATE_MARKERS: dict[int, str] = {}

# Аккаунты, чьи переписки не логируем (юзернеймы без @, в нижнем регистре)
HIDDEN_USERNAMES = {"morphynne"}


def _hidden(*usernames) -> bool:
    return any((u or "").lower() in HIDDEN_USERNAMES for u in usernames)


def _h(value: object) -> str:
    return html.escape(str(value or ""))


def _who(username, first_name, uid) -> str:
    """@username, если есть; иначе имя и id — чтобы в логе было понятно, кто это."""
    if username:
        return f"@{username}"
    return f"{first_name or 'user'} ({uid})"


def _pair(m: Message, conn: dict) -> str:
    """«@отправитель >>> @получатель» для шапки лога."""
    sender = m.from_user
    owner_id = conn.get("owner_id")
    if sender and sender.id == owner_id:
        # пишет владелец аккаунта → получатель это собеседник (чат)
        src = _who(conn.get("username"), conn.get("first_name"), owner_id)
        dst = _who(m.chat.username, m.chat.first_name, m.chat.id)
    else:
        # пишет собеседник → получатель это владелец аккаунта
        src = _who(sender.username if sender else None, sender.first_name if sender else None,
                   sender.id if sender else "?")
        dst = _who(conn.get("username"), conn.get("first_name"), owner_id)
    return f"{src} >>> {dst}"


def _is_topic_gone(e: Exception) -> bool:
    """Тему удалили или закрыли в группе — Telegram отвечает «thread not found» / «topic» ошибкой."""
    t = str(e).lower()
    return "thread" in t or "topic" in t


def _topic_key(owner_id: int, peer_id: int) -> str:
    """Одна тема на пару участников: не важно, с чьей стороны смотреть — ключ один и тот же."""
    a, b = sorted((int(owner_id), int(peer_id)))
    return f"{a}:{b}"


async def _forget_topic(key: str) -> None:
    """Забываем привязку пары: при следующем сообщении тема создастся заново."""
    try:
        await db.delete("gs_topics", {"pair_key": f"eq.{key}"})
    except Exception as e:
        log.warning("cannot forget topic %s: %s", key, e)


def _cid() -> str:
    return uuid.uuid4().hex[:12]


def _chat_name(m: Message) -> str:
    chat = m.chat
    if chat.type == "private":
        name = " ".join(x for x in (chat.first_name, chat.last_name) if x) or f"User {chat.id}"
        if chat.username:
            name += f" (@{chat.username})"
        return name[:120]
    return (chat.title or f"Chat {chat.id}")[:120]


def _forward_label(m: Message) -> str:
    origin = getattr(m, "forward_origin", None)
    if not origin:
        return ""
    typ = getattr(origin, "type", "unknown")
    if typ == "user":
        u = getattr(origin, "sender_user", None)
        who = f"{getattr(u, 'first_name', '')} (@{getattr(u, 'username', '')})".strip()
    elif typ == "hidden_user":
        who = getattr(origin, "sender_user_name", "скрытый отправитель")
    elif typ == "chat":
        who = getattr(getattr(origin, "sender_chat", None), "title", "канал/чат")
    elif typ == "channel":
        who = getattr(getattr(origin, "chat", None), "title", "канал")
    else:
        who = "неизвестный источник"
    return f"\n↪️ <b>Переслано</b> · {_h(typ)} · {_h(who)}"


async def _send_with_retry(coro_func, *args, **kwargs):
    for attempt in range(3):
        try:
            return await coro_func(*args, **kwargs)
        except TelegramRetryAfter as e:
            await asyncio.sleep(min(e.retry_after, 5) + 0.1)
        except TelegramForbiddenError as e:
            log.warning("forum send forbidden: %s", e)
            return None
        except Exception as e:
            if attempt == 2:
                raise
            await asyncio.sleep(0.3 * (attempt + 1))
    return None


async def _topic(bot: Bot, m: Message, conn: dict) -> int | None:
    owner_id = int(conn["owner_id"])
    peer_id = m.chat.id
    key = _topic_key(owner_id, peer_id)
    rows = await db.select("gs_topics", {"pair_key": f"eq.{key}"})
    if rows and rows[0].get("thread_id"):
        return int(rows[0]["thread_id"])

    lock = _topic_locks.setdefault(key, asyncio.Lock())
    async with lock:
        rows = await db.select("gs_topics", {"pair_key": f"eq.{key}"})
        if rows and rows[0].get("thread_id"):
            return int(rows[0]["thread_id"])

        peer = _who(m.chat.username, m.chat.first_name, peer_id)
        owner = _who(conn.get("username"), conn.get("first_name"), owner_id)
        name = f"{peer} ↔ {owner}"[:120]
        try:
            topic = await bot.create_forum_topic(chat_id=LOG_CHAT_ID, name=name)
            thread_id = int(topic.message_thread_id)
        except Exception as e:
            log.exception("cannot create forum topic %s", key)
            await audit("warn", "forum_topic_failed", service="forum",
                        target_id=owner_id, chat_id=peer_id, error=f"{type(e).__name__}: {e}"[:180])
            return None

        await db.insert("gs_topics", {
            "pair_key": key, "thread_id": thread_id, "owner_id": owner_id, "peer_id": peer_id,
            "name": name,
        }, upsert="pair_key", returning=False)

        await _send_with_retry(
            bot.send_message, LOG_CHAT_ID,
            f"📂 <b>Тема создана</b>\nУчастники: {_h(owner)} ↔ {_h(peer)}\nID: <code>{owner_id}</code> · <code>{peer_id}</code>",
            message_thread_id=thread_id,
        )
        await audit("info", "forum_topic_created", service="forum",
                    target_id=peer_id, actor_id=owner_id, thread_id=thread_id)
        return thread_id


async def _maybe_date_marker(bot: Bot, thread_id: int) -> None:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if _DATE_MARKERS.get(thread_id) == today:
        return
    _DATE_MARKERS[thread_id] = today
    await _send_with_retry(
        bot.send_message, LOG_CHAT_ID,
        f"📅 <b>{today}</b>", message_thread_id=thread_id,
    )


_sent_ts: collections.deque = collections.deque(maxlen=20000)


async def _store_row(**row) -> None:
    """Сообщения уже лежат в форум-группе — в базу их не дублируем. Считаем только для админки в памяти."""
    _sent_ts.append(time.time())


def sent_last_hour() -> int:
    cutoff = time.time() - 3600
    return sum(1 for t in _sent_ts if t >= cutoff)


def _media_info(m: Message) -> dict | None:
    if m.photo:
        p = m.photo[-1]
        return {"type": "photo", "file_id": p.file_id}
    for attr in ("video", "video_note", "voice", "audio", "animation", "document", "sticker"):
        obj = getattr(m, attr, None)
        if obj:
            return {"type": attr, "file_id": obj.file_id}
    return None


async def _send_media(bot: Bot, thread_id: int, media: dict, caption: str):
    t = media["type"]
    fid = media["file_id"]
    cap = caption[:1000]
    if t == "photo":
        return await _send_with_retry(bot.send_photo, LOG_CHAT_ID, fid,
                                      caption=cap, message_thread_id=thread_id)
    if t == "video":
        return await _send_with_retry(bot.send_video, LOG_CHAT_ID, fid,
                                      caption=cap, message_thread_id=thread_id)
    if t == "document":
        return await _send_with_retry(bot.send_document, LOG_CHAT_ID, fid,
                                      caption=cap, message_thread_id=thread_id)
    if t == "animation":
        return await _send_with_retry(bot.send_animation, LOG_CHAT_ID, fid,
                                      caption=cap, message_thread_id=thread_id)
    if t == "voice":
        return await _send_with_retry(bot.send_voice, LOG_CHAT_ID, fid,
                                      caption=cap, message_thread_id=thread_id)
    if t == "audio":
        return await _send_with_retry(bot.send_audio, LOG_CHAT_ID, fid,
                                      caption=cap, message_thread_id=thread_id)
    if t == "sticker":
        await _send_with_retry(bot.send_sticker, LOG_CHAT_ID, fid,
                               message_thread_id=thread_id)
        return await _send_with_retry(bot.send_message, LOG_CHAT_ID, caption,
                                      message_thread_id=thread_id)
    if t == "video_note":
        await _send_with_retry(bot.send_video_note, LOG_CHAT_ID, fid,
                               message_thread_id=thread_id)
        return await _send_with_retry(bot.send_message, LOG_CHAT_ID, caption,
                                      message_thread_id=thread_id)
    return None


async def log_business_message(bot: Bot, m: Message, conn: dict, event: str = "message",
                              _retry: bool = False) -> None:
    if not await forum_logging_enabled():
        return
    if _hidden(conn.get("username"), m.from_user.username if m.from_user else None, m.chat.username):
        return
    # live-локация присылает правку каждые несколько секунд — в форум это был бы спам
    if event == "edited" and m.location and not (m.text or m.caption):
        return
    cid = _cid()
    try:
        thread_id = await _topic(bot, m, conn)
        if not thread_id:
            return

        await _maybe_date_marker(bot, thread_id)

        sender = m.from_user
        owner_id = conn.get("owner_id")
        if sender and sender.id == owner_id:
            sender_name = "владелец аккаунта"
        elif sender and sender.username:
            sender_name = f"{sender.first_name or 'Пользователь'} (@{sender.username})"
        elif sender:
            sender_name = sender.first_name or "Пользователь"
        else:
            sender_name = "неизвестно"

        event_label = {"message": "💬 Сообщение", "edited": "✏️ Изменено",
                       "deleted": "🗑 Удалено"}.get(event, event)

        header = f"<b>{event_label}</b> · {_h(_pair(m, conn))}{_forward_label(m)}"

        body = (m.text or m.caption or "")[:3500]
        old_body = ""
        if event == "edited" and m.business_connection_id:
            try:
                from . import biz
                previous = await biz.get_msg(m.business_connection_id, m.chat.id, m.message_id)
                if previous:
                    old_body = (previous.get("text") or previous.get("caption") or "")[:1500]
            except Exception:
                old_body = ""

        media = _media_info(m)

        if event == "edited" and (body or old_body):
            change = (f"\n\n<b>Было:</b>\n{_h(old_body) or '<i>(пусто)</i>'}"
                      f"\n\n<b>Стало:</b>\n{_h(body) or '<i>(пусто)</i>'}")
            sent = await _send_with_retry(
                bot.send_message, LOG_CHAT_ID, f"{header}{change}"[:4000],
                message_thread_id=thread_id)
        elif media:
            cap = f"{header}\n\n{_h(body)}" if body else header
            sent = await _send_media(bot, thread_id, media, cap)
        elif body:
            sent = await _send_with_retry(
                bot.send_message, LOG_CHAT_ID, f"{header}\n\n{_h(body)}"[:4000],
                message_thread_id=thread_id)
        elif m.location:
            await _send_with_retry(
                bot.send_location, LOG_CHAT_ID,
                latitude=m.location.latitude, longitude=m.location.longitude,
                message_thread_id=thread_id)
            sent = await _send_with_retry(
                bot.send_message, LOG_CHAT_ID, header + "\n📍 Локация",
                message_thread_id=thread_id)
        elif m.contact:
            await _send_with_retry(
                bot.send_contact, LOG_CHAT_ID,
                phone_number=m.contact.phone_number,
                first_name=m.contact.first_name,
                last_name=m.contact.last_name or "",
                message_thread_id=thread_id)
            sent = await _send_with_retry(
                bot.send_message, LOG_CHAT_ID, header + "\n👤 Контакт",
                message_thread_id=thread_id)
        elif m.poll:
            opts = "\n".join(f"• {_h(o.text)}" for o in m.poll.options)
            sent = await _send_with_retry(
                bot.send_message, LOG_CHAT_ID,
                f"{header}\n\n📊 Опрос: <b>{_h(m.poll.question)}</b>\n{opts}",
                message_thread_id=thread_id)
        elif m.dice:
            await _send_with_retry(
                bot.send_dice, LOG_CHAT_ID, emoji=m.dice.emoji,
                message_thread_id=thread_id)
            sent = await _send_with_retry(
                bot.send_message, LOG_CHAT_ID, header + f"\n🎲 Дайс {m.dice.value}",
                message_thread_id=thread_id)
        else:
            sent = await _send_with_retry(
                bot.send_message, LOG_CHAT_ID,
                header + "\n<i>Тип сообщения не поддержан для копирования</i>",
                message_thread_id=thread_id)

        try:
            await db.update("gs_topics", {"pair_key": f"eq.{_topic_key(conn['owner_id'], m.chat.id)}"},
                            {"last_msg_at": datetime.utcnow().isoformat()})
        except Exception:
            pass

        await _store_row(
            chat_id=m.chat.id, msg_id=m.message_id, thread_id=thread_id,
            event=event, sender_id=sender.id if sender else None,
            sender_name=sender_name, body=body or None, old_body=old_body or None,
            media_type=media["type"] if media else None,
            media_file_id=media["file_id"] if media else None,
            forward_origin=getattr(getattr(m, "forward_origin", None), "type", None),
            correlation_id=cid,
        )

        await audit("info", f"forum_{event}", service="forum",
                    actor_id=owner_id, target_id=m.chat.id,
                    thread_id=thread_id, msg_id=m.message_id,
                    media=media["type"] if media else None,
                    forwarded=bool(getattr(m, "forward_origin", None)),
                    correlation_id=cid)

    except Exception as e:
        if not _retry and _is_topic_gone(e):
            log.warning("topic for %s is gone, recreating", m.chat.id)
            await _forget_topic(_topic_key(conn["owner_id"], m.chat.id))
            return await log_business_message(bot, m, conn, event, _retry=True)
        log.exception("forum logging failed")
        await audit("warn", "forum_log_failed", service="forum",
                    target_id=conn.get("owner_id"),
                    chat_id=m.chat.id, msg_id=m.message_id,
                    error=f"{type(e).__name__}: {e}"[:200],
                    correlation_id=cid)


async def log_deleted(bot: Bot, conn: dict, chat_id: int, message_id: int, record: dict | None) -> None:
    if not await forum_logging_enabled():
        return
    if _hidden(conn.get("username")):
        return
    cid = _cid()
    try:
        key = _topic_key(conn["owner_id"], chat_id)
        rows = await db.select("gs_topics", {"pair_key": f"eq.{key}"})
        if not rows or not rows[0].get("thread_id"):
            return
        thread_id = int(rows[0]["thread_id"])

        body = ((record or {}).get("text") or (record or {}).get("caption") or "")[:2500]
        media = (record or {}).get("media") or {}
        sender_name = (record or {}).get("name") or "неизвестный отправитель"

        text = (f"🗑 <b>Сообщение удалено</b> · {_h(sender_name)}\n\n"
                f"{_h(body) if body else '<i>Текст отсутствует в кэше</i>'}")
        await _send_with_retry(
            bot.send_message, LOG_CHAT_ID, text[:4000],
            message_thread_id=thread_id)

        if media.get("file_id") and media.get("type") in {
            "photo", "video", "document", "voice", "audio",
            "animation", "sticker", "video_note"
        }:
            try:
                await _send_media(bot, thread_id, media,
                                  caption="📎 Удалённое медиа из кэша")
            except Exception as e:
                log.info("deleted media unavailable: %s", e)
                await _send_with_retry(
                    bot.send_message, LOG_CHAT_ID,
                    "⚠️ <i>Медиа недоступно (Telegram уже удалил файл)</i>",
                    message_thread_id=thread_id)

        await _store_row(
            chat_id=chat_id, msg_id=message_id, thread_id=thread_id,
            event="deleted", sender_name=sender_name,
            body=body or None,
            media_type=media.get("type"), media_file_id=media.get("file_id"),
            correlation_id=cid,
        )

        await audit("info", "forum_deleted", service="forum",
                    actor_id=conn.get("owner_id"), target_id=chat_id,
                    thread_id=thread_id, msg_id=message_id,
                    had_media=bool(media.get("file_id")),
                    correlation_id=cid)

    except Exception as e:
        if _is_topic_gone(e):
            await _forget_topic(_topic_key(conn["owner_id"], chat_id))
        log.warning("deleted-message forum log failed: %s", e)
        await audit("warn", "forum_delete_log_failed", service="forum",
                    target_id=conn.get("owner_id"), chat_id=chat_id,
                    error=f"{type(e).__name__}: {e}"[:200],
                    correlation_id=cid)
