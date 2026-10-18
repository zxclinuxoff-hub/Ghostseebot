import datetime as dt
import random

from . import users as U
from .logs import audit

# (код, вес %) — суммарно 100
OUTCOMES = [("d1", 5), ("d2", 1), ("d3", 0.5), ("disc_m3", 8), ("disc_y1", 5), ("none", 80.5)]
FREE_DAYS = {"d1": 1, "d2": 2, "d3": 3}
DISC_TTL = dt.timedelta(hours=2, minutes=30)  # скидка живёт 2.5 часа


async def spin(u: dict) -> tuple[bool, str]:
    last = U.parse(u.get("last_roulette"))
    if last and U.now() - last < dt.timedelta(hours=24):
        left = dt.timedelta(hours=24) - (U.now() - last)
        h, m = divmod(int(left.total_seconds() // 60), 60)
        return False, f"⏳ Следующая попытка через <b>{h} ч {m} мин</b>."
    code = random.choices([o[0] for o in OUTCOMES], weights=[o[1] for o in OUTCOMES])[0]
    await audit("info", "roulette_result", u["tg_id"], outcome=code)
    uid = u["tg_id"]
    if code == "none":
        await U.patch_user(uid, last_roulette=U.iso(U.now()))
        return True, "😔 Сегодня не повезло. Попробуй завтра — шанс есть всегда!"
    if code in FREE_DAYS:
        days = FREE_DAYS[code]
        await U.grant(uid, days)
        await U.patch_user(uid, last_roulette=U.iso(U.now()))
        return True, f"🎉 Джекпот! <b>+{days} дн.</b> подписки бесплатно!"
    plan = code.split("_")[1]  # disc_y1 → y1, disc_m3 → m3
    pct = random.choice(range(10, 36, 5)) if plan == "y1" else random.choice(range(5, 21, 5))
    pct = max(pct, int(u.get(f"disc_{plan}") or 0))
    expires = U.now() + DISC_TTL
    await U.patch_user(
        uid,
        **{f"disc_{plan}": pct, f"disc_{plan}_until": U.iso(expires)},
        last_roulette=U.iso(U.now()),
    )
    title = "годовую" if plan == "y1" else "3-месячную"
    until_s = expires.strftime("%H:%M")
    return True, (
        f"🎉 Выигрыш: скидка <b>{pct}%</b> на {title} подписку!\n"
        f"⏱ Действует <b>2.5 часа</b> (до {until_s}).\n"
        f"Применится при покупке в разделе «Подписка»."
    )


async def active_discount(u: dict, plan: str) -> int:
    """Актуальный % скидки с учётом срока 2.5 ч. Истёкшие обнуляет."""
    if plan not in ("m3", "y1"):
        return 0
    pct = int((u or {}).get(f"disc_{plan}", 0) or 0)
    if pct <= 0:
        return 0
    until = U.parse((u or {}).get(f"disc_{plan}_until"))
    if until and U.now() > until:
        # сгорела
        try:
            await U.patch_user(u["tg_id"], **{f"disc_{plan}": 0, f"disc_{plan}_until": None})
        except Exception:
            pass
        return 0
    # старые скидки без until — даём 2.5ч с момента last_roulette или считаем активными один раз
    if not until:
        return pct
    return pct
