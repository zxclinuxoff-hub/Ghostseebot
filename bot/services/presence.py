"""Присутствие владельца. Bot API не отдаёт статус «в сети», поэтому считаем активностью
любые действия владельца: сообщения в Business-чатах (кроме наших автоответов), сообщения и кнопки боту."""
from __future__ import annotations

import time

from aiogram import BaseMiddleware

from . import presence_rules as R

_last: dict[int, float] = {}


def touch(uid: int) -> None:
    now = time.time()
    if len(_last) > 20000:  # очистка старых записей
        for k in [k for k, v in _last.items() if now - v > 3600]:
            _last.pop(k, None)
    _last[uid] = now


def is_online(uid: int) -> bool:
    return R.is_recent(_last.get(uid), time.time())


class PresenceMW(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user:
            touch(user.id)
        return await handler(event, data)
