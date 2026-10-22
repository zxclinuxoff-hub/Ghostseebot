from __future__ import annotations

import asyncio
import datetime as dt
import html
import random
import re
import string
from collections import Counter

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup as M, Message

from .. import keyboards as K
from ..config import cfg
from ..db import DBError, db
from ..services import users as U
from ..services.logs import audit
from ..services import settings as S

router = Router(name="admin")
router.message.filter(F.from_user.id.in_(cfg.admin_ids))
router.callback_query.filter(F.from_user.id.in_(cfg.admin_ids))

HELP = """<b>👑 Админ-панель</b>
<code>/stats</code> — статистика, рефералы, доход
<code>/user ID|@name</code> — карточка
<code>/give ID|@name 7d|3m|1y</code> — выдать подписку
<code>/take ID|@name [30d]</code> — забрать (без срока — всю)
<code>/ban</code> · <code>/unban</code> ID|@name
<code>/logs [info|warn|error] [N]</code> — логи
<code>/broadcast</code> — рассылка (текст/фото + кнопки)
<code>/status</code> — проверка частей бота (🟢/🟡/🔴)
<code>/partner_add ID|@name ПРОЦЕНТ [код]</code> · <code>/partners</code> · <code>/payout код ЗВЁЗДЫ</code>
<code>/refund USER_ID CHARGE_ID</code> — вернуть Stars
<code>/promo_list</code> · <code>/promo_stats КОД</code> · <code>/promo_on|off КОД</code> · <code>/promo_del КОД</code>"""


@router.message(Command("admin"))
async def admin(m: Message):
    await m.answer(HELP, reply_markup=K.admin_menu())


async def build_stats() -> str:
    n = U.now()
    d = lambda days: U.iso(n - dt.timedelta(days=days))
    total = await db.count("gs_users")
    active = await db.count("gs_users", {"sub_until": f"gt.{U.iso(n)}", "banned": "eq.false"})
    new24 = await db.count("gs_users", {"created_at": f"gt.{d(1)}"})
    banned = await db.count("gs_users", {"banned": "eq.true"})
    ref_ok = await db.count("gs_referrals", {"status": "eq.credited"})
    ref_wait = await db.count("gs_referrals", {"status": "eq.pending"})
    errs = await db.count("gs_logs", {"level": "eq.error", "ts": f"gt.{d(1)}"})
    pays = await db.select_all("gs_payments")
    t = lambda p: U.parse(p["created_at"])
    rev = lambda days: sum(p["stars"] for p in pays if t(p) > n - dt.timedelta(days=days))
    by_plan = Counter(p["plan"] for p in pays)
    payers = len({p["tg_id"] for p in pays})
    partner_total = sum(p["partner_share"] or 0 for p in pays)
    top = Counter(r["referrer_id"] for r in await db.select_all("gs_referrals", {"status": "eq.credited"})).most_common(5)
    top_txt = "\n".join(f"  <code>{uid}</code> — {c}" for uid, c in top) or "  —"
    w7 = d(7)
    outcomes = ("d1", "d2", "d3", "disc_m3", "disc_y1", "none")
    rl = {k: await db.count("gs_logs", {"event": "eq.roulette_result", "ts": f"gt.{w7}", "details->>outcome": f"eq.{k}"}) for k in outcomes}
    spins = sum(rl.values())
    ref7 = await db.count("gs_referrals", {"status": "eq.credited", "credited_at": f"gt.{w7}"})
    try:
        dons = await db.select_all("gs_donations")
        d_total = sum(x["stars"] for x in dons)
        d_day = sum(x["stars"] for x in dons if t(x) > n - dt.timedelta(days=1))
        d_top = Counter()
        for x in dons:
            d_top[x["tg_id"]] += x["stars"]
        d_top_txt = "\n".join(f"  <code>{uid}</code> — {s}⭐" for uid, s in d_top.most_common(5)) or "  —"
        dtxt = (f"🖤 <b>Донаты</b>: {len(dons)} шт. · {d_total}⭐ всего · {d_day}⭐ за сутки\n"
                f"Топ поддержавших:\n{d_top_txt}\n\n")
    except DBError:
        dtxt = "🖤 <b>Донаты</b>: нет данных (ошибка базы)\n\n"
    rtxt = (f"🎰 <b>Рулетка за 7 дн.</b>: {spins} круток\n"
            f"  +1д: {rl['d1']} · +2д: {rl['d2']} · +3д: {rl['d3']} · скидка 3м: {rl['disc_m3']} · скидка год: {rl['disc_y1']} · без приза: {rl['none']}\n"
            f"🎁 Рефералов подтверждено за 7 дн.: {ref7}\n\n")
    return (f"📊 <b>Статистика</b>\n\n👥 Пользователей: {total} (+{new24} за сутки)\n✅ Активных подписок: {active}\n🛒 Платили: {payers}\n⛔ Забанено: {banned}\n\n"
            f"💰 <b>Доход</b>: {sum(p['stars'] for p in pays)}⭐ всего · {rev(7)}⭐ / 7 дн · {rev(30)}⭐ / 30 дн\n"
            f"Покупки: 1м — {by_plan['m1']}, 3м — {by_plan['m3']}, год — {by_plan['y1']}\nПартнёрам начислено: {partner_total}⭐\n\n"
            f"👥 <b>Рефералы</b>: подтверждено {ref_ok}, ждут подписки {ref_wait}\nТоп:\n{top_txt}\n\n{dtxt}{rtxt}🔴 Ошибок за сутки: {errs}")


async def partners_text() -> str:
    rows = await db.select("gs_partners")
    out = []
    for p in rows:
        pays = await db.select_all("gs_payments", {"partner_code": f"eq.{p['code']}"})
        earned = sum(x["partner_share"] or 0 for x in pays)
        out.append(f"<code>{p['code']}</code> · <code>{p['tg_id']}</code> · {p['percent']}% · заработано {earned}⭐ · выплачено {p['paid']}⭐")
    return "\n".join(out) or "партнёров нет"


@router.callback_query(F.data.startswith("adm:"))
async def adm_cb(cb: CallbackQuery, state: FSMContext, bot: Bot):
    act = cb.data[4:]
    if act != "logging_toggle":  # у переключателя свой answer с подтверждением
        await cb.answer()
    if act == "stats":
        await cb.message.answer(await build_stats())
    elif act == "logs":
        text, kb = await logs_view("", 1)
        await cb.message.answer(text, reply_markup=kb)
    elif act == "partners":
        await cb.message.answer(await partners_text())
    elif act == "broadcast":
        await start_broadcast(cb.message, state)
    elif act == "status":
        await cb.message.answer(await status_text(bot))
    elif act == "logging":
        return await cb_logging_menu(cb)
    elif act == "logging_toggle":
        return await cb_logging_toggle(cb)
    elif act == "promos":
        return await adm_promos(cb)
    elif act == "menu":
        await cb.message.answer(HELP, reply_markup=K.admin_menu())


@router.message(Command("stats"))
async def stats(m: Message): await m.answer(await build_stats())


@router.message(Command("logs"))
async def logs(m: Message, command: CommandObject):
    a = (command.args or "").split()
    level = a[0] if a and a[0] in ("info", "warn", "error") else ""
    text, kb = await logs_view(level, 1)
    await m.answer(text, reply_markup=kb)


@router.message(Command("partners"))
async def partners(m: Message): await m.answer(await partners_text())


async def _target(m: Message, arg: str):
    u = await U.resolve_target(arg)
    if not u:
        await m.answer("Пользователь не найден (он должен был запускать бота).")
    return u


@router.message(Command("user"))
async def user(m: Message, command: CommandObject):
    u = await _target(m, (command.args or "").split()[0] if command.args else "")
    if not u:
        return
    pays = await db.select_all("gs_payments", {"tg_id": f"eq.{u['tg_id']}"})
    await m.answer(f"👤 <code>{u['tg_id']}</code> {u['first_name']} {('@' + u['username']) if u.get('username') else ''}\n"
                   f"Подписка до: <b>{U.fmt_dt(u['sub_until'])}</b>{' ⛔ бан' if u.get('banned') else ''}\n"
                   f"Платежей: {len(pays)} на {sum(p['stars'] for p in pays)}⭐\nПартнёр: {u.get('partner_code') or '—'}\n"
                   f"Скидки: 3м {u['disc_m3']}% · год {u['disc_y1']}%")


@router.message(Command("give"))
async def give(m: Message, command: CommandObject, bot: Bot):
    a = (command.args or "").split()
    days = U.parse_period(a[1]) if len(a) > 1 else None
    if len(a) < 2 or not days:
        return await m.answer("Формат: <code>/give 123456 7d</code> · <code>/give @name 3m</code> · <code>/give ID 1y</code>")
    u = await _target(m, a[0])
    if not u:
        return
    u = await U.grant(u["tg_id"], days)
    await audit("info", "admin_give", u["tg_id"], by=m.from_user.id, days=days)
    await m.answer(f"✅ +{days} дн. → подписка до <b>{U.fmt_dt(u['sub_until'])}</b>")
    try:
        await bot.send_message(u["tg_id"], f"🎁 Тебе выдали подписку на {days} дн. Действует до {U.fmt_dt(u['sub_until'])}.")
    except Exception:
        pass


@router.message(Command("take"))
async def take(m: Message, command: CommandObject):
    a = (command.args or "").split()
    if not a:
        return await m.answer("Формат: <code>/take ID|@name [30d]</code>")
    u = await _target(m, a[0])
    if not u:
        return
    days = U.parse_period(a[1]) if len(a) > 1 else None
    u = await U.take(u["tg_id"], days)
    await audit("info", "admin_take", u["tg_id"], by=m.from_user.id, days=days)
    await m.answer(f"✅ Подписка теперь до <b>{U.fmt_dt(u['sub_until'])}</b>")


@router.message(Command("ban", "unban"))
async def ban(m: Message, command: CommandObject):
    u = await _target(m, (command.args or "").split()[0] if command.args else "")
    if not u:
        return
    flag = command.command == "ban"
    await U.patch_user(u["tg_id"], banned=flag)
    await audit("info", "admin_ban" if flag else "admin_unban", u["tg_id"], by=m.from_user.id)
    await m.answer("⛔ Забанен" if flag else "✅ Разбанен")


@router.message(Command("partner_add"))
async def partner_add(m: Message, command: CommandObject):
    a = (command.args or "").split()
    if len(a) < 2 or not a[1].isdigit() or not 1 <= int(a[1]) <= 90:
        return await m.answer("Формат: <code>/partner_add ID|@name ПРОЦЕНТ [код]</code> (1–90%)")
    u = await _target(m, a[0])
    if not u:
        return
    code = (a[2] if len(a) > 2 else "".join(random.choices(string.ascii_lowercase + string.digits, k=6))).lower()
    await db.insert("gs_partners", {"code": code, "tg_id": u["tg_id"], "percent": int(a[1])}, upsert="code", returning=False)
    await audit("info", "partner_add", u["tg_id"], code=code, percent=int(a[1]))
    await m.answer(f"✅ Партнёр добавлен\nСсылка: <code>https://t.me/{cfg.bot_username}?start=p_{code}</code>")


@router.message(Command("payout"))
async def payout(m: Message, command: CommandObject):
    a = (command.args or "").split()
    if len(a) < 2 or not a[1].isdigit():
        return await m.answer("Формат: <code>/payout код ЗВЁЗДЫ</code> (отметить выплату вручную)")
    rows = await db.select("gs_partners", {"code": f"eq.{a[0].lower()}"})
    if not rows:
        return await m.answer("Код не найден")
    await db.update("gs_partners", {"code": f"eq.{a[0].lower()}"}, {"paid": rows[0]["paid"] + int(a[1])})
    await audit("info", "partner_payout", rows[0]["tg_id"], code=a[0], stars=int(a[1]))
    await m.answer("✅ Выплата отмечена")


@router.message(Command("refund"))
async def refund(m: Message, command: CommandObject, bot: Bot):
    a = (command.args or "").split()
    if len(a) < 2 or not a[0].isdigit():
        return await m.answer("Формат: <code>/refund USER_ID CHARGE_ID</code>")
    await bot.refund_star_payment(user_id=int(a[0]), telegram_payment_charge_id=a[1])
    await audit("info", "refund", int(a[0]), charge=a[1])
    await m.answer("✅ Возврат оформлен (доступ при необходимости забери: /take)")


# ---------------- рассылка (текст / фото + кнопки) ----------------
class BC(StatesGroup):
    content = State()
    buttons = State()
    confirm = State()


async def start_broadcast(m: Message, state: FSMContext):
    await state.set_state(BC.content)
    await m.answer("📣 Пришли сообщение для рассылки (текст или фото с подписью). Отмена: /cancel")


@router.message(Command("broadcast"))
async def broadcast(m: Message, state: FSMContext): await start_broadcast(m, state)


@router.message(Command("cancel"))
async def cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Отменено")


@router.message(BC.content)
async def bc_content(m: Message, state: FSMContext):
    await state.update_data(chat=m.chat.id, mid=m.message_id)
    await state.set_state(BC.buttons)
    await m.answer("Кнопки? По одной в строке: <code>Текст | https://ссылка</code>\nИли отправь <code>-</code> без кнопок.")


def parse_buttons(text: str):
    rows = []
    for line in text.splitlines():
        t, _, u = line.partition("|")
        if t.strip() and u.strip().startswith(("http://", "https://", "tg://")):
            rows.append([B(text=t.strip(), url=u.strip())])
    return M(inline_keyboard=rows) if rows else None


@router.message(BC.buttons)
async def bc_buttons(m: Message, state: FSMContext, bot: Bot):
    kb = None if (m.text or "").strip() == "-" else parse_buttons(m.text or "")
    await state.update_data(buttons=[[b.model_dump() for b in r] for r in kb.inline_keyboard] if kb else None)
    d = await state.get_data()
    await bot.copy_message(m.chat.id, d["chat"], d["mid"], reply_markup=kb)
    await state.set_state(BC.confirm)
    await m.answer("👆 Так увидят пользователи. Отправить всем?",
                   reply_markup=M(inline_keyboard=[[B(text="🚀 Отправить", callback_data="bc_go"), B(text="❌ Отмена", callback_data="bc_no")]]))


@router.callback_query(F.data == "bc_no")
async def bc_no(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer("Отменено")


@router.callback_query(F.data == "bc_go", BC.confirm)
async def bc_go(cb: CallbackQuery, state: FSMContext, bot: Bot):
    d = await state.get_data()
    await state.clear()
    await cb.answer("Запускаю…")
    kb = M(inline_keyboard=[[B(**b) for b in r] for r in d["buttons"]]) if d.get("buttons") else None
    users = await db.select_all("gs_users", {"banned": "eq.false"})
    sent = failed = 0
    status = await cb.message.answer(f"📣 Рассылка: 0/{len(users)}")
    for i, u in enumerate(users, 1):
        try:
            await bot.copy_message(u["tg_id"], d["chat"], d["mid"], reply_markup=kb)
            sent += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await bot.copy_message(u["tg_id"], d["chat"], d["mid"], reply_markup=kb)
                sent += 1
            except Exception:
                failed += 1
        except (TelegramForbiddenError, Exception):
            failed += 1
        if i % 50 == 0:
            try:
                await status.edit_text(f"📣 Рассылка: {i}/{len(users)}")
            except Exception:
                pass
        await asyncio.sleep(0.05)
    await audit("info", "broadcast", cb.from_user.id, sent=sent, failed=failed)
    await status.edit_text(f"✅ Рассылка завершена: доставлено {sent}, ошибок {failed}")


async def cb_logging_menu(cb: CallbackQuery):
    enabled = await S.forum_logging_enabled()
    status = "🟢 ВКЛЮЧЕНО" if enabled else "🔴 ВЫКЛЮЧЕНО"
    kb = M(inline_keyboard=[
        [B(
            text="🔴 Выключить логирование" if enabled else "🟢 Включить логирование",
            callback_data="adm:logging_toggle",
        )],
    ])
    text = (f"🎛 <b>Логирование личных чатов</b>\n\n"
            f"Статус: <b>{status}</b>\n\n"
            f"Когда включено — все Business-сообщения из подключённых аккаунтов "
            f"логируются в форум-темы.\n\n"
            f"Когда выключено — бот продолжает работать (отвечает, команды, "
            f"платежи), но в форум ничего не пишет.\n"
            f"Существующие темы и сообщения не удаляются.\n\n"
            f"Изменение применяется в течение 10 секунд.")
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except Exception:
        await cb.message.answer(text, reply_markup=kb)


async def cb_logging_toggle(cb: CallbackQuery):
    current = await S.forum_logging_enabled()
    new_value = not current
    await S.set("forum_logging", new_value, updated_by=cb.from_user.id)
    await audit("info", "admin_logging_toggle", cb.from_user.id,
                service="admin", actor_id=cb.from_user.id, enabled=new_value)
    await cb.answer("🟢 Включено" if new_value else "🔴 Выключено", show_alert=True)
    await cb_logging_menu(cb)


async def status_text(bot: Bot) -> str:
    """Проверка каждой части бота: 🟢 работает, 🟡 есть предупреждение, 🔴 сломано."""
    import time
    from ..services import scheduler
    from ..services import logs as L

    lines = []

    def row(state: str, label: str, detail: str = ""):
        icon = {"ok": "🟢", "warn": "🟡", "bad": "🔴"}[state]
        lines.append(f"{icon} <b>{label}</b>" + (f" — {detail}" if detail else ""))

    # Telegram API
    t0 = time.perf_counter()
    try:
        me = await bot.get_me()
        ms = int((time.perf_counter() - t0) * 1000)
        row("ok" if ms < 2000 else "warn", "Telegram API", f"@{me.username}, {ms} мс")
    except Exception as e:
        row("bad", "Telegram API", f"{type(e).__name__}: {str(e)[:80]}")

    # Supabase
    t0 = time.perf_counter()
    try:
        await db.select("gs_settings", {"key": "eq.forum_logging", "limit": 1})
        ms = int((time.perf_counter() - t0) * 1000)
        row("ok" if ms < 1500 else "warn", "Supabase (база)", f"{ms} мс")
    except Exception as e:
        row("bad", "Supabase (база)", f"{type(e).__name__}: {str(e)[:80]}")

    from ..commands import engine as E
    row("ok", "Задержка команд", E.lat_summary())

    # Планировщик: цикл должен обновляться каждые несколько секунд
    if scheduler.HEARTBEAT == 0:
        row("bad", "Планировщик", "ещё ни разу не запускался")
    else:
        age = int(time.time() - scheduler.HEARTBEAT)
        row("ok" if age < 60 else "warn" if age < 300 else "bad", "Планировщик",
            f"последний цикл {age} сек. назад")

    # Форум-логирование
    try:
        from ..services.settings import forum_logging_enabled
        on = await forum_logging_enabled()
        since = U.iso(U.now() - dt.timedelta(hours=1))
        from ..services.forum_logs import sent_last_hour
        fwd = sent_last_hour()
        if on:
            row("ok", "Форум-логирование", f"включено, за час отправлено в группу {fwd}")
        else:
            row("warn", "Форум-логирование", "выключено вручную")
    except Exception as e:
        row("bad", "Форум-логирование", f"{type(e).__name__}: {str(e)[:80]}")

    # Ошибки за последний час
    since = U.iso(U.now() - dt.timedelta(hours=1))
    try:
        errs = await db.select("gs_logs", {"level": "eq.error", "ts": f"gt.{since}",
                                           "order": "ts.desc", "limit": 500})
        n = len(errs)
        top = ", ".join(f"{ev} ×{c}" for ev, c in Counter(r["event"] for r in errs).most_common(3))
        row("ok" if n == 0 else "warn" if n <= 5 else "bad", "Ошибки за час",
            f"{n}" + (f" ({top})" if top else ""))
    except Exception as e:
        row("bad", "Журнал ошибок", f"{type(e).__name__}: {str(e)[:80]}")

    up = int(time.time() - L.STARTED_AT)
    h, rem = divmod(up, 3600)
    lines.append(f"\n⏱ Аптайм процесса: {h} ч {rem // 60} мин")
    return "🩺 <b>Статус бота</b>\n\n" + "\n".join(lines)



@router.message(Command("promo_create"))
async def promo_create(m: Message, command: CommandObject):
    """ /promo_create CODE days [uses] [user_id] [ref_bonus]
        uses=0 → безлимит; user_id=0 → для всех
    """
    from ..services import promos
    parts = (command.args or "").split()
    if len(parts) < 2:
        return await m.answer(
            "🎟 <code>/promo_create CODE days [uses] [user_id] [ref_bonus]</code>\n"
            "uses=0 безлимит · user_id=0 всем · ref_bonus дни рефереру"
        )
    code = parts[0]
    try:
        days = int(parts[1])
        uses = int(parts[2]) if len(parts) > 2 else 1
        only = int(parts[3]) if len(parts) > 3 else 0
        ref_b = int(parts[4]) if len(parts) > 4 else 0
    except ValueError:
        return await m.answer("❌ days, uses, user_id и ref_bonus — только числа")
    max_uses = None if uses == 0 else uses
    only_user = only if only else None
    try:
        r = await promos.create(code, days, max_uses=max_uses, only_user=only_user,
                                ref_bonus_days=ref_b, created_by=m.from_user.id)
    except Exception as e:
        return await m.answer(f"❌ Не создался: {str(e)[:300]}")
    if r != "ok":
        return await m.answer("❌ Не создался")
    await m.answer(
        f"✅ Промо <code>{code.upper()}</code>\n"
        f"Дни: <b>{days}</b> · uses: {uses or '∞'} · "
        f"personal: {only or 'нет'} · ref_bonus: {ref_b}\n"
        f"🔗 <code>{promos.promo_link(code)}</code>"
    )


PROMO_SIZE = 6
PROMO_HELP = (
    "🎟 <b>Промокоды</b>\n"
    "<code>/promo_create CODE days [uses] [user_id] [ref_bonus]</code>\n"
    "<code>/promo_stats КОД</code> · <code>/promo_on КОД</code> · <code>/promo_off КОД</code> · <code>/promo_del КОД</code>\n"
    "Пример: <code>/promo_create GHOST7 7 50 0 1</code> → 7 дней, 50 активаций, всем, +1 день рефереру"
)


def _promo_active(p) -> bool:
    return p.get("active") is not False


def _promo_line(p) -> str:
    st = "✅" if _promo_active(p) else "⏸"
    lim = p.get("max_uses") or "∞"
    extra = f" · личный <code>{p['only_user']}</code>" if p.get("only_user") else ""
    exp = f" · до {U.fmt_dt(p['expires_at'])}" if p.get("expires_at") else ""
    return f"{st} <code>{html.escape(str(p['code']))}</code> +{p.get('days')}д · {p.get('used') or 0}/{lim}{extra}{exp}"


async def promos_view(page: int = 1):
    from ..services import promos
    rows, total, pages, page = await promos.list_page(page, PROMO_SIZE)
    head = f"🎟 <b>Промокоды</b> · стр. {page}/{pages} · всего {total}\n\n"
    body = "\n".join(_promo_line(p) for p in rows) or "Промокодов пока нет. Создай: <code>/promo_create</code>"
    kb = [[B(text="➕ Создать промокод", callback_data="promo:new")]]
    for p in rows:
        c = p["code"]
        kb.append([
            B(text=f"📊 {c}"[:30], callback_data=f"promo:stats:{c}"),
            B(text="⏸ Выкл" if _promo_active(p) else "▶️ Вкл", callback_data=f"promo:toggle:{c}:{page}"),
            B(text="🗑", callback_data=f"promo:delask:{c}:{page}"),
        ])
    nav = []
    if page > 1:
        nav.append(B(text="◀️", callback_data=f"promo:page:{page - 1}"))
    if page < pages:
        nav.append(B(text="▶️", callback_data=f"promo:page:{page + 1}"))
    if nav:
        kb.append(nav)
    return head + body, M(inline_keyboard=kb)


async def promo_stats_text(code: str) -> str:
    from ..services import promos
    p = await promos.get(code)
    if not p:
        return "❌ Промокод не найден"
    reds = await promos.redemptions(p["code"], 30)
    lines = [f"{U.fmt_dt(r['created_at'])} · <code>{r['tg_id']}</code>" for r in reds]
    extra = f"Личный: <code>{p['only_user']}</code>\n" if p.get("only_user") else ""
    exp = f"Истекает: {U.fmt_dt(p['expires_at'])}\n" if p.get("expires_at") else ""
    txt = (f"📊 <b>{html.escape(str(p['code']))}</b> · {'✅ активен' if _promo_active(p) else '⏸ отключён'}\n"
           f"+{p.get('days')} дн. · активаций {p.get('used') or 0}/{p.get('max_uses') or '∞'}\n🔗 <code>{promos.promo_link(p['code'])}</code>\n{extra}{exp}\n"
           + ("\n".join(lines) or "Пока никто не активировал"))
    return txt[:4000]


async def _edit_or_skip(cb: CallbackQuery, text: str, kb):
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass  # та же самая страница — Telegram не даёт «изменить» на идентичную


async def adm_promos(cb: CallbackQuery):
    """Вызывается из adm_cb (там cb.answer() уже сделан)."""
    text, kb = await promos_view(1)
    await cb.message.answer(PROMO_HELP + "\n\n" + text, reply_markup=kb)


@router.callback_query(F.data.startswith("promo:"))
async def cb_promo(cb: CallbackQuery, state: FSMContext):
    from ..services import promos
    parts = cb.data.split(":")
    act = parts[1]
    if act == "new":
        await cb.answer()
        return await promo_wiz_start(cb, state)
    if act == "page":
        await cb.answer()
        text, kb = await promos_view(int(parts[2]))
        return await _edit_or_skip(cb, text, kb)
    code = parts[2] if len(parts) > 2 else ""
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1
    if act == "stats":
        await cb.answer()
        return await cb.message.answer(await promo_stats_text(code))
    if act == "toggle":
        p = await promos.get(code)
        if not p:
            return await cb.answer("Промокод не найден", show_alert=True)
        new_state = not _promo_active(p)
        await promos.set_active(code, new_state)
        await audit("info", "promo_toggle", cb.from_user.id, code=code, active=new_state)
        await cb.answer("Включён" if new_state else "Отключён")
        text, kb = await promos_view(page)
        return await _edit_or_skip(cb, text, kb)
    if act == "delask":
        await cb.answer()
        kb = M(inline_keyboard=[
            [B(text="✅ Да, удалить", callback_data=f"promo:delok:{code}:{page}")],
            [B(text="↩️ Нет", callback_data=f"promo:page:{page}")],
        ])
        return await _edit_or_skip(cb, f"⚠️ Удалить промокод <code>{html.escape(code)}</code> и всю историю активаций?", kb)
    if act == "delok":
        await promos.delete(code)
        await audit("warn", "promo_delete", cb.from_user.id, code=code)
        await cb.answer("Удалён")
        text, kb = await promos_view(page)
        return await _edit_or_skip(cb, text, kb)
    await cb.answer()


# ---------- мастер создания промокода кнопками ----------
class PromoWiz(StatesGroup):
    code = State()
    days = State()
    uses = State()
    target = State()


WIZ_DAYS = [1, 3, 7, 14, 30]
WIZ_USES = [1, 10, 50, 100]
WIZ_REF = [0, 1, 3, 7]


def _wiz_screen(step: str, d: dict):
    cancel = [B(text="❌ Отмена", callback_data="pw:cancel:0")]
    if step == "code":
        return ("🎟 <b>Новый промокод</b>\n\nКод сделаем случайный или напиши свой?",
                [[B(text="🎲 Случайный", callback_data="pw:code:rand"), B(text="✏️ Свой", callback_data="pw:code:ask")], cancel])
    if step == "code_ask":
        return ("✏️ Напиши код одним сообщением: 3–32 символа, латиница, цифры, <code>_</code> или <code>-</code>.", [cancel])
    if step == "days":
        return (f"🎟 Код <code>{d['code']}</code>\n\nСколько дней подписки он даёт?",
                [[B(text=f"{x} дн.", callback_data=f"pw:days:{x}") for x in WIZ_DAYS],
                 [B(text="✏️ Другое число", callback_data="pw:days:ask")], cancel])
    if step == "days_ask":
        return ("✏️ Напиши число дней (от 1 до 3650).", [cancel])
    if step == "uses":
        return ("🔢 Сколько раз его можно активировать?",
                [[B(text=str(x), callback_data=f"pw:uses:{x}") for x in WIZ_USES],
                 [B(text="♾ Без лимита", callback_data="pw:uses:0"), B(text="✏️ Другое", callback_data="pw:uses:ask")], cancel])
    if step == "uses_ask":
        return ("✏️ Напиши число активаций (0 — без лимита).", [cancel])
    if step == "target":
        return ("👥 Кому доступен промокод?",
                [[B(text="👥 Всем", callback_data="pw:to:all"), B(text="👤 Один человек", callback_data="pw:to:ask")], cancel])
    if step == "target_ask":
        return ("✏️ Напиши ID или @username пользователя (он должен был запускать бота).", [cancel])
    if step == "ref":
        return ("🎁 Сколько дней получит рефереру, если по этому коду активирует друг?",
                [[B(text=(str(x) if x else "Без бонуса"), callback_data=f"pw:ref:{x}") for x in WIZ_REF], cancel])
    if step == "confirm":
        who = f"пользователь <code>{d['only_user']}</code>" if d.get("only_user") else "всем"
        uses = d["uses"] or "∞"
        txt = (f"🧾 <b>Проверь промокод</b>\n\n"
               f"Код: <code>{d['code']}</code>\nДней: <b>{d['days']}</b>\nАктиваций: <b>{uses}</b>\n"
               f"Кому: {who}\nБонус рефереру: <b>+{d['ref']} дн.</b>")
        return txt, [[B(text="✅ Создать", callback_data="pw:ok:0")], cancel]
    raise ValueError(step)


async def _wiz_show(bot, chat_id: int, state: FSMContext, text: str, kb):
    """Один экран мастера: всё редактируется в одном сообщении."""
    mid = (await state.get_data()).get("pmid")
    if mid:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=mid, reply_markup=kb)
            return
        except TelegramBadRequest as e:
            if "not modified" in str(e).lower():
                return
    m = await bot.send_message(chat_id, text, reply_markup=kb)
    await state.update_data(pmid=m.message_id, chat=chat_id)


async def _wiz_render(bot, chat_id: int, state: FSMContext, step: str):
    d = await state.get_data()
    text, kb = _wiz_screen(step, d)
    await _wiz_show(bot, chat_id, state, text, M(inline_keyboard=kb))


async def _wiz_finish_to_list(bot, chat_id: int, state: FSMContext, prefix: str = ""):
    """Выход из мастера: показываем список промокодов в том же сообщении."""
    mid = (await state.get_data()).get("pmid")
    await state.clear()
    text, kb = await promos_view(1)
    text = prefix + text
    if mid:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=mid, reply_markup=kb)
            return
        except TelegramBadRequest:
            pass
    await bot.send_message(chat_id, text, reply_markup=kb)


async def promo_wiz_start(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.update_data(pmid=cb.message.message_id, chat=cb.message.chat.id)
    await _wiz_render(cb.bot, cb.message.chat.id, state, "code")


@router.callback_query(F.data.startswith("pw:"))
async def cb_promo_wiz(cb: CallbackQuery, state: FSMContext):
    from ..services import promos
    parts = cb.data.split(":")
    what, val = parts[1], (parts[2] if len(parts) > 2 else "")
    chat = cb.message.chat.id
    await cb.answer()
    if what == "cancel":
        return await _wiz_finish_to_list(cb.bot, chat, state, "❌ Отменено\n\n")
    if what == "code":
        if val == "rand":
            await state.update_data(code="".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8)))
            return await _wiz_render(cb.bot, chat, state, "days")
        await state.set_state(PromoWiz.code)
        return await _wiz_render(cb.bot, chat, state, "code_ask")
    if what == "days":
        if val == "ask":
            await state.set_state(PromoWiz.days)
            return await _wiz_render(cb.bot, chat, state, "days_ask")
        await state.update_data(days=int(val))
        return await _wiz_render(cb.bot, chat, state, "uses")
    if what == "uses":
        if val == "ask":
            await state.set_state(PromoWiz.uses)
            return await _wiz_render(cb.bot, chat, state, "uses_ask")
        await state.update_data(uses=int(val))
        return await _wiz_render(cb.bot, chat, state, "target")
    if what == "to":
        if val == "ask":
            await state.set_state(PromoWiz.target)
            return await _wiz_render(cb.bot, chat, state, "target_ask")
        await state.update_data(only_user=None)
        return await _wiz_render(cb.bot, chat, state, "ref")
    if what == "ref":
        await state.update_data(ref=int(val))
        return await _wiz_render(cb.bot, chat, state, "confirm")
    if what == "ok":
        d = await state.get_data()
        r = await promos.create(d["code"], d["days"], max_uses=(d["uses"] or None),
                                only_user=d.get("only_user"), ref_bonus_days=d.get("ref", 0),
                                created_by=cb.from_user.id)
        await audit("info", "promo_wizard_create", cb.from_user.id, code=d["code"], days=d["days"])
        return await _wiz_finish_to_list(cb.bot, chat, state, f"✅ Промокод <code>{d['code']}</code> создан\n🔗 <code>{promos.promo_link(d['code'])}</code>\n\n" if r == "ok" else "❌ Не создался\n\n")


async def _wiz_input_error(m: Message, text: str):
    await m.answer("❌ " + text + "\nНапиши ещё раз или нажми «Отмена» в мастере.")


@router.message(PromoWiz.code)
async def wiz_code_text(m: Message, state: FSMContext):
    from ..services import promos
    code = (m.text or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9_\-]{3,32}", code):
        return await _wiz_input_error(m, "Код: 3–32 символа, латиница, цифры, _ или -.")
    if await promos.get(code):
        return await _wiz_input_error(m, f"Код {code} уже существует.")
    await state.update_data(code=code)
    await state.set_state(None)
    await _wiz_render(m.bot, m.chat.id, state, "days")


@router.message(PromoWiz.days)
async def wiz_days_text(m: Message, state: FSMContext):
    t = (m.text or "").strip()
    if not t.isdigit() or not 1 <= int(t) <= 3650:
        return await _wiz_input_error(m, "Нужно целое число дней от 1 до 3650.")
    await state.update_data(days=int(t))
    await state.set_state(None)
    await _wiz_render(m.bot, m.chat.id, state, "uses")


@router.message(PromoWiz.uses)
async def wiz_uses_text(m: Message, state: FSMContext):
    t = (m.text or "").strip()
    if not t.isdigit() or int(t) > 1000000:
        return await _wiz_input_error(m, "Нужно целое число активаций (0 — без лимита).")
    await state.update_data(uses=int(t))
    await state.set_state(None)
    await _wiz_render(m.bot, m.chat.id, state, "target")


@router.message(PromoWiz.target)
async def wiz_target_text(m: Message, state: FSMContext):
    u = await U.resolve_target(m.text or "")
    if not u:
        return await _wiz_input_error(m, "Пользователь не найден (он должен был запускать бота).")
    await state.update_data(only_user=u["tg_id"])
    await state.set_state(None)
    await _wiz_render(m.bot, m.chat.id, state, "ref")


@router.message(Command("promo_list"))
async def promo_list(m: Message):
    text, kb = await promos_view(1)
    await m.answer(text, reply_markup=kb)


def _code_arg(command: CommandObject) -> str:
    parts = (command.args or "").split()
    return parts[0] if parts else ""


@router.message(Command("promo_stats"))
async def promo_stats_cmd(m: Message, command: CommandObject):
    code = _code_arg(command)
    if not code:
        return await m.answer("Использование: <code>/promo_stats КОД</code>")
    await m.answer(await promo_stats_text(code))


async def _promo_switch(m: Message, command: CommandObject, state: bool):
    from ..services import promos
    code = _code_arg(command)
    if not code:
        return await m.answer("Использование: <code>/promo_on КОД</code> или <code>/promo_off КОД</code>")
    if not await promos.set_active(code, state):
        return await m.answer("❌ Промокод не найден")
    await audit("info", "promo_toggle", m.from_user.id, code=code.upper(), active=state)
    await m.answer(f"{'✅ Включён' if state else '⏸ Отключён'}: <code>{html.escape(code.upper())}</code>")


@router.message(Command("promo_on"))
async def promo_on(m: Message, command: CommandObject):
    await _promo_switch(m, command, True)


@router.message(Command("promo_off"))
async def promo_off(m: Message, command: CommandObject):
    await _promo_switch(m, command, False)


@router.message(Command("promo_del"))
async def promo_del_cmd(m: Message, command: CommandObject):
    from ..services import promos
    code = _code_arg(command)
    if not code:
        return await m.answer("Использование: <code>/promo_del КОД</code>")
    if not await promos.get(code):
        return await m.answer("❌ Промокод не найден")
    await promos.delete(code)
    await audit("warn", "promo_delete", m.from_user.id, code=code.upper())
    await m.answer(f"🗑 Удалён: <code>{html.escape(code.upper())}</code>")


LOGS_SIZE = 20


async def logs_view(level: str = "", page: int = 1):
    where = {"level": f"eq.{level}"} if level else {}
    total = await db.count("gs_logs", where or None)
    pages = max(1, -(-total // LOGS_SIZE))
    page = min(max(1, page), pages)
    rows = await db.select("gs_logs", {**where, "order": "ts.desc", "limit": LOGS_SIZE,
                                       "offset": (page - 1) * LOGS_SIZE})
    icon = {"error": "🔴", "warn": "🟡"}
    head = f"📜 <b>Логи</b> · {level or 'все'} · стр. {page}/{pages} · всего {total}\n\n"
    body, budget = [], 3600 - len(head)
    for r in rows:
        who = f" <code>{r['tg_id']}</code>" if r.get("tg_id") else ""
        det = html.escape(str(r.get("details") or ""))[:200]
        line = f"{U.fmt_dt(r['ts'])} {icon.get(r['level'], '⚪')} <b>{html.escape(str(r['event']))}</b>{who}"
        if det:
            line += f"\n<code>{det}</code>"
        if budget - len(line) < 0:
            break
        budget -= len(line) + 1
        body.append(line)
    lvl = level or "-"
    nav = []
    if page > 1:
        nav.append(B(text="◀️", callback_data=f"logp:{lvl}:{page - 1}"))
    nav.append(B(text="🔄", callback_data=f"logp:{lvl}:{page}"))
    if page < pages:
        nav.append(B(text="▶️", callback_data=f"logp:{lvl}:{page + 1}"))
    kb = M(inline_keyboard=[nav, [
        B(text="Все", callback_data="logp:-:1"),
        B(text="🔴 Ошибки", callback_data="logp:error:1"),
        B(text="🟡 Предупр.", callback_data="logp:warn:1"),
    ]])
    return head + ("\n".join(body) or "логов нет"), kb


@router.callback_query(F.data.startswith("logp:"))
async def cb_logs_page(cb: CallbackQuery):
    _, lvl, pg = cb.data.split(":")
    await cb.answer()
    text, kb = await logs_view("" if lvl == "-" else lvl, int(pg) if pg.isdigit() else 1)
    await _edit_or_skip(cb, text, kb)


@router.message(Command("status"))
async def status_cmd(m: Message, bot: Bot):
    await m.answer(await status_text(bot))

