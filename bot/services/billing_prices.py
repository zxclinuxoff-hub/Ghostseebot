import math

from ..config import PLANS
from . import roulette


def price_for(u, plan: str) -> tuple[int, int]:
    """(цена в Stars с учётом скидки, процент скидки)."""
    base = PLANS[plan]["stars"]
    # синхронная обёртка: если until истёк — 0 (обновление в БД ленивое через spin/active)
    pct = 0
    if plan in ("m3", "y1") and u:
        pct = int(u.get(f"disc_{plan}", 0) or 0)
        until_s = u.get(f"disc_{plan}_until")
        if until_s:
            import datetime as dt
            from .users import parse, now
            until = parse(until_s)
            if until and now() > until:
                pct = 0
    return max(1, math.ceil(base * (100 - pct) / 100)), pct
