"""Донат Telegram Stars: счёт, проверка и учёт. Подписку и тариф не трогает."""
from __future__ import annotations

from aiogram import Bot
from aiogram.types import LabeledPrice, Message

from ..config import cfg
from ..db import DBError, db
from . import donate_rules as R
from .logs import audit


async def send_invoice(bot: Bot, chat_id: int, stars: int) -> None:
    await bot.send_invoice(
        chat_id=chat_id,
        title="Поддержка GhostSeeBot",
        description="Добровольный донат Telegram Stars на развитие проекта. Подписку не продлевает.",
        payload=R.make_payload(stars),
        currency=R.CURRENCY,
        prices=[LabeledPrice(label=f"Донат {stars}⭐", amount=stars)],
        provider_token="",
    )


async def on_paid(bot: Bot, m: Message) -> None:
    """Засчитываем донат только здесь — по событию successful_payment, и только один раз (charge_id — ключ)."""
    sp = m.successful_payment
    uid = m.from_user.id
    if not R.validate_payment(sp.invoice_payload, sp.currency, sp.total_amount):
        await audit("error", "donate_bad_payment", uid, payload=(sp.invoice_payload or "")[:64])
        return
    try:
        await db.insert("gs_donations", {
            "charge_id": sp.telegram_payment_charge_id,
            "tg_id": uid,
            "stars": sp.total_amount,
            "payload": sp.invoice_payload,
        }, returning=False)
    except DBError as e:
        if "23505" in str(e) or "duplicate" in str(e).lower():
            return  # повторная доставка того же платежа — уже засчитан и поблагодарён
        await audit("error", "donate_record_failed", uid, err=str(e)[:200])

    await audit("info", "donation", uid, stars=sp.total_amount)
    await m.answer("🖤 Спасибо за поддержку GhostSeeBot! Твой вклад помогает развивать проект")
    for aid in cfg.admin_ids:
        try:
            await bot.send_message(aid, f"⭐ <b>Донат</b>: {m.from_user.full_name} (<code>{uid}</code>) — {sp.total_amount}⭐")
        except Exception:
            pass
