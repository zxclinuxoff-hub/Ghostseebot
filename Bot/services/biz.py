"""Работа с Business API напрямую через HTTP (не зависит от версии aiogram), кэш сообщений, состояния чатов, отложенные задачи."""
from __future__ import annotations

import time

import httpx

from ..config import cfg
from ..db import db
from . import users as U

_http = httpx.AsyncClient(timeout=30)


class TgError(Exception):
    pass


async def api(method: str, **params):
    params = {k: v for k, v in params.items() if v is not None}
    r = await _http.post(f"https://api.telegram.org/bot{cfg.bot_token}/{method}", json=params)
    j = r.json()
    if not j.get("ok"):
        raise TgError(f"{method}: {j.get('description')}")
    return j["result"]


def kb_json(kb):
    return kb.model_dump(mode="json", exclude_none=True) if kb else None


async def edit(bc, chat_id, mid, text, kb=None):
    return await api("editMessageText", business_connection_id=bc, chat_id=chat_id, message_id=mid,
                     text=text[:4096], parse_mode="HTML", reply_markup=kb_json(kb))


async def send(bc, chat_id, text, kb=None):
    return await api("sendMessage", business_connection_id=bc, chat_id=chat_id, text=text[:4096],
                     parse_mode="HTML", reply_markup=kb_json(kb))


async def delete(bc, ids):
    return await api("deleteBusinessMessages", business_connection_id=bc, message_ids=list(ids))


async def chat_action(bc, chat_id, action):
    return await api("sendChatAction", business_connection_id=bc, chat_id=chat_id, action=action)


async def set_name(bc, first, last=None):
    return await api("setBusinessAccountName", business_connection_id=bc, first_name=first, last_name=last or None)


# ---------- подключения ----------
_conns: dict[str, dict] = {}


async def save_conn(row: dict):
    _conns[row["id"]] = row
    await db.insert("gs_conns", row, upsert="id", returning=False)
    return row


async def get_conn(bc: str):
    if bc in _conns:
        return _conns[bc]
    rows = await db.select("gs_conns", {"id": f"eq.{bc}"})
    if rows:
        _conns[bc] = rows[0]
        return rows[0]
    try:
        c = await api("getBusinessConnection", business_connection_id=bc)
    except TgError:
        return None
    return await save_conn({
        "id": bc, "owner_id": c["user"]["id"], "user_chat_id": c["user_chat_id"], "enabled": c.get("is_enabled", True),
        "first_name": c["user"].get("first_name", ""), "last_name": c["user"].get("last_name", ""),
        "username": c["user"].get("username"),
    })


# ---------- состояние чата (мут, автоответчик, фильтры...) ----------
_chat: dict[tuple, tuple[float, dict]] = {}


async def chat_get(bc, chat_id) -> dict:
    k = (bc, chat_id)
    c = _chat.get(k)
    if c and time.time() - c[0] < 60:
        return c[1]
    rows = await db.select("gs_chat", {"bc": f"eq.{bc}", "chat_id": f"eq.{chat_id}"})
    data = rows[0]["data"] if rows else {}
    _chat[k] = (time.time(), data)
    return data


async def chat_set(bc, chat_id, **kw) -> dict:
    data = {**await chat_get(bc, chat_id), **kw}
    _chat[(bc, chat_id)] = (time.time(), data)
    await db.insert("gs_chat", {"bc": bc, "chat_id": chat_id, "data": data}, upsert="bc,chat_id", returning=False)
    return data


# ---------- кэш сообщений ----------
async def cache_msg(bc, chat_id, mid, owner_id, data: dict):
    await db.insert("gs_msgs", {"bc": bc, "chat_id": chat_id, "msg_id": mid, "owner_id": owner_id, "data": data},
                    upsert="bc,chat_id,msg_id", returning=False)


async def get_msg(bc, chat_id, mid):
    rows = await db.select("gs_msgs", {"bc": f"eq.{bc}", "chat_id": f"eq.{chat_id}", "msg_id": f"eq.{mid}"})
    return rows[0]["data"] if rows else None


async def drop_msg(bc, chat_id, mid):
    await db.delete("gs_msgs", {"bc": f"eq.{bc}", "chat_id": f"eq.{chat_id}", "msg_id": f"eq.{mid}"})


# ---------- отложенные задачи ----------
async def schedule(kind: str, delay_s: float, **payload):
    import datetime as dt
    await db.insert("gs_jobs", {"run_at": U.iso(U.now() + dt.timedelta(seconds=delay_s)), "kind": kind, "payload": payload},
                    returning=False)
