import logging

from ..db import db

log = logging.getLogger("ghostsee")


async def audit(level: str, event: str, tg_id=None, **details):
    """Лог в консоль + таблицу gs_logs (текст сообщений сюда не пишем)."""
    getattr(log, {"warn": "warning"}.get(level, level), log.info)("%s tg=%s %s", event, tg_id, details)
    try:
        await db.insert("gs_logs", {"level": level, "event": event, "tg_id": tg_id, "details": details}, returning=False)
    except Exception as e:  # лог не должен ронять бота
        log.error("log insert failed: %s", e)
