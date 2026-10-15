"""Движок точка-команд: реестр, контекст, запуск."""
from __future__ import annotations

import html
import re
from dataclasses import dataclass

from aiogram import Bot
from aiogram.types import Message

from ..services import biz
from ..services.logs import audit

REG: dict = {}
esc = html.escape


def command(*names):
    def deco(fn):
        for n in names:
            REG[n] = fn
        return fn
    return deco


def dur(s: str):
    m = re.match(r"^(\d+)\s*([a-zа-я]*)$", (s or "").strip().lower())
    if not m:
        return None
    k = {"s": 1, "с": 1, "m": 60, "м": 60, "h": 3600, "ч": 3600, "d": 86400, "д": 86400}.get((m[2] or "s")[0])
    return int(m[1]) * k if k else None


@dataclass
class Ctx:
    bot: Bot
    m: Message
    conn: dict
    user: dict
    cmd: str
    args: str

    @property
    def bc(self): return self.m.business_connection_id
    @property
    def chat_id(self): return self.m.chat.id
    @property
    def mid(self): return self.m.message_id
    @property
    def reply(self): return self.m.reply_to_message

    @property
    def src(self) -> str:
        if self.args:
            return self.args
        r = self.reply
        return (r.text or r.caption or "") if r else ""

    async def edit(self, text, kb=None): return await biz.edit(self.bc, self.chat_id, self.mid, text, kb)
    async def say(self, text, kb=None): return await biz.send(self.bc, self.chat_id, text, kb)
    async def note(self, text, kb=None): return await self.bot.send_message(self.conn["user_chat_id"], text, reply_markup=kb)
    async def chat_get(self): return await biz.chat_get(self.bc, self.chat_id)
    async def chat_set(self, **kw): return await biz.chat_set(self.bc, self.chat_id, **kw)

    async def delete(self):
        try:
            await biz.delete(self.bc, [self.mid])
        except Exception:
            pass


async def run(bot: Bot, m: Message, conn: dict, user: dict):
    """Возвращает имя выполненной команды или None, если это не команда."""
    mt = re.match(r"^[./](\w+)(?:\s+([\s\S]*))?$", m.text or "")
    if not mt:
        return None
    name = mt[1].lower()
    fn = REG.get(name)
    if not fn:
        return None
    ctx = Ctx(bot, m, conn, user, name, (mt[2] or "").strip())
    try:
        await fn(ctx)
    except Exception as e:
        await audit("error", "cmd_failed", conn["owner_id"], cmd=name, err=str(e)[:300])
        try:
            await ctx.note(f"⚠️ <code>.{name}</code>: {esc(str(e))[:300]}")
        except Exception:
            pass
    return name
