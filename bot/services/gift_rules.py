"""Правила подарочной подписки (без зависимостей — легко тестировать)."""
from __future__ import annotations

import re
import secrets

PREFIX = "gift:"
_PAYLOAD_RE = re.compile(r"^gift:([a-z0-9]{1,8}):(\d{1,3})$")
_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")  # допустимые символы параметра /start


def is_gift(payload: str | None) -> bool:
    return bool(payload) and payload.startswith(PREFIX)


def make_payload(plan: str, pct: int) -> str:
    return f"{PREFIX}{plan}:{int(pct)}"


def parse_payload(payload: str | None, plans) -> str | None:
    """Тариф из payload или None, если payload подделан или тариф неизвестен."""
    m = _PAYLOAD_RE.match(payload or "")
    if not m or m.group(1) not in plans:
        return None
    return m.group(1)


def new_code() -> str:
    return secrets.token_urlsafe(9)  # 12 символов


def valid_code(code: str | None) -> bool:
    return bool(_CODE_RE.fullmatch(code or ""))


def link(code: str, bot_username: str) -> str:
    return f"https://t.me/{bot_username}?start=gift_{code}"
