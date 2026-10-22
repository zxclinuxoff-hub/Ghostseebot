import asyncio
import logging
import time
import uuid
from contextvars import ContextVar

from ..db import db

log = logging.getLogger("ghostsee")
_tasks: set = set()

_corr_id: ContextVar[str] = ContextVar("corr_id", default="")
STARTED_AT = time.time()  # для аптайма в статусе


def new_correlation() -> str:
    cid = uuid.uuid4().hex[:12]
    _corr_id.set(cid)
    return cid


def get_correlation() -> str:
    return _corr_id.get()


def bg(coro):
    async def _run():
        try:
            await coro
        except Exception as e:
            log.warning("bg task failed: %s: %s", type(e).__name__, e)
    t = asyncio.create_task(_run())
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
    return t


def is_network_error(e: BaseException) -> bool:
    import httpx
    from ..db import NetworkError
    names = {"TelegramNetworkError", "TelegramRetryAfter", "ClientError", "ClientOSError",
             "ServerDisconnectedError", "TimeoutError", "ClientConnectorError", "ClientPayloadError"}
    return isinstance(e, (NetworkError, httpx.TimeoutException, httpx.TransportError,
                          asyncio.TimeoutError, ConnectionError)) or type(e).__name__ in names


# Обычные события (info) остаются в консоли Render и в базу не пишутся.
# Ошибки, предупреждения и события оплат/донатов/подарков сохраняются всегда.
KEEP_IN_DB = {"payment", "donation", "gift_bought", "gift_redeemed"}


async def _write(level, event, tg_id, details):
    if level == "info" and event not in KEEP_IN_DB:
        return
    try:
        await db.insert("gs_logs", {
            "level": level, "event": event, "tg_id": tg_id, "details": details,
        }, returning=False)
    except Exception as e:
        log.warning("log insert failed: %s", e)


async def audit(level: str, event: str, tg_id=None, *, service: str = "core",
                actor_id=None, target_id=None, correlation_id: str = "", **details):
    cid = correlation_id or get_correlation()
    getattr(log, {"warn": "warning"}.get(level, level), log.info)(
        "[%s] %s svc=%s actor=%s target=%s tg=%s %s",
        cid, event, service, actor_id, target_id, tg_id, details,
    )
    payload = {
        "service": service, "actor_id": actor_id,
        "target_id": target_id, "correlation_id": cid,
        **details,
    }
    bg(_write(level, event, tg_id, payload))
