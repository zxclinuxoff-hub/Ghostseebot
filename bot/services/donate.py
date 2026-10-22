"""Донат Telegram Stars: счёт, проверка и учёт. Подписку и тариф не трогает."""
from __future__ import annotations

from html import escape

from aiogram import Bot
from aiogram.types import LabeledPrice, Message

from ..config import cfg
from ..db import DBError, db
from . import donate_rules as R
from .logs import audit


async def send_invoice(bot: Bot, chat_id: int, uid: int, stars: int, comment: str | None) -> None:
    """Сохраняем комментарий под токеном, а в счёт кладём только сумму и токен (лимит payload — 128 байт)."""
    token = R.new_token()
    await db.insert("gs_donation_intents", {
        "token": token, "tg_id": uid, "stars": stars, "comment": comment,
    }, returning=False)
    await bot.send_invoice(
        chat_id=chat_id,
        title="Поддержка GhostSeeBot",
        description="Добровольный донат Telegram Stars на развитие проекта. Подписку не продлевает.",
        payload=R.make_payload(stars, token),
        currency=R.CURRENCY,
        prices=[LabeledPrice(label=f"Донат {stars}⭐", amount=stars)],
        provider_token="",
    )


async def _comment_for(token: str | None) -> str | None:
    if not token:
        return None
    try:
        rows = await db.select("gs_donation_intents", {"token": f"eq.{token}"})
    except DBError:
        return None
    return rows[0].get("comment") if rows else None


async def on_paid(bot: Bot, m: Message) -> None:
    """Засчитываем донат только здесь — по событию successful_payment, и только один раз (charge_id — ключ)."""
    sp = m.successful_payment
    uid = m.from_user.id
    if not R.validate_payment(sp.invoice_payload, sp.currency, sp.total_amount):
        await audit("error", "donate_bad_payment", uid, payload=(sp.invoice_payload or "")[:64])
        return
    comment = await _comment_for(R.token_of(sp.invoice_payload))
    try:
        await db.insert("gs_donations", {
            "charge_id": sp.telegram_payment_charge_id,
            "tg_id": uid,
            "stars": sp.total_amount,
            "payload": sp.invoice_payload,
            "comment": comment,
        }, returning=False)
    except DBError as e:
        if "23505" in str(e) or "duplicate" in str(e).lower():
            return  # повторная доставка того же платежа — уже засчитан и поблагодарён
        await audit("error", "donate_record_failed", uid, err=str(e)[:200])

    await audit("info", "donation", uid, stars=sp.total_amount)
    await m.answer("🖤 Спасибо за поддержку GhostSeeBot! Твой вклад помогает развивать проект")
    text = f"🖤 <b>Донат</b>: {escape(m.from_user.full_name)} (<code>{uid}</code>) — {sp.total_amount}⭐"
    if comment:
        text += f"\n💬 {escape(comment)}"
    for aid in cfg.admin_ids:
        try:
            await bot.send_message(aid, text)
        except Exception:
            pass
