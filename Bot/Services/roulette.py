import datetime as dt
import random

from . import users as U

# (код, вес %) — суммарно 100
OUTCOMES = [("d1", 70), ("d2", 10), ("d3", 5), ("disc_y1", 7), ("disc_m3", 8)]


async def spin(u: dict) -> tuple[bool, str]:
    last = U.parse(u.get("last_roulette"))
    if last and U.now() - last < dt.timedelta(hours=24):
        left = dt.timedelta(hours=24) - (U.now() - last)
        h, m = divmod(int(left.total_seconds() // 60), 60)
        return False, f"⏳ Следующая попытка через <b>{h} ч {m} мин</b>."
    code = random.choices([o[0] for o in OUTCOMES], weights=[o[1] for o in OUTCOMES])[0]
    uid = u["tg_id"]
    if code.startswith("d"):
        days = int(code[1])
        await U.grant(uid, days)
        await U.patch_user(uid, last_roulette=U.iso(U.now()))
        return True, f"🎉 Выигрыш: <b>+{days} дн.</b> подписки!"
    plan = code.split("_")[1]
    pct = random.choice(range(10, 51, 5)) if plan == "y1" else random.choice(range(5, 21, 5))
    cur = int(u.get(f"disc_{plan}") or 0)
    pct = max(pct, cur)
    await U.patch_user(uid, **{f"disc_{plan}": pct}, last_roulette=U.iso(U.now()))
    title = "годовую" if plan == "y1" else "3-месячную"
    return True, f"🎉 Выигрыш: скидка <b>{pct}%</b> на {title} подписку! Применится при покупке в разделе «Купить»."
