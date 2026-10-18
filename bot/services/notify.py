"""Временные сообщения в группу: отправить и удалить через ttl секунд. В базу ничего не пишем."""
import asyncio
import logging

from aiogram import Bot

from ..config import LOG_CHAT_ID

log = logging.getLogger("ghostsee.notify")
_pending: set = set()


async def _expire(bot: Bot, chat_id: int, message_id: int, ttl: float):
    await asyncio.sleep(ttl)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception as e:  # уже удалено или нет прав — не страшно
        log.info("temp message not deleted: %s", e)


async def temp_notice(bot: Bot, text: str, ttl: float = 15, thread_id: int | None = None,
                      chat_id: int = LOG_CHAT_ID) -> None:
    kwargs = {"message_thread_id": thread_id} if thread_id else {}
    msg = await bot.send_message(chat_id, text[:4000], **kwargs)
    t = asyncio.create_task(_expire(bot, chat_id, msg.message_id, ttl))
    _pending.add(t)
    t.add_done_callback(_pending.discard)
