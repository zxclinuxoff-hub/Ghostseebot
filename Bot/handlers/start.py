from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton as B, Message

from .. import keyboards as K
from ..config import PLANS, cfg
from ..db import db
from ..services import billing, referrals, roulette
from ..services import users as U
from ..services.billing_prices import price_for
from ..services.logs import audit
from ..texts import HELP_CMDS

router = Router(name="start")
ASSETS = Path(__file__).resolve().parents[2] / "assets"
_fid: dict[str, str] = {}

START_CAPTION = (
    "👻 <b>GhostSee</b> — подключи бота к аккаунту\n\n"
    "1️⃣ Настройки → <b>Автоматизация чатов</b>\n"
    f"2️⃣ Введи <code>@{cfg.bot_username}</code> → <b>Добавить</b>\n"
    "3️⃣ Выдай права: читать, отвечать, удалять сообщения\n\n"
    f"🎁 {cfg.trial_days} дней бесплатно — уже включены."
)


def main_caption(u) -> str:
    st = (f"✅ Подписка до <b>{U.fmt_dt(u['sub_until'])}</b> (осталось {U.days_left(u)} дн.)"
          if U.is_active(u) else "⏸ Подписка закончилась — бот на паузе")
    return f"<b>👻 GHOSTSEEBOT</b>\n<i>вижу то, что исчезает</i>\n\n{st}"


def _banner(name: str) -> Path:
    for ext in ("jpg", "jpeg", "png"):
        p = ASSETS / f"{name}.{ext}"
        if p.exists():
            return p
    raise FileNotFoundError(f"нет баннера assets/{name}.(jpg|png)")


async def send_banner(target: Message, name: str, caption: str, kb):
    photo = _fid.get(name) or FSInputFile(_banner(name))
    msg = await target.answer_photo(photo, caption=caption, reply_markup=kb)
    if name not in _fid and msg.photo:
        _fid[name] = msg.photo[-1].file_id
    return msg


async def show(cb: CallbackQuery, text: str, kb):
    msg = cb.message
    try:
        if msg.photo:
            await msg.edit_caption(caption=text, reply_markup=kb)
        else:
            await msg.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        if "not modified" not in str(e):
            await msg.answer(text, reply_markup=kb)


# ---------------- /start ----------------
@router.message(CommandStart())
async def cmd_start(m: Message, command: CommandObject, bot: Bot):
    u, is_new = await U.ensure_user(m.from_user)
    if is_new:
        await audit("info", "user_new", m.from_user.id, args=command.args)
        a = command.args or ""
        if a.startswith("ref_") and a[4:].isdigit():
            rid = int(a[4:])
            if rid != m.from_user.id and await U.get_user(rid):
                await referrals.register(m.from_user.id, rid)
        elif a.startswith("p_"):
            code = a[2:].lower()
            if await db.select("gs_partners", {"code": f"eq.{code}"}):
                await U.patch_user(m.from_user.id, partner_code=code)

    try:
        await send_banner(m, "banner_start", START_CAPTION, K.start_kb(True))
    except TelegramBadRequest as e:  # tg://settings/... может не приниматься как URL кнопки
        await audit("warn", "start_btn_url_rejected", m.from_user.id, err=str(e)[:120])
        try:
            await send_banner(m, "banner_start", START_CAPTION, K.start_kb(False))
        except Exception:
            await m.answer(START_CAPTION, reply_markup=K.start_kb(False))
    except Exception as e:  # нет файла баннера и т.п. — не роняем /start
        await audit("error", "start_banner_failed", m.from_user.id, err=str(e)[:200])
        await m.answer(START_CAPTION, reply_markup=K.start_kb(False))

    res = await referrals.try_credit(bot, m.from_user.id)
    if res == "not_subscribed":
        await m.answer(f"📢 Подпишись на канал {cfg.channel}, чтобы твой друг получил бонус за приглашение.", reply_markup=K.channel_kb())


@router.message(Command("menu"))
async def cmd_menu(m: Message):
    u, _ = await U.ensure_user(m.from_user)
    await m.answer(main_caption(u), reply_markup=K.main_menu())


@router.message(Command("buy"))
async def cmd_buy(m: Message):
    u, _ = await U.ensure_user(m.from_user)
    await m.answer(buy_text(), reply_markup=K.buy_kb(u))


@router.callback_query(F.data == "check_sub")
async def cb_check(cb: CallbackQuery, bot: Bot):
    res = await referrals.try_credit(bot, cb.from_user.id)
    await cb.answer({"ok": "✅ Подписка подтверждена, бонус начислен!", "none": "Всё уже в порядке 👍",
                     "not_subscribed": "Ты ещё не подписан на канал", "error": "Не удалось проверить, попробуй позже"}[res], show_alert=True)


# ---------------- меню ----------------
@router.callback_query(F.data == "menu")
async def cb_menu(cb: CallbackQuery):
    u, _ = await U.ensure_user(cb.from_user)
    await cb.answer()
    await cb.message.answer(main_caption(u), reply_markup=K.main_menu())


@router.callback_query(F.data == "back")
async def cb_back(cb: CallbackQuery):
    u, _ = await U.ensure_user(cb.from_user)
    await cb.answer()
    await show(cb, main_caption(u), K.main_menu())


async def partner_block(uid: int) -> str:
    rows = await db.select("gs_partners", {"tg_id": f"eq.{uid}"})
    out = []
    for p in rows:
        users = await db.count("gs_users", {"partner_code": f"eq.{p['code']}"})
        pays = await db.select_all("gs_payments", {"partner_code": f"eq.{p['code']}"})
        earned = sum(x["partner_share"] or 0 for x in pays)
        out.append(f"\n🤝 <b>Партнёр</b> ({p['percent']}%)\nСсылка: <code>https://t.me/{cfg.bot_username}?start=p_{p['code']}</code>\n"
                   f"Пришло: {users} · покупок: {len(pays)}\nЗаработано: {earned}⭐ · выплачено: {p['paid']}⭐ · к выплате: {max(0, earned - p['paid'])}⭐")
    return "".join(out)


@router.callback_query(F.data == "cabinet")
async def cb_cabinet(cb: CallbackQuery):
    u, _ = await U.ensure_user(cb.from_user)
    st = await referrals.stats(u["tg_id"])
    status = f"✅ до <b>{U.fmt_dt(u['sub_until'])}</b> (осталось {U.days_left(u)} дн.)" if U.is_active(u) else "⏸ закончилась"
    text = (f"👤 <b>Личный кабинет</b>\n\nID: <code>{u['tg_id']}</code>\nПодписка: {status}\n"
            f"Рефералов: {st['confirmed']} (бонусов: +{st['bonus']} дн.)" + await partner_block(u["tg_id"]))
    await cb.answer()
    await show(cb, text, K.back_kb([[B(text="💳 Купить / продлить", callback_data="buy")]]))


def refs_text(uid: int, st: dict) -> str:
    link = f"https://t.me/{cfg.bot_username}?start=ref_{uid}"
    return (f"👥 <b>Реферальная система</b>\n\nТвоя ссылка:\n<code>{link}</code>\n\n"
            f"Подтверждено: <b>{st['confirmed']}</b> · ждут подписки: {st['pending']}\nБонусов получено: <b>+{st['bonus']} дн.</b>\n\n"
            "🎁 <b>Награды</b>\n• 2 друга → +3 дня\n• 5 друзей → +8 дней (всего)\n• дальше — +1 день за каждого\n\n"
            f"Друг засчитывается, если он запустил бота по твоей ссылке и подписан на {cfg.channel}.")


@router.callback_query(F.data == "refs")
async def cb_refs(cb: CallbackQuery):
    u, _ = await U.ensure_user(cb.from_user)
    st = await referrals.stats(u["tg_id"])
    await cb.answer()
    await show(cb, refs_text(u["tg_id"], st), K.refs_kb(f"https://t.me/{cfg.bot_username}?start=ref_{u['tg_id']}"))


@router.callback_query(F.data == "cmds")
async def cb_cmds(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer(HELP_CMDS, reply_markup=K.back_kb())


def buy_text() -> str:
    return ("💳 <b>Подписка «Всё включено»</b>\nУдалённые и изменённые сообщения, временные фото, все команды.\n\n"
            "• 1 месяц — <b>40⭐</b>\n• 3 месяца — <b>100⭐</b> <i>(выгода 20⭐)</i>\n• 1 год — <b>360⭐</b> <i>(выгода 120⭐)</i>\n\n"
            "Скидки из рулетки применяются автоматически.")


@router.callback_query(F.data == "buy")
async def cb_buy(cb: CallbackQuery):
    u, _ = await U.ensure_user(cb.from_user)
    await cb.answer()
    await show(cb, buy_text(), K.buy_kb(u))


@router.callback_query(F.data.startswith("pay:"))
async def cb_pay(cb: CallbackQuery, bot: Bot):
    plan = cb.data.split(":")[1]
    u, _ = await U.ensure_user(cb.from_user)
    await cb.answer()
    if plan in PLANS and not u.get("banned"):
        await billing.send_invoice(bot, cb.from_user.id, u, plan)


@router.callback_query(F.data == "support")
async def cb_support(cb: CallbackQuery):
    await cb.answer()
    await show(cb, "💬 <b>Поддержка и инструкции</b>\n\nНовости и гайды — в канале. По вопросам оплаты и работы бота — пиши в поддержку.",
               K.back_kb([[B(text="✉️ Написать в поддержку", url=cfg.support_url)], [B(text="📢 Канал", url=cfg.channel_url)]]))


@router.callback_query(F.data == "roulette")
async def cb_roulette(cb: CallbackQuery):
    await cb.answer()
    await show(cb, "🎰 <b>Ежедневная рулетка</b>\nРаз в 24 часа:\n• +1 день подписки (чаще всего)\n• до +3 дней\n"
                   "• скидка до 50% на год или до 20% на 3 месяца", K.roulette_kb())


@router.callback_query(F.data == "spin")
async def cb_spin(cb: CallbackQuery):
    u, _ = await U.ensure_user(cb.from_user)
    ok, text = await roulette.spin(await U.get_user(u["tg_id"], fresh=True))
    await cb.answer()
    await audit("info", "roulette", cb.from_user.id, ok=ok)
    await show(cb, "🎰 <b>Рулетка</b>\n\n" + text, K.back_kb())


@router.callback_query(F.data == "settings")
async def cb_settings(cb: CallbackQuery):
    u, _ = await U.ensure_user(cb.from_user)
    await cb.answer()
    await show(cb, "⚙️ <b>Настройки</b>\nЧто присылать в этот чат:", K.settings_kb(u))


@router.callback_query(F.data.startswith("set:"))
async def cb_set(cb: CallbackQuery):
    key = cb.data.split(":")[1]
    if key not in ("notify_deleted", "notify_edited", "silent"):
        return await cb.answer()
    u, _ = await U.ensure_user(cb.from_user)
    new = not U.setting(u, key, key != "silent")
    u = await U.set_settings(cb.from_user.id, **{key: new})
    await cb.answer("Включено" if new else "Выключено")
    try:
        await cb.message.edit_reply_markup(reply_markup=K.settings_kb(u))
    except TelegramBadRequest:
        pass
