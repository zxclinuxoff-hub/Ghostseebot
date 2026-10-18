"""Обязательная подписка на канал: без неё бот ничем не пользуется."""
import time

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from ..config import cfg
from . import referrals

GATE_TEXT = (f"🔒 <b>Доступ только для подписчиков канала</b>\n\n"
             f"Подпишись на {cfg.channel} и нажми «Я подписался» — после этого бот заработает.")
GATE_SHORT = f"🔒 Бот на паузе: подпишись на канал {cfg.channel}, чтобы пользоваться им."

# uid -> (ts, result, ttl)
_cache: dict[int, tuple[float, object, int]] = {}


async def is_member(bot, uid: int, force: bool = False):
    """True / False / None (не удалось проверить — бот не админ канала и т.п.)."""
    c = _cache.get(uid)
    if c and not force and time.time() - c[0] < c[2]:
        return c[1]
    res = await referrals.is_subscribed(bot, uid)
    # Подписан — кэш коротко (чтобы отписка быстро ловилась).
    # Не подписан — тоже коротко (чтобы «Я подписался» быстро открывало доступ).
    # Ошибка проверки — минута.
    if res is True:
        ttl = 45
    elif res is False:
        ttl = 15
    else:
        ttl = 60
    _cache[uid] = (time.time(), res, ttl)
    return res


def invalidate(uid: int):
    _cache.pop(uid, None)


async def allowed(bot, uid: int, force: bool = False) -> bool:
    """Доступ только при явной подписке. Админы — всегда."""
    if uid in cfg.admin_ids:
        return True
    # Только True. False и None (сбой проверки) — блок.
    # None блокируем специально: иначе при ошибке API все ходят без канала.
    return (await is_member(bot, uid, force=force)) is True


class GateMiddleware(BaseMiddleware):
    """Блокирует личку с ботом (меню, покупки, кнопки) для тех, кто не подписан на канал."""

    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if not user or user.id in cfg.admin_ids:
            return await handler(event, data)

        if isinstance(event, Message):
            # /start всегда пускаем (там свой гейт + кнопка «Я подписался»)
            if event.chat.type != "private" or event.successful_payment:
                return await handler(event, data)
            text = (event.text or "").strip()
            if text.startswith("/start"):
                return await handler(event, data)
        elif isinstance(event, CallbackQuery):
            # только проверка подписки
            if (event.data or "").startswith("check_sub"):
                return await handler(event, data)
        else:
            return await handler(event, data)

        bot = data["bot"]
        if await allowed(bot, user.id):
            return await handler(event, data)

        from ..keyboards import channel_kb
        if isinstance(event, CallbackQuery):
            try:
                await event.answer("🔒 Сначала подпишись на канал", show_alert=True)
            except Exception:
                pass
            try:
                await bot.send_message(user.id, GATE_TEXT, reply_markup=channel_kb())
            except Exception:
                pass
            return None

        await bot.send_message(user.id, GATE_TEXT, reply_markup=channel_kb())
        return None
