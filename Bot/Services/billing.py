from aiogram import Bot
from aiogram.types import LabeledPrice, Message

from ..config import PLANS, cfg
from ..db import DBError, db
from . import users as U
from .billing_prices import price_for
from .logs import audit


async def send_invoice(bot: Bot, chat_id: int, u: dict, plan: str):
    stars, pct = price_for(u, plan)
    p = PLANS[plan]
    desc = "Подписка «Всё включено»: удалённые и изменённые сообщения, временные фото, все команды."
    if pct:
        desc += f" Скидка {pct}% из рулетки."
    await bot.send_invoice(
        chat_id=chat_id, title=f"GhostSee — {p['title']}", description=desc,
        payload=f"sub:{plan}:{pct}", currency="XTR", prices=[LabeledPrice(label=p["title"], amount=stars)],
        provider_token="",
    )


async def on_paid(bot: Bot, m: Message):
    sp = m.successful_payment
    uid = m.from_user.id
    try:
        _, plan, _pct = sp.invoice_payload.split(":")
        p = PLANS[plan]
    except Exception:
        await audit("error", "pay_bad_payload", uid, payload=sp.invoice_payload)
        return
    u, _ = await U.ensure_user(m.from_user)

    partner, share = None, 0
    if u.get("partner_code"):
        rows = await db.select("gs_partners", {"code": f"eq.{u['partner_code']}"})
        if rows:
            partner = rows[0]
            share = sp.total_amount * partner["percent"] // 100
    try:
        await db.insert("gs_payments", {
            "tg_id": uid, "plan": plan, "stars": sp.total_amount, "base_stars": p["stars"],
            "charge_id": sp.telegram_payment_charge_id,
            "partner_code": partner["code"] if partner else None, "partner_share": share,
        }, returning=False)
    except DBError as e:
        if "23505" in str(e) or "duplicate" in str(e).lower():
            return  # повторная доставка апдейта
        await audit("error", "pay_record_failed", uid, err=str(e)[:200])  # платёж есть — доступ всё равно выдаём

    u = await U.grant(uid, p["days"])
    if plan in ("m3", "y1") and u.get(f"disc_{plan}"):
        u = await U.patch_user(uid, **{f"disc_{plan}": 0})
    await audit("info", "payment", uid, plan=plan, stars=sp.total_amount, partner=partner["code"] if partner else None)

    await m.answer(f"✅ <b>Оплата прошла, спасибо!</b>\nПодписка до <b>{U.fmt_dt(u['sub_until'])}</b> (МСК).")
    for aid in cfg.admin_ids:
        try:
            await bot.send_message(aid, f"💰 <b>Оплата</b>: {m.from_user.full_name} (<code>{uid}</code>) — {p['title']}, {sp.total_amount}⭐\n"
                                        f"charge: <code>{sp.telegram_payment_charge_id}</code>")
        except Exception:
            pass
    if partner and share:
        try:
            await bot.send_message(partner["tg_id"], f"🤝 Партнёрское начисление: +{share}⭐ (покупка по твоей ссылке)")
        except Exception:
            pass
