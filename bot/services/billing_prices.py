import math

from ..config import PLANS
from . import roulette


def price_for(u, plan: str) -> tuple[int, int]:
    """(цена в Stars с учётом скидки, процент скидки)."""
    base = PLANS[plan]["stars"]
    pct = 0
    if plan in ("m3", "y1") and u:
        pct = int(u.get(f"disc_{plan}", 0) or 0)
        until_s = u.get(f"disc_{plan}_until")
        if until_s:
            from .users import parse, now
            until = parse(until_s)
            if until and now() > until:
                pct = 0
        elif pct:
            # старые скидки без until — не вечные: если last_roulette > 2.5ч назад, 0
            from .users import parse, now
            import datetime as dt
            lr = parse(u.get("last_roulette"))
            if lr and now() - lr > dt.timedelta(hours=2, minutes=30):
                pct = 0
    return max(1, math.ceil(base * (100 - pct) / 100)), pct
