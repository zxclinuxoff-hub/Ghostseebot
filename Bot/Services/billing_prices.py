import math

from ..config import PLANS


def price_for(u, plan: str) -> tuple[int, int]:
    """(цена в Stars с учётом скидки, процент скидки)."""
    base = PLANS[plan]["stars"]
    pct = int((u or {}).get(f"disc_{plan}", 0) or 0) if plan in ("m3", "y1") else 0
    return max(1, math.ceil(base * (100 - pct) / 100)), pct
