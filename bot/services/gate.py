"""Обязательная подписка на канал: без неё бот ничем не пользуется."""
import time

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from ..config import cfg
from . import referrals

GATE_TEXT = (f"🔒 <b>Доступ только для подписчиков канала</b>\n\n"
             f"Подпишись на {cfg.channel} и нажми «Я подписался» — после этого бот заработает.")
GATE_SHORT = f"🔒 Бот на паузе: подпишись на канал {cfg.channel}, чтобы пользоваться им."

_cache: dict[int, tuple[float, object, int]] = {}


async def is_member(bot, uid: int, force: bool = False):
    """True / False / None (не удалось проверить — например, бот не админ канала)."""
    c = _cache.get(uid)
    if c and not force and time.time() - c[0] < c[2]:
        return c[1]
    res = await referrals.is_subscribed(bot, uid)
    _cache[uid] = (time.time(), res, 600 if res else 20 if res is False else 60)
    return res


async def allowed(bot, uid: int) -> bool:
    if uid in cfg.admin_ids:
        return True
    return (await is_member(bot, uid)) is not False  # None (ошибка проверки) не блокирует


class GateMiddleware(BaseMiddleware):
    """Блокирует личку с ботом (меню, покупки, кнопки) для тех, кто не подписан на канал."""

    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if not user or user.id in cfg.admin_ids:
            return await handler(event, data)
        if isinstance(event, Message):
            if event.chat.type != "private" or event.successful_payment or (event.text or "").startswith("/start"):
                return await handler(event, data)
        elif isinstance(event, CallbackQuery):
            if (event.data or "").startswith(("check_sub", "unmute:")):
                return await handler(event, data)
        else:
            return await handler(event, data)
        bot = data["bot"]
        if await allowed(bot, user.id):
            return await handler(event, data)
        from ..keyboards import channel_kb
        if isinstance(event, CallbackQuery):
            await event.answer("🔒 Сначала подпишись на канал", show_alert=True)
        await bot.send_message(user.id, GATE_TEXT, reply_markup=channel_kb())
        return None
