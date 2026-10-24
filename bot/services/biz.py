"""Работа с Business API напрямую через HTTP (быстро, с повторами), кэш сообщений, состояния чатов, отложенные задачи."""
from __future__ import annotations

import asyncio
import time

import httpx

from ..config import cfg
from ..db import NetworkError, db
from . import users as U
from .premium_emoji import transform_params

_http = httpx.AsyncClient(
    timeout=httpx.Timeout(20.0, connect=5.0),
    limits=httpx.Limits(max_keepalive_connections=20, keepalive_expiry=60),
)
_SAFE = ("edit", "delete", "get", "sendChatAction", "setBusiness")  # идемпотентные — можно повторять при таймауте


class TgError(Exception):
    pass


class TgNetError(TgError, NetworkError):
    pass


async def api(method: str, **params):
    params = transform_params({k: v for k, v in params.items() if v is not None})
    url = f"https://api.telegram.org/bot{cfg.bot_token}/{method}"
    last = None
    for attempt in range(3):
        try:
            r = await _http.post(url, json=params)
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:  # запрос не ушёл — повторять безопасно
            last = e
            await asyncio.sleep(0.2 * (attempt + 1))
            continue
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last = e
            if method.startswith(_SAFE) and attempt < 2:
                await asyncio.sleep(0.2 * (attempt + 1))
                continue
            break
        try:
            j = r.json()
        except ValueError:
            last = RuntimeError(f"HTTP {r.status_code}")
            await asyncio.sleep(0.3)
            continue
        if j.get("ok"):
            return j["result"]
        ra = (j.get("parameters") or {}).get("retry_after")
        if ra and attempt < 2:  # лимит Telegram — ждём и повторяем
            await asyncio.sleep(min(int(ra), 5) + 0.1)
            continue
        raise TgError(f"{method}: {j.get('description')}")
    raise TgNetError(f"{method}: {type(last).__name__ if last else '?'} (сеть/таймаут)")


def kb_json(kb):
    return kb.model_dump(mode="json", exclude_none=True) if kb else None


async def edit(bc, chat_id, mid, text, kb=None):
    return await api("editMessageText", business_connection_id=bc, chat_id=chat_id, message_id=mid,
                     text=text[:4096], parse_mode="HTML", reply_markup=kb_json(kb))


_own: dict[tuple, float] = {}  # сообщения, которые отправил сам бот от имени владельца


def is_own(bc, chat_id, msg_id) -> bool:
    return (bc, chat_id, msg_id) in _own


async def send(bc, chat_id, text, kb=None, reply_to=None):
    r = await api("sendMessage", business_connection_id=bc, chat_id=chat_id, text=text[:4096], parse_mode="HTML",
                  reply_markup=kb_json(kb), reply_parameters={"message_id": reply_to} if reply_to else None)
    if isinstance(r, dict) and r.get("message_id"):
        if len(_own) > 5000:
            _own.clear()
        _own[(bc, chat_id, r["message_id"])] = time.time()
    return r


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
    if c and time.time() - c[0] < 120:
        return c[1]
    rows = await db.select("gs_chat", {"bc": f"eq.{bc}", "chat_id": f"eq.{chat_id}"})
    data = dict(rows[0]["data"]) if rows else {}
    if c:  # перечитываем после истечения кэша — временные отметки из памяти не теряем
        for key in _TIMER_KEYS:
            if key in c[1]:
                data[key] = c[1][key]
    _chat[k] = (time.time(), data)
    return data


_TIMER_KEYS = {"last_clone", "last_afk", "last_autoreply"}  # временные отметки: не нужны после перезапуска


async def chat_set(bc, chat_id, **kw) -> dict:
    data = {**await chat_get(bc, chat_id), **kw}
    _chat[(bc, chat_id)] = (time.time(), data)  # кэш обновляем сразу — действует мгновенно
    if kw and set(kw) <= _TIMER_KEYS:
        return data  # только таймер — в базу не пишем, это было бы по записи на каждое сообщение
    await db.insert("gs_chat", {"bc": bc, "chat_id": chat_id, "data": data}, upsert="bc,chat_id", returning=False)
    return data


# ---------- кэш сообщений ----------
# Сообщения держим в памяти бота на MSG_TTL секунд. В Supabase их не пишем:
# это главный источник запросов (каждое сообщение = запрос). Удалённое сообщение находим в памяти.
# Минус: после перезапуска бота история сообщений обнуляется.
MSG_TTL = 2 * 3600
MSG_MAX = 20000
MSG_DB = False  # True — вернуть запись в gs_msgs (тогда расходуются запросы к Supabase)
_msg_mem: dict[tuple, tuple[float, dict]] = {}


def _prune(now: float) -> None:
    if len(_msg_mem) < MSG_MAX:
        return
    cutoff = now - MSG_TTL
    for k in [k for k, (ts, _) in _msg_mem.items() if ts < cutoff]:
        _msg_mem.pop(k, None)
    if len(_msg_mem) >= MSG_MAX:  # совсем переполнено — выкидываем самые старые
        for k in list(_msg_mem)[: MSG_MAX // 2]:
            _msg_mem.pop(k, None)


async def cache_msg(bc, chat_id, mid, owner_id, data: dict):
    now = time.time()
    _msg_mem[(bc, chat_id, mid)] = (now, data)
    _prune(now)
    if MSG_DB:
        await db.insert("gs_msgs", {"bc": bc, "chat_id": chat_id, "msg_id": mid, "owner_id": owner_id, "data": data},
                        upsert="bc,chat_id,msg_id", returning=False)


async def flush_msgs() -> None:
    """Совместимость: при MSG_DB=False писать нечего."""
    return None


async def msg_flush_loop() -> None:
    """Совместимость со старым запуском: ничего не делает, если запись в базу выключена."""
    while True:
        await asyncio.sleep(3600)


async def get_msg(bc, chat_id, mid):
    hit = _msg_mem.get((bc, chat_id, mid))
    if hit and time.time() - hit[0] < MSG_TTL:
        return hit[1]
    if not MSG_DB:
        return None
    rows = await db.select("gs_msgs", {"bc": f"eq.{bc}", "chat_id": f"eq.{chat_id}", "msg_id": f"eq.{mid}"})
    return rows[0]["data"] if rows else None


async def drop_msg(bc, chat_id, mid):
    _msg_mem.pop((bc, chat_id, mid), None)
    if MSG_DB:
        await db.delete("gs_msgs", {"bc": f"eq.{bc}", "chat_id": f"eq.{chat_id}", "msg_id": f"eq.{mid}"})


# ---------- отложенные задачи ----------
_JOB_NEXT = 0.0  # когда проверять очередь; 0 — проверить сейчас (например, после перезапуска)


def job_next() -> float:
    return _JOB_NEXT


def set_job_next(ts: float) -> None:
    global _JOB_NEXT
    _JOB_NEXT = ts


async def schedule(kind: str, delay_s: float, **payload):
    import datetime as dt
    await db.insert("gs_jobs", {"run_at": U.iso(U.now() + dt.timedelta(seconds=delay_s)), "kind": kind, "payload": payload},
                    returning=False)
    ts = time.time() + delay_s
    if _JOB_NEXT and ts < _JOB_NEXT:  # новая задача раньше текущей — будим планировщик вовремя
        set_job_next(ts)  # при _JOB_NEXT == 0 уже велено проверить сейчас — не трогаем
