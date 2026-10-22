"""Подарочная подписка: покупка звёздами → одноразовая ссылка → активация у получателя."""
from __future__ import annotations

from aiogram import Bot
from aiogram.types import LabeledPrice, Message

from ..config import PLANS, cfg
from ..db import DBError, db
from . import gift_rules as R
from . import users as U
from .billing_prices import price_for
from .logs import audit

INVALID = "❌ Ссылка недействительна или устарела."


async def send_invoice(bot: Bot, chat_id: int, u: dict, plan: str) -> None:
    stars, pct = price_for(u, plan)
    p = PLANS[plan]
    await bot.send_invoice(
        chat_id=chat_id, title=f"GhostSee — подарок: {p['title']}",
        description="Подарочная подписка «Всё включено». Получатель активирует её по ссылке.",
        payload=R.make_payload(plan, pct), currency="XTR",
        prices=[LabeledPrice(label=f"Подарок: {p['title']}", amount=stars)], provider_token="",
    )


async def on_paid(bot: Bot, m: Message) -> None:
    """Создаём подарок один раз (charge_id уникален) и отдаём покупателю ссылку."""
    sp = m.successful_payment
    uid = m.from_user.id
    plan = R.parse_payload(sp.invoice_payload, PLANS)
    if plan is None or sp.currency != "XTR" or sp.total_amount <= 0:
        await audit("error", "gift_bad_payload", uid, payload=(sp.invoice_payload or "")[:64])
        return
    code = R.new_code()
    try:
        await db.insert("gs_gifts", {
            "code": code, "buyer_id": uid, "plan": plan, "stars": sp.total_amount,
            "charge_id": sp.telegram_payment_charge_id,
        }, returning=False)
    except DBError as e:
        if "23505" in str(e) or "duplicate" in str(e).lower():
            return  # повторная доставка того же платежа — ссылку уже отдали
        await audit("error", "gift_record_failed", uid, err=str(e)[:200])
        return await m.answer("⚠️ Оплата прошла, но подарок не создан. Напиши в тикет, мы его восстановим.")

    await audit("info", "gift_bought", uid, plan=plan, stars=sp.total_amount)
    await m.answer(
        f"🎁 <b>Подарок готов!</b>\nОтправь другу эту ссылку. Он откроет её в боте, и подписка "
        f"«{PLANS[plan]['title']}» активируется у него. Ссылка одноразовая.\n\n"
        f"<code>{R.link(code, cfg.bot_username)}</code>")
    for aid in cfg.admin_ids:
        try:
            await bot.send_message(aid, f"🎁 <b>Подарок</b>: {m.from_user.full_name} (<code>{uid}</code>) — "
                                        f"{PLANS[plan]['title']}, {sp.total_amount}⭐")
        except Exception:
            pass


async def redeem(bot: Bot, m: Message, code: str, uid: int) -> None:
    """Активация по ссылке. Один подарок — одна активация: захват делает одна атомарная операция."""
    if not R.valid_code(code):
        return await m.answer(INVALID)
    try:
        rows = await db.update("gs_gifts", {"code": f"eq.{code}", "redeemed_by": "is.null"},
                               {"redeemed_by": uid, "redeemed_at": U.iso(U.now())})
    except DBError as e:
        await audit("error", "gift_claim_failed", uid, err=str(e)[:200])
        return await m.answer("⚠️ Не удалось активировать подарок, попробуй через минуту.")
    if not rows:
        try:
            exists = await db.select("gs_gifts", {"code": f"eq.{code}"})
        except DBError:
            exists = []
        return await m.answer("🎁 Этот подарок уже активирован." if exists else INVALID)

    g = rows[0]
    plan = g["plan"]
    try:
        u = await U.grant(uid, PLANS[plan]["days"])
    except Exception as e:
        # подписку не выдали — возвращаем ссылку, чтобы её можно было открыть снова
        await audit("error", "gift_grant_failed", uid, err=str(e)[:200])
        try:
            await db.update("gs_gifts", {"code": f"eq.{code}"}, {"redeemed_by": None, "redeemed_at": None})
        except DBError:
            pass
        return await m.answer("⚠️ Не удалось активировать подарок, попробуй через минуту. Ссылка сохранена.")

    await audit("info", "gift_redeemed", uid, plan=plan)
    await m.answer(f"🎁 <b>Подарок активирован!</b>\nПодписка до <b>{U.fmt_dt(u['sub_until'])}</b> (МСК).")
    if g.get("buyer_id") and g["buyer_id"] != uid:
        try:
            await bot.send_message(g["buyer_id"], f"🎁 Твой подарок активирован: подписка "
                                                  f"«{PLANS[plan]['title']}» у получателя.")
        except Exception:
            pass
