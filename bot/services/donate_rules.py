"""Правила доната Telegram Stars (без зависимостей — легко тестировать).

Донат НЕ связан с тарифом: отдельный префикс payload («donate:»), отдельная таблица gs_donations.
"""
from __future__ import annotations

import re
import secrets

DONATE_AMOUNTS: tuple[int, ...] = (1, 2, 5, 10)
PREFIX = "donate:"
CURRENCY = "XTR"
# donate:<сумма>:<12 hex-символов> — уникальный id счёта, чтобы не путать платежи между собой
_PAYLOAD_RE = re.compile(r"^donate:(\d{1,3}):([0-9a-f]{12})$")


def make_payload(stars: int) -> str:
    if stars not in DONATE_AMOUNTS:
        raise ValueError(f"недопустимая сумма доната: {stars}")
    return f"{PREFIX}{stars}:{secrets.token_hex(6)}"


def is_donation(payload: str | None) -> bool:
    return bool(payload) and payload.startswith(PREFIX)


def parse_payload(payload: str | None) -> int | None:
    """Сумму доната из payload или None, если payload не донатный или подделан."""
    m = _PAYLOAD_RE.match(payload or "")
    if not m:
        return None
    stars = int(m.group(1))
    return stars if stars in DONATE_AMOUNTS else None


def validate_payment(payload: str | None, currency: str | None, total_amount: int | None) -> bool:
    """Проверка сумы, валюты и типа платежа — и для pre_checkout, и для successful_payment."""
    stars = parse_payload(payload)
    return stars is not None and currency == CURRENCY and total_amount == stars
