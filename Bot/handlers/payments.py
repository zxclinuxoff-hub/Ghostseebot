from aiogram import Bot, F, Router
from aiogram.types import Message, PreCheckoutQuery

from ..config import PLANS
from ..services import billing
from ..services import users as U

router = Router(name="payments")


@router.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    u = await U.get_user(q.from_user.id)
    ok = not (u and u.get("banned")) and q.invoice_payload.split(":")[1:2] and q.invoice_payload.split(":")[1] in PLANS
    await q.answer(ok=bool(ok), error_message=None if ok else "Покупка недоступна")


@router.message(F.successful_payment)
async def paid(m: Message, bot: Bot):
    await billing.on_paid(bot, m)
