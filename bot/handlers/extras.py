"""Меню «Поддержать разработчика», «Настройка команд» и исключения для .afk.

Все действия проверяют владельца на сервере (по from_user текущего запроса, а не по callback-data).
Настройки команд доступны только при активной подписке.
"""
from __future__ import annotations

import html

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup as M, Message

from .. import keyboards as K
from ..db import DBError
from ..services import afk_excl
from ..services import afk_rules as AR
from ..services import donate
from ..services import donate_rules as DR
from ..services import users as U
from ..services.logs import audit
from .start import LINE, show

router = Router(name="extras")
esc = html.escape
DENIED = "Настройка команд доступна при активной подписке."
DB_FAIL = "⚠️ База временно недоступна, попробуй через минуту."

# Расширяемый реестр: чтобы добавить настройку другой команды, достаточно новой записи и своих обработчиков.
CMD_SETTINGS: dict[str, str] = {"afk": "🌙 Настройка .afk"}

DONATE_LABELS = {1: "⭐ 1 звезда", 2: "⭐ 2 звезды", 5: "⭐ 5 звёзд", 10: "⭐ 10 звёзд"}


class AfkAdd(StatesGroup):
    waiting = State()


async def _owner(uid: int) -> dict | None:
    """Свежие данные из базы: владелец не забанен и подписка активна."""
    u = await U.get_user(uid, fresh=True)
    if not u or u.get("banned") or not U.is_active(u):
        return None
    return u


async def _deny(cb: CallbackQuery) -> None:
    await cb.answer(DENIED, show_alert=True)


# ---------------- поддержка разработчика ----------------
DONATE_TEXT = (f"🖤 <b>Поддержать разработчика</b>\n{LINE}\n"
               "Если тебе нравится GhostSeeBot и моя работа над проектом, ты можешь поддержать его развитие "
               "звёздами Telegram. Спасибо за поддержку!")


def donate_kb() -> M:
    rows = [[B(text=DONATE_LABELS[n], callback_data=f"donate:{n}")] for n in DR.DONATE_AMOUNTS]
    return K.back_kb(rows, label="⬅️ Назад")


@router.callback_query(F.data == "donate")
async def cb_donate(cb: CallbackQuery):
    await cb.answer()
    await show(cb, DONATE_TEXT, donate_kb())


@router.callback_query(F.data.regexp(r"^donate:\d+$"))
async def cb_donate_amount(cb: CallbackQuery, bot: Bot):
    try:
        stars = int(cb.data.split(":")[1])
    except ValueError:
        return await cb.answer()
    if stars not in DR.DONATE_AMOUNTS:
        return await cb.answer("Такой суммы нет", show_alert=True)
    try:
        await donate.send_invoice(bot, cb.from_user.id, stars)
    except Exception as e:
        await audit("error", "donate_invoice_failed", cb.from_user.id, err=str(e)[:200])
        return await cb.answer("Не удалось создать счёт, попробуй позже", show_alert=True)
    await cb.answer("Счёт отправлен в чат с ботом")


# ---------------- настройка команд ----------------
CMD_TEXT = (f"⚙️ <b>Настройка команд</b>\n{LINE}\n"
            "Здесь ты можешь управлять поведением отдельных команд GhostSeeBot.\n\n"
            "Выбери команду для настройки:")


def cmd_settings_kb() -> M:
    rows = [[B(text=title, callback_data=f"cfg:{key}")] for key, title in CMD_SETTINGS.items()]
    return K.back_kb(rows, label="⬅️ Назад")


@router.callback_query(F.data == "cmdcfg")
async def cb_cmdcfg(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    if not await _owner(cb.from_user.id):
        return await _deny(cb)
    await cb.answer()
    await show(cb, CMD_TEXT, cmd_settings_kb())


# ---------------- .afk: исключения ----------------
AFK_TEXT = (f"🌙 <b>Настройка .afk</b>\n{LINE}\n"
            "Исключения — пользователи, которым бот не будет отправлять AFK-ответы.\n\n"
            "Добавляй или удаляй пользователей из списка исключений.")


def afk_kb() -> M:
    return M(inline_keyboard=[
        [B(text="➕ Добавить исключение", callback_data="afkx:add")],
        [B(text="➖ Удалить исключение", callback_data="afkx:del:1")],
        [B(text="📋 Список исключений", callback_data="afkx:list:1")],
        [B(text="⬅️ Назад", callback_data="cmdcfg")],
    ])


def _back_to_afk_kb(extra: list | None = None) -> M:
    rows = list(extra or [])
    rows.append([B(text="⬅️ Назад", callback_data="cfg:afk")])
    return M(inline_keyboard=rows)


def _name_or_id(row: dict) -> str:
    return esc(row.get("excluded_name") or "имя неизвестно")


@router.callback_query(F.data == "cfg:afk")
async def cb_afk_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    if not await _owner(cb.from_user.id):
        return await _deny(cb)
    await cb.answer()
    await show(cb, AFK_TEXT, afk_kb())


@router.callback_query(F.data == "afkx:add")
async def cb_afk_add(cb: CallbackQuery, state: FSMContext):
    if not await _owner(cb.from_user.id):
        return await _deny(cb)
    await state.set_state(AfkAdd.waiting)
    await cb.answer()
    await show(cb, (f"➕ <b>Добавить исключение</b>\n{LINE}\n"
                    "Пришли Telegram ID пользователя — только цифры, одним сообщением.\n\n"
                    "Пример: <code>123456789</code>"),
               M(inline_keyboard=[[B(text="❌ Отмена", callback_data="afkx:cancel")]]))


@router.callback_query(F.data == "afkx:cancel")
async def cb_afk_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer("Отменено")
    await show(cb, AFK_TEXT, afk_kb())


async def _resolve_name(bot: Bot, pid: int) -> str | None:
    """Имя берём, если Telegram его отдаёт (бот должен был контактировать с пользователем)."""
    try:
        chat = await bot.get_chat(pid)
    except Exception:
        return None
    name = " ".join(x for x in (chat.first_name, getattr(chat, "last_name", None)) if x) or None
    if chat.username:
        name = f"{name} (@{chat.username})" if name else f"@{chat.username}"
    return name


@router.message(AfkAdd.waiting)
async def msg_afk_add(m: Message, state: FSMContext, bot: Bot):
    if not await _owner(m.from_user.id):
        await state.clear()
        return await m.answer(DENIED)
    text = m.text or ""
    if text.startswith("/"):  # команду не превращаем в ID — просто выходим из режима добавления
        await state.clear()
        return await m.answer("Добавление отменено. Открой меню снова: /menu")
    pid = AR.parse_partner_id(text)
    if pid is None:
        return await m.answer("❗ Нужен Telegram ID: только цифры, от 5 до 15 знаков. "
                              "Пришли ещё раз или нажми «Отмена» в меню.")
    if pid == m.from_user.id:
        return await m.answer("Нельзя добавить самого себя. Пришли ID другого пользователя.")
    name = await _resolve_name(bot, pid)
    try:
        added = await afk_excl.add(m.from_user.id, pid, name)
    except DBError as e:
        await audit("error", "afk_excl_add_failed", m.from_user.id, err=str(e)[:200])
        return await m.answer(DB_FAIL)
    await state.clear()
    head = "✅ Исключение добавлено" if added else "ℹ️ Этот ID уже в списке"
    await m.answer(f"{head}: <code>{pid}</code>" + (f" — {esc(name)}" if name else ""),
                   reply_markup=_back_to_afk_kb())


def _pager_row(prefix: str, page: int, pages: int) -> list[B]:
    nav = []
    if page > 1:
        nav.append(B(text="⬅️", callback_data=f"{prefix}{page - 1}"))
    if page < pages:
        nav.append(B(text="➡️", callback_data=f"{prefix}{page + 1}"))
    return nav


@router.callback_query(F.data.regexp(r"^afkx:list:\d+$"))
async def cb_afk_list(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    uid = cb.from_user.id
    if not await _owner(uid):
        return await _deny(cb)
    try:
        total = await afk_excl.count(uid)
        page, pages, offset = AR.page_bounds(total, int(cb.data.split(":")[-1]))
        rows = await afk_excl.page(uid, offset, AR.PAGE_SIZE) if total else []
    except DBError as e:
        await audit("error", "afk_excl_list_failed", uid, err=str(e)[:200])
        return await cb.answer(DB_FAIL, show_alert=True)
    await cb.answer()
    if not total:
        return await show(cb, (f"📋 <b>Список исключений</b>\n{LINE}\nСписок пуст.\n"
                               "Добавь первое исключение — и бот не будет отправлять AFK-ответ этому пользователю."),
                          _back_to_afk_kb([[B(text="➕ Добавить исключение", callback_data="afkx:add")]]))
    lines = [f"{offset + i}. <code>{r['excluded_id']}</code> — {_name_or_id(r)}"
             for i, r in enumerate(rows, 1)]
    text = (f"📋 <b>Список исключений</b> (всего: {total}, стр. {page}/{pages})\n{LINE}\n" + "\n".join(lines))
    kb = [_pager_row("afkx:list:", page, pages)] if pages > 1 else []
    await show(cb, text, _back_to_afk_kb(kb))


async def _render_del(cb: CallbackQuery, uid: int, page_no: int) -> None:
    """Экран «Удалить исключение». Вызывается без cb.answer — ответ отдаёт вызывающий обработчик."""
    try:
        total = await afk_excl.count(uid)
        page, pages, offset = AR.page_bounds(total, page_no)
        rows = await afk_excl.page(uid, offset, AR.PAGE_SIZE) if total else []
    except DBError as e:
        await audit("error", "afk_excl_del_list_failed", uid, err=str(e)[:200])
        return await show(cb, DB_FAIL, _back_to_afk_kb())
    if not total:
        return await show(cb, f"➖ <b>Удалить исключение</b>\n{LINE}\nСписок пуст — удалять нечего.",
                          _back_to_afk_kb([[B(text="➕ Добавить исключение", callback_data="afkx:add")]]))
    buttons = [[B(text=f"❌ {r['excluded_id']} — {r.get('excluded_name') or 'без имени'}"[:60],
                  callback_data=f"afkx:rm:{r['excluded_id']}:{page}")] for r in rows]
    kb = buttons + ([_pager_row("afkx:del:", page, pages)] if pages > 1 else [])
    await show(cb, (f"➖ <b>Удалить исключение</b>\n{LINE}\nНажми на пользователя, чтобы убрать его из списка.\n"
                    f"Страница {page}/{pages}"), _back_to_afk_kb(kb))


@router.callback_query(F.data.regexp(r"^afkx:del:\d+$"))
async def cb_afk_del(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    uid = cb.from_user.id
    if not await _owner(uid):
        return await _deny(cb)
    await cb.answer()
    await _render_del(cb, uid, int(cb.data.split(":")[-1]))


@router.callback_query(F.data.regexp(r"^afkx:rm:\d{5,15}:\d+$"))
async def cb_afk_remove(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    uid = cb.from_user.id
    if not await _owner(uid):
        return await _deny(cb)
    _, _, pid_s, page_s = cb.data.split(":")
    try:
        removed = await afk_excl.remove(uid, int(pid_s))  # удаляем только запись этого владельца
    except DBError as e:
        await audit("error", "afk_excl_remove_failed", uid, err=str(e)[:200])
        return await cb.answer(DB_FAIL, show_alert=True)
    await cb.answer("Удалено" if removed else "Уже удалено")
    await _render_del(cb, uid, int(page_s))  # экран обновляется сразу, без выхода из меню
