from __future__ import annotations

import asyncio
import datetime as dt
import random
import string
from collections import Counter

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup as M, Message

from .. import keyboards as K
from ..config import cfg
from ..db import db
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
<code>/refund USER_ID CHARGE_ID</code> — вернуть Stars"""


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
    return (f"📊 <b>Статистика</b>\n\n👥 Пользователей: {total} (+{new24} за сутки)\n✅ Активных подписок: {active}\n🛒 Платили: {payers}\n⛔ Забанено: {banned}\n\n"
            f"💰 <b>Доход</b>: {sum(p['stars'] for p in pays)}⭐ всего · {rev(7)}⭐ / 7 дн · {rev(30)}⭐ / 30 дн\n"
            f"Покупки: 1м — {by_plan['m1']}, 3м — {by_plan['m3']}, год — {by_plan['y1']}\nПартнёрам начислено: {partner_total}⭐\n\n"
            f"👥 <b>Рефералы</b>: подтверждено {ref_ok}, ждут подписки {ref_wait}\nТоп:\n{top_txt}\n\n🔴 Ошибок за сутки: {errs}")


async def logs_text(level: str = "", n: int = 25) -> str:
    p = {"order": "ts.desc", "limit": min(n, 60)}
    if level:
        p["level"] = f"eq.{level}"
    rows = await db.select("gs_logs", p)
    icon = {"error": "🔴", "warn": "🟡"}
    out = [f"{U.fmt_dt(r['ts'])} {icon.get(r['level'], '⚪')} {r['event']}" + (f" <code>{r['tg_id']}</code>" if r["tg_id"] else "")
           + (f" {str(r['details'])[:80]}" if r["details"] else "") for r in rows]
    return "\n".join(out) or "логов нет"


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
        await cb.message.answer((await logs_text())[:4000])
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


@router.message(Command("stats"))
async def stats(m: Message): await m.answer(await build_stats())


@router.message(Command("logs"))
async def logs(m: Message, command: CommandObject):
    a = (command.args or "").split()
    level = a[0] if a and a[0] in ("info", "warn", "error") else ""
    n = next((int(x) for x in a if x.isdigit()), 25)
    await m.answer((await logs_text(level, n))[:4000])


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
        fwd = await db.count("gs_forum_msgs", {"created_at": f"gt.{since}"})
        if on:
            row("ok", "Форум-логирование", f"включено, за час записано {fwd}")
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
    days = int(parts[1])
    uses = int(parts[2]) if len(parts) > 2 else 1
    only = int(parts[3]) if len(parts) > 3 else 0
    ref_b = int(parts[4]) if len(parts) > 4 else 0
    max_uses = None if uses == 0 else uses
    only_user = only if only else None
    r = await promos.create(code, days, max_uses=max_uses, only_user=only_user,
                            ref_bonus_days=ref_b, created_by=m.from_user.id)
    if r != "ok":
        return await m.answer("❌ Не создался")
    await m.answer(
        f"✅ Промо <code>{code.upper()}</code>\n"
        f"Дни: <b>{days}</b> · uses: {uses or '∞'} · "
        f"personal: {only or 'нет'} · ref_bonus: {ref_b}"
    )


@router.message(Command("promo_list"))
async def promo_list(m: Message):
    from ..services import promos
    rows = await promos.list_recent(20)
    if not rows:
        return await m.answer("Пусто")
    lines = []
    for p in rows:
        lines.append(
            f"<code>{p['code']}</code> +{p.get('days')}д "
            f"used={p.get('used')}/{p.get('max_uses') or '∞'} "
            f"{'user='+str(p['only_user']) if p.get('only_user') else ''}"
        )
    await m.answer("🎟 <b>Промокоды</b>\n" + "\n".join(lines))


@router.callback_query(F.data == "adm:promos")
async def adm_promos(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer(
        "🎟 <b>Промокоды</b>\n\n"
        "<code>/promo_create CODE days [uses] [user_id] [ref_bonus]</code>\n"
        "<code>/promo_list</code>\n\n"
        "Пример: <code>/promo_create GHOST7 7 50 0 1</code>\n"
        "→ 7 дней, 50 активаций, всем, +1 день рефереру"
    )


@router.message(Command("status"))
async def status_cmd(m: Message, bot: Bot):
    await m.answer(await status_text(bot))

