import datetime as dt
import random

from . import users as U

# (код, вес %) — суммарно 100. Бесплатные дни — очень редкие, чаще всего «не повезло».
OUTCOMES = [("d1", 5), ("d2", 1), ("d3", 0.5), ("disc_m3", 8), ("disc_y1", 5), ("none", 80.5)]
FREE_DAYS = {"d1": 1, "d2": 2, "d3": 3}


async def spin(u: dict) -> tuple[bool, str]:
    last = U.parse(u.get("last_roulette"))
    if last and U.now() - last < dt.timedelta(hours=24):
        left = dt.timedelta(hours=24) - (U.now() - last)
        h, m = divmod(int(left.total_seconds() // 60), 60)
        return False, f"⏳ Следующая попытка через <b>{h} ч {m} мин</b>."
    code = random.choices([o[0] for o in OUTCOMES], weights=[o[1] for o in OUTCOMES])[0]
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
    pct = random.choice(range(10, 51, 5)) if plan == "y1" else random.choice(range(5, 21, 5))
    pct = max(pct, int(u.get(f"disc_{plan}") or 0))
    await U.patch_user(uid, **{f"disc_{plan}": pct}, last_roulette=U.iso(U.now()))
    title = "годовую" if plan == "y1" else "3-месячную"
    return True, f"🎉 Выигрыш: скидка <b>{pct}%</b> на {title} подписку! Применится при покупке в разделе «Подписка»."
