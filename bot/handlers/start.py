from __future__ import annotations

import html
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton as B, InputMediaPhoto, Message

from .. import keyboards as K
from ..config import PLANS, cfg
from ..db import db
from ..services import billing, gate, referrals, roulette
from ..services import users as U
from ..services.logs import audit
from ..texts import CMD_CATEGORIES, HELP_CMDS, SUPPORT_BOT, TUTORIAL

router = Router(name="start")
_ROOT = Path(__file__).resolve().parents[2]
# Linux чувствителен к регистру: assets / Assets
ASSETS = next((d for d in (_ROOT / "assets", _ROOT / "Assets") if d.is_dir()), _ROOT / "assets")
_fid: dict[str, str] = {}

START_CAPTION = (
    "👻 <b>GhostSee</b> — подключи бота к аккаунту\n\n"
    "1️⃣ Настройки → <b>Автоматизация чатов</b>\n"
    f"2️⃣ Введи <code>@{cfg.bot_username}</code> → <b>Добавить</b>\n"
    "3️⃣ Выдай права: читать, отвечать, удалять сообщения\n\n"
    f"🎁 {cfg.trial_days} дней бесплатно — уже включены."
)
LINE = "━━━━━━━━━━━━━━"


def main_caption(u) -> str:
    name = html.escape(u.get("first_name") or "друг")
    if U.is_active(u):
        status = f"✅ <b>Подписка активна</b>\n┗ до {U.fmt_dt(u['sub_until'])} · осталось {U.days_left(u)} дн."
    else:
        status = "⏸ <b>Подписка закончилась</b>\n┗ бот на паузе — продли в разделе «Подписка»"
    return (
        "👻 <b>GhostSee</b>\n"
        "<i>видит то, что исчезает</i>\n\n"
        f"👋 Привет, <b>{name}</b>!\n{status}\n\n"
        f"{LINE}\n"
        "🗑 Удалённые и изменённые сообщения\n"
        "👁 Исчезающие фото и видео\n"
        "🛠 Команды для чатов\n"
        f"{LINE}\n\n"
        "👇 <b>Выбери раздел</b>"
    )


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
    """Только изменение текущего сообщения — без удаления и без нового."""
    msg = cb.message
    # лимит caption у Telegram — 1024
    if msg.photo and len(text) > 1000:
        text = text[:997] + "..."
    try:
        if msg.photo:
            await msg.edit_caption(caption=text, reply_markup=kb)
        else:
            await msg.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        err = str(e).lower()
        if "not modified" in err:
            return
        # ещё раз коротко
        try:
            short = (text[:900] + "…") if len(text) > 900 else text
            if msg.photo:
                await msg.edit_caption(caption=short, reply_markup=kb)
            else:
                await msg.edit_text(short, reply_markup=kb)
        except Exception:
            await cb.answer("Не удалось обновить", show_alert=False)
    except Exception:
        await cb.answer("Не удалось обновить", show_alert=False)


async def show_banner(cb: CallbackQuery, name: str, text: str, kb):
    """Меняет и баннер, и текст текущего сообщения (одно сообщение, без нового и без удаления).

    Если сообщение с фото — подменяем саму картинку на баннер нужного раздела (edit_media).
    Если текстовое — обычная правка текста.
    """
    msg = cb.message
    if msg.photo:
        caption = text[:1000]
        media = InputMediaPhoto(
            media=_fid.get(name) or FSInputFile(_banner(name)),
            caption=caption,
            parse_mode="HTML",
        )
        try:
            m = await msg.edit_media(media=media, reply_markup=kb)
            if name not in _fid and m and m.photo:
                _fid[name] = m.photo[-1].file_id
            return
        except TelegramBadRequest as e:
            if "not modified" in str(e).lower():
                return
        except Exception:
            pass
        # запасной вариант: хотя бы текст подписи
        return await show(cb, text, kb)
    if msg.text is not None:
        return await show(cb, text, kb)
    try:
        photo = _fid.get(name) or FSInputFile(_banner(name))
        m = await msg.answer_photo(photo, caption=text[:1000], reply_markup=kb)
        if name not in _fid and m.photo:
            _fid[name] = m.photo[-1].file_id
    except Exception:
        await msg.answer(text[:4000], reply_markup=kb)


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

    args = command.args or ""
    if not await gate.allowed(bot, m.from_user.id):
        if args.startswith("promo_"):  # запомним ссылку: активируем сразу после подписки
            await U.set_settings(m.from_user.id, pending_promo=args[6:])
        await audit("info", "gate_shown", m.from_user.id)
        return await m.answer(gate.GATE_TEXT, reply_markup=K.channel_kb())

    if args.startswith("promo_"):  # ссылка-промокод: /start promo_КОД
        await _redeem_and_reply(m, bot, args[6:], m.from_user.id)
        return await referrals.try_credit(bot, m.from_user.id)

    # /start = инструкция подключения
    try:
        await send_banner(m, "banner_start", START_CAPTION, K.start_kb(True))
    except TelegramBadRequest as e:
        await audit("warn", "start_btn_url_rejected", m.from_user.id, err=str(e)[:120])
        try:
            await send_banner(m, "banner_start", START_CAPTION, K.start_kb(False))
        except Exception:
            await m.answer(START_CAPTION, reply_markup=K.start_kb(False))
    except Exception as e:
        await audit("error", "start_banner_failed", m.from_user.id, err=str(e)[:200])
        await m.answer(START_CAPTION, reply_markup=K.start_kb(False))

    await referrals.try_credit(bot, m.from_user.id)




@router.message(Command("unfreeze"))
async def cmd_unfreeze(m: Message):
    """Снять заморозку из личного чата с ботом (работает даже когда бот заморожен в Business-чатах)."""
    from ..services import users as U
    u, _ = await U.ensure_user(m.from_user)
    if not U.is_frozen(u):
        return await m.answer("❄️ Заморозки нет — бот работает.")
    await U.end_freeze(u["tg_id"])
    await m.answer("✅ Заморозка снята — бот снова работает.")


@router.message(Command("menu"))
async def cmd_menu(m: Message):
    u, _ = await U.ensure_user(m.from_user)
    try:
        await send_banner(m, "banner_main", main_caption(u), K.main_menu(m.from_user.id))
    except Exception:
        await m.answer(main_caption(u), reply_markup=K.main_menu(m.from_user.id))

@router.message(Command("buy"))
async def cmd_buy(m: Message):
    u, _ = await U.ensure_user(m.from_user)
    await m.answer(buy_text(), reply_markup=K.buy_kb(u))



async def _redeem_and_reply(msg: Message, bot: Bot, code: str, uid: int):
    """Активация промокода с понятным ответом: сколько дней зачислено и до какого срока."""
    from ..services import promos
    res, days = await promos.redeem(bot, uid, code)
    if res == "ok":
        await U.set_settings(uid, last_promo=code.upper())
        return await msg.answer(await promos.success_text(uid, days))
    await msg.answer(promos.ERROR_TEXT.get(res, promos.ERROR_TEXT["error"]))


@router.message(F.text.regexp(r"^[./]promo\s+\S+", flags=__import__("re").I))
async def private_promo(m: Message, bot: Bot):
    parts = (m.text or "").split(maxsplit=1)
    code = parts[1].strip() if len(parts) > 1 else ""
    if not code:
        return await m.answer("🎟 <code>.promo КОД</code>")
    u, _ = await U.ensure_user(m.from_user)
    await _redeem_and_reply(m, bot, code, u["tg_id"])


@router.callback_query(F.data == "check_sub")
async def cb_check(cb: CallbackQuery, bot: Bot):
    await U.ensure_user(cb.from_user)
    gate.invalidate(cb.from_user.id)
    member = await gate.is_member(bot, cb.from_user.id, force=True)
    if member is False:
        return await cb.answer("Ты ещё не подписан на канал 🙂", show_alert=True)
    await cb.answer("✅ Подписка подтверждена!")
    await referrals.try_credit(bot, cb.from_user.id)
    pend = ((await U.ensure_user(cb.from_user))[0].get("settings") or {}).get("pending_promo")
    if pend:  # промокод из ссылки, которую открыли до подписки
        await U.set_settings(cb.from_user.id, pending_promo=None)
        await _redeem_and_reply(cb.message, bot, pend, cb.from_user.id)
    try:
        await cb.message.delete()
    except Exception:
        pass
    u, _ = await U.ensure_user(cb.from_user)
    try:
        await send_banner(cb.message, "banner_main", main_caption(u), K.main_menu(cb.from_user.id))
    except Exception:
        await cb.message.answer(main_caption(u), reply_markup=K.main_menu(cb.from_user.id))


# ---------------- меню ----------------
@router.callback_query(F.data == "menu")
async def cb_menu(cb: CallbackQuery):
    u, _ = await U.ensure_user(cb.from_user)
    await cb.answer()
    await show_banner(cb, "banner_main", main_caption(u), K.main_menu(cb.from_user.id))


@router.callback_query(F.data == "back")
async def cb_back(cb: CallbackQuery):
    u, _ = await U.ensure_user(cb.from_user)
    await cb.answer()
    await show_banner(cb, "banner_main", main_caption(u), K.main_menu(cb.from_user.id))


@router.callback_query(F.data == "connect")
async def cb_connect(cb: CallbackQuery):
    """Инструкция по подключению бота."""
    await cb.answer()
    text = (
        "🔌 <b>Как подключить бота</b>\n"
        f"{LINE}\n\n"
        "1️⃣ Открой <b>Настройки</b> Telegram\n"
        "2️⃣ Зайди в <b>Автоматизация чатов</b> (Business)\n"
        f"3️⃣ В поиске введи <code>@{cfg.bot_username}</code> и нажми <b>Добавить</b>\n"
        "4️⃣ Выдай права: читать, отвечать, удалять сообщения\n"
        "5️⃣ Чаты: «Все личные чаты» (или нужные)\n\n"
        "✅ Бот напишет «Подключён» — готово!"
    )
    await show(cb, text, K.start_kb(True))



# ---------------- туториал ----------------
@router.callback_query(F.data.startswith("tut:"))
async def cb_tutorial(cb: CallbackQuery):
    page = int(cb.data.split(":")[1])
    page = min(max(page, 1), len(TUTORIAL))
    await cb.answer()
    await show(cb, TUTORIAL[page - 1], K.tutorial_kb(page, len(TUTORIAL)))


# ---------------- команды ----------------
@router.callback_query(F.data == "cmds")
async def cb_cmds(cb: CallbackQuery):
    await cb.answer()
    await show(
        cb,
        "🛠 <b>Команды бота</b>\n" + LINE + "\n"
        "Работают в личных чатах после подключения.\n"
        "Префикс <code>.</code> или <code>/</code>\n\n"
        "👇 Нажми команду — описание появится здесь.",
        K.cmds_grid_kb(),
    )


@router.callback_query(F.data.startswith("cat:"))
async def cb_cat(cb: CallbackQuery):
    key = cb.data.split(":")[1]
    await cb.answer()
    text = HELP_CMDS if key == "all" else CMD_CATEGORIES.get(key, (None, "Раздел не найден"))[1]
    await show_banner(cb, "banner_commands", text, K.back_kb(to="cmds", label="⬅️ К командам"))


@router.callback_query(F.data.startswith("cmdinfo:"))
async def cb_cmdinfo(cb: CallbackQuery):
    """Описание команды сверху (цитата), сетка кнопок остаётся."""
    parts = cb.data.split(":")
    key = parts[1]
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
    from ..texts import CMD_INFO
    desc = CMD_INFO.get(
        key,
        f"<code>.{key}</code> — команда\n\n"
        f"<blockquote>Описание скоро.\n\nФормат ввода:\n<code>.{key}</code></blockquote>",
    )
    await cb.answer()
    text = f"🛠 <b>Функционал</b>\n{LINE}\n{desc}"
    await show(cb, text, K.cmds_grid_kb(page))


@router.callback_query(F.data.startswith("cmdpg:"))
async def cb_cmdpage(cb: CallbackQuery):
    page = int(cb.data.split(":")[1])
    await cb.answer()
    await show(
        cb,
        "🛠 <b>Команды бота</b>\n" + LINE + "\n"
        "Работают в личных чатах после подключения.\n"
        "Префикс <code>.</code> или <code>/</code>\n\n"
        "👇 Нажми команду — описание появится здесь.",
        K.cmds_grid_kb(page),
    )


@router.callback_query(F.data == "unfreeze")
async def cb_unfreeze(cb: CallbackQuery):
    from ..services import users as U
    u, _ = await U.ensure_user(cb.from_user)
    if not U.is_frozen(u):
        return await cb.answer("Заморозки уже нет", show_alert=True)
    await U.end_freeze(u["tg_id"])
    await cb.answer("✅ Разморожено")
    try:
        await cb.message.edit_text("❄️ Заморозка снята — бот снова работает ✅")
    except TelegramBadRequest:
        pass


# ---------------- кабинет ----------------
async def partner_block(uid: int) -> str:
    rows = await db.select("gs_partners", {"tg_id": f"eq.{uid}"})
    out = []
    for p in rows:
        users = await db.count("gs_users", {"partner_code": f"eq.{p['code']}"})
        pays = await db.select_all("gs_payments", {"partner_code": f"eq.{p['code']}"})
        earned = sum(x["partner_share"] or 0 for x in pays)
        out.append(f"\n\n🤝 <b>Партнёр</b> ({p['percent']}%)\nСсылка: <code>https://t.me/{cfg.bot_username}?start=p_{p['code']}</code>\n"
                   f"Пришло: {users} · покупок: {len(pays)}\nЗаработано: {earned}⭐ · выплачено: {p['paid']}⭐ · к выплате: {max(0, earned - p['paid'])}⭐")
    return "".join(out)


@router.callback_query(F.data == "cabinet")
async def cb_cabinet(cb: CallbackQuery):
    u, _ = await U.ensure_user(cb.from_user)
    st = await referrals.stats(u["tg_id"])
    status = f"✅ до <b>{U.fmt_dt(u['sub_until'])}</b> (осталось {U.days_left(u)} дн.)" if U.is_active(u) else "⏸ закончилась"
    tr = "✅ вкл" if U.setting(u, "tracker", True) else "❌ выкл"
    fr = U.setting(u, "freeze_until", None)
    freeze_s = "нет"
    if fr:
        ft = U.parse(fr) if isinstance(fr, str) else None
        if ft and U.now() < ft:
            freeze_s = f"до {U.fmt_dt(fr)}"
        else:
            freeze_s = "нет"
    promo = U.setting(u, "last_promo", None) or "—"
    text = (
        f"👤 <b>Личный кабинет</b>\n{LINE}\n"
        f"🆔 ID: <code>{u['tg_id']}</code>\n"
        f"📅 Подписка: {status}\n"
        f"🖥️ Трекер: <b>{tr}</b>\n"
        f"❄️ Заморозка: <b>{freeze_s}</b>\n"
        f"🎟 Последний промо: <code>{promo}</code>\n"
        f"👥 Рефералов: {st['confirmed']} (бонусов: +{st['bonus']} дн.)"
        + await partner_block(u["tg_id"])
    )
    await cb.answer()
    rows = [
        [B(text="💳 Купить / продлить", callback_data="buy")],
        [B(text="🎟 Ввести промокод", callback_data="promo_ask")],
    ]
    if U.is_frozen(u):
        rows.insert(0, [B(text="❄️ Разморозить", callback_data="unfreeze")])
    await show(cb, text, K.back_kb(rows))


def refs_text(uid: int, st: dict) -> str:
    link = f"https://t.me/{cfg.bot_username}?start=ref_{uid}"
    return (f"👥 <b>Реферальная система</b>\n{LINE}\nТвоя ссылка:\n<code>{link}</code>\n\n"
            f"✅ Подтверждено: <b>{st['confirmed']}</b> · ⏳ ждут подписки: {st['pending']}\n🎁 Бонусов получено: <b>+{st['bonus']} дн.</b>\n\n"
            "<b>Награды</b>\n • 2 друга → +3 дня\n • 5 друзей → +8 дней (всего)\n • дальше — +1 день за каждого\n\n"
            f"Друг засчитывается, когда запустил бота по твоей ссылке и подписался на {cfg.channel}.")


@router.callback_query(F.data == "refs")
async def cb_refs(cb: CallbackQuery):
    u, _ = await U.ensure_user(cb.from_user)
    st = await referrals.stats(u["tg_id"])
    await cb.answer()
    await show(cb, refs_text(u["tg_id"], st), K.refs_kb(f"https://t.me/{cfg.bot_username}?start=ref_{u['tg_id']}"))


# ---------------- подписка ----------------
def buy_text() -> str:
    return (f"💳 <b>Подписка «Всё включено»</b>\n{LINE}\n"
            "Удалённые и изменённые сообщения, временные фото и все команды — без ограничений.\n\n"
            "┌ 1 месяц — <b>40⭐</b>\n├ 3 месяца — <b>100⭐</b> · выгода 20⭐\n└ 1 год — <b>360⭐</b> · выгода 120⭐\n\n"
            "🎰 Скидки из рулетки применяются автоматически.\n"
            f"🎫 <b>Хочешь скидку до 35%?</b> Напиши в тикет: @{SUPPORT_BOT}")


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


# ---------------- поддержка ----------------
@router.callback_query(F.data == "support")
async def cb_support(cb: CallbackQuery):
    await cb.answer()
    await show(cb, f"💬 <b>Поддержка</b>\n{LINE}\n"
                   f"🎫 Вопросы по оплате, подписке, ошибки и предложения — пиши в тикет: @{SUPPORT_BOT}\n\n"
                   "💎 <b>Скидка до 35%</b> на подписку — тоже через тикет.\n\n"
                   f"📢 Новости и инструкции: {cfg.channel}", K.support_kb())


# ---------------- рулетка ----------------
@router.callback_query(F.data == "roulette")
async def cb_roulette(cb: CallbackQuery):
    await cb.answer()
    await show(cb, f"🎰 <b>Ежедневная рулетка</b>\n{LINE}\nОдна попытка раз в 24 часа.\n\n"
                   "🎁 Бесплатные дни — очень редко (шанс на +1 день всего 5%)\n"
                   "💸 Скидка до 20% на 3 месяца или до 35% на год (действует 2.5 часа)\n"
                   "😔 Чаще всего не везёт — но завтра новая попытка 🍀", K.roulette_kb())


@router.callback_query(F.data == "spin")
async def cb_spin(cb: CallbackQuery):
    u, _ = await U.ensure_user(cb.from_user)
    ok, text = await roulette.spin(await U.get_user(u["tg_id"], fresh=True))
    await cb.answer()
    await audit("info", "roulette", cb.from_user.id, ok=ok)
    await show(cb, "🎰 <b>Рулетка</b>\n\n" + text, K.back_kb())


# ---------------- настройки ----------------

@router.callback_query(F.data == "promo_ask")
async def cb_promo_ask(cb: CallbackQuery):
    await cb.answer()
    await show(cb, f"🎟 <b>Промокод</b>\n{LINE}\nНапиши в чат с ботом:\n<code>.promo КОД</code>", K.back_kb())

@router.callback_query(F.data == "settings")
async def cb_settings(cb: CallbackQuery):
    u, _ = await U.ensure_user(cb.from_user)
    await cb.answer()
    await show(cb, f"⚙️ <b>Настройки</b>\n{LINE}\n🖥️ <b>Трекер сообщений</b> — главный модуль (вкл. по умолчанию).\nВыключи — бот перестанет присылать удаления/правки.\n\nНиже — тонкая настройка:", K.settings_kb(u))


@router.callback_query(F.data.startswith("set:"))
async def cb_set(cb: CallbackQuery):
    key = cb.data.split(":")[1]
    if key not in ("tracker", "notify_deleted", "notify_edited", "silent"):
        return await cb.answer()
    u, _ = await U.ensure_user(cb.from_user)
    defaults = {"silent": False}
    new = not U.setting(u, key, defaults.get(key, True))
    u = await U.set_settings(cb.from_user.id, **{key: new})
    await cb.answer("Включено" if new else "Выключено")
    try:
        await cb.message.edit_reply_markup(reply_markup=K.settings_kb(u))
    except TelegramBadRequest:
        pass
