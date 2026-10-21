from aiogram import Bot, F, Router
from aiogram.types import Message, PreCheckoutQuery

from ..config import PLANS
from ..services import billing, donate
from ..services import donate_rules as DR
from ..services import users as U

router = Router(name="payments")


@router.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    if DR.is_donation(q.invoice_payload):  # донат: сумма и валюта должны совпасть с payload
        ok = DR.validate_payment(q.invoice_payload, q.currency, q.total_amount)
        return await q.answer(ok=bool(ok), error_message=None if ok else "Донат недоступен")
    u = await U.get_user(q.from_user.id)
    ok = not (u and u.get("banned")) and q.invoice_payload.split(":")[1:2] and q.invoice_payload.split(":")[1] in PLANS
    await q.answer(ok=bool(ok), error_message=None if ok else "Покупка недоступна")


@router.message(F.successful_payment)
async def paid(m: Message, bot: Bot):
    if DR.is_donation(m.successful_payment.invoice_payload):
        return await donate.on_paid(bot, m)  # донат не продлевает подписку
    await billing.on_paid(bot, m)
