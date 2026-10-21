"""Правила исключений для .afk (без зависимостей — легко тестировать)."""
from __future__ import annotations

import math
import re

PAGE_SIZE = 8
_ID_RE = re.compile(r"\d{5,15}")


def parse_partner_id(text: str | None) -> int | None:
    """Telegram ID собеседника: только цифры, 5–15 знаков, без знаков и пробелов внутри."""
    s = (text or "").strip()
    if not _ID_RE.fullmatch(s):
        return None
    value = int(s)
    return value if value > 0 else None


def page_bounds(total: int, page: int, size: int = PAGE_SIZE) -> tuple[int, int, int]:
    """Возвращает (номер страницы, всего страниц, смещение). Номер страницы зажимается в допустимый диапазон."""
    pages = max(1, math.ceil(total / size))
    page = min(max(1, page), pages)
    return page, pages, (page - 1) * size
