"""Правила доната Telegram Stars (без зависимостей — легко тестировать).

Сумма — любое целое число от MIN_STARS до MAX_STARS (предел Telegram).
Донат НЕ связан с тарифом: отдельный префикс payload («donate:»), отдельная таблица gs_donations.
"""
from __future__ import annotations

import re
import secrets

MIN_STARS = 1
MAX_STARS = 10_000  # предел Telegram для одного счёта в звёздах; больше бот не может выставить
PREFIX = "donate:"
CURRENCY = "XTR"
COMMENT_MAX = 200
# donate:<сумма>:<12 hex-символов> — токен связывает счёт с комментарием в gs_donation_intents
_PAYLOAD_RE = re.compile(r"^donate:(\d{1,3}):([0-9a-f]{12})$")
_AMOUNT_RE = re.compile(r"\d{1,5}")


def valid_amount(n) -> bool:
    return isinstance(n, int) and MIN_STARS <= n <= MAX_STARS


def parse_amount(text: str | None) -> int | None:
    """Сумма, которую написал пользователь: только цифры, от 1 до MAX_STARS."""
    s = (text or "").strip()
    if not _AMOUNT_RE.fullmatch(s):
        return None
    n = int(s)
    return n if valid_amount(n) else None


def new_token() -> str:
    return secrets.token_hex(6)


def make_payload(stars: int, token: str | None = None) -> str:
    if not valid_amount(stars):
        raise ValueError(f"недопустимая сумма доната: {stars}")
    return f"{PREFIX}{stars}:{token or new_token()}"


def is_donation(payload: str | None) -> bool:
    return bool(payload) and payload.startswith(PREFIX)


def parse_payload(payload: str | None) -> int | None:
    """Сумму доната из payload или None, если payload не донатный или подделан."""
    m = _PAYLOAD_RE.match(payload or "")
    if not m:
        return None
    stars = int(m.group(1))
    return stars if valid_amount(stars) else None


def token_of(payload: str | None) -> str | None:
    m = _PAYLOAD_RE.match(payload or "")
    return m.group(2) if m else None


def validate_payment(payload: str | None, currency: str | None, total_amount: int | None) -> bool:
    """Проверка суммы, валюты и типа платежа — и для pre_checkout, и для successful_payment."""
    stars = parse_payload(payload)
    return stars is not None and currency == CURRENCY and total_amount == stars


def clean_comment(text: str | None) -> str | None:
    """Комментарий: одна строка, не длиннее COMMENT_MAX символов. Пусто — None."""
    if not text:
        return None
    s = " ".join(text.split())[:COMMENT_MAX]
    return s or None
