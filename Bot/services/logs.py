import asyncio
import logging

from ..db import db

log = logging.getLogger("ghostsee")
_tasks: set = set()


def bg(coro):
    """Запустить в фоне (не задерживая ответ пользователю). Ошибки — только в консоль."""
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
    names = {"TelegramNetworkError", "TelegramRetryAfter", "ClientError", "ClientOSError", "ServerDisconnectedError",
             "TimeoutError", "ClientConnectorError", "ClientPayloadError"}
    return isinstance(e, (NetworkError, httpx.TimeoutException, httpx.TransportError, asyncio.TimeoutError, ConnectionError)) \
        or type(e).__name__ in names


async def _write(level, event, tg_id, details):
    try:
        await db.insert("gs_logs", {"level": level, "event": event, "tg_id": tg_id, "details": details}, returning=False)
    except Exception as e:  # лог не должен ронять бота
        log.warning("log insert failed: %s", e)


async def audit(level: str, event: str, tg_id=None, **details):
    """Лог в консоль + таблицу gs_logs (в фоне; текст сообщений сюда не пишем)."""
    getattr(log, {"warn": "warning"}.get(level, level), log.info)("%s tg=%s %s", event, tg_id, details)
    bg(_write(level, event, tg_id, details))
