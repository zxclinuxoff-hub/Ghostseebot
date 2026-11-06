from aiogram import Bot, F, Router
from aiogram.types import Message, PreCheckoutQuery

from ..config import PLANS
from ..services import billing, donate, gifts
from ..services.billing_prices import price_for
from ..services import gift_rules as GR
from ..services import donate_rules as DR
from ..services import users as U
from ..services import wheel as W

router = Router(name="payments")


@router.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    if q.invoice_payload.startswith("wheelpack:"):  # пакет прокрутов
        ok = q.currency == "XTR" and await W.can_pack(q.from_user.id, int(q.invoice_payload.split(":")[1]), q.total_amount)
        return await q.answer(ok=bool(ok), error_message=None if ok else "Пакет недоступен")
    if q.invoice_payload.startswith("wheel:"):  # прокрут колеса фортуны
        ok = q.currency == "XTR" and q.total_amount == W.PRICE and await W.can_pay(q.from_user.id)
        return await q.answer(ok=bool(ok), error_message=None if ok else "Лимит прокрутов на сегодня исчерпан")
    if GR.is_gift(q.invoice_payload):
        u = await U.get_user(q.from_user.id)
        ok = (not (u and u.get("banned")) and q.currency == "XTR"
              and GR.parse_payload(q.invoice_payload, PLANS) is not None)
        return await q.answer(ok=bool(ok), error_message=None if ok else "Подарок недоступен")
    if DR.is_donation(q.invoice_payload):  # донат: сумма и валюта должны совпасть с payload
        ok = DR.validate_payment(q.invoice_payload, q.currency, q.total_amount)
        return await q.answer(ok=bool(ok), error_message=None if ok else "Донат недоступен")
    parts = q.invoice_payload.split(":")
    u = await U.get_user(q.from_user.id)
    ok = False
    if len(parts) == 3 and parts[0] == "sub" and parts[1] in PLANS and q.currency == "XTR" and not (u and u.get("banned")):
        try:
            expected, pct = price_for(u or {}, parts[1])
            ok = int(parts[2]) == int(pct) and q.total_amount == int(expected)
        except Exception:
            ok = False
    await q.answer(ok=bool(ok), error_message=None if ok else "Сумма или тариф покупки не совпадает. Создай новый счёт.")


@router.message(F.successful_payment)
async def paid(m: Message, bot: Bot):
    if m.successful_payment.invoice_payload.startswith(("wheel:", "wheelpack:")):
        return await W.on_paid(bot, m)
    if GR.is_gift(m.successful_payment.invoice_payload):
        return await gifts.on_paid(bot, m)  # подарок: подписка не выдаётся покупателю
    if DR.is_donation(m.successful_payment.invoice_payload):
        return await donate.on_paid(bot, m)  # донат не продлевает подписку
    await billing.on_paid(bot, m)
