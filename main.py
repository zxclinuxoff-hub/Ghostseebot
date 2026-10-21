import os
import pathlib
import sys


EXPECTED = {
    "bot": ["config.py", "db.py", "keyboards.py", "texts.py"],
    "bot/services": ["users.py", "biz.py", "billing.py", "billing_prices.py", "referrals.py",
                     "roulette.py", "scheduler.py", "logs.py", "gate.py"],
    "bot/handlers": ["start.py", "payments.py", "admin.py", "business.py", "extras.py"],
    "bot/commands": ["engine.py", "tools.py"],
}


def _fix_case():
    """GitHub с телефона часто меняет регистр (Bot вместо bot, Texts.py вместо texts.py).
    На Linux регистр важен — создаём симлинки с нужными именами и показываем, каких файлов не хватает."""
    root = pathlib.Path(__file__).resolve().parent
    for rel in ("bot", "bot/services", "bot/handlers", "bot/commands", "assets"):
        cur = root
        for part in rel.split("/"):
            if not cur.exists():
                break
            want = cur / part
            if not want.exists():
                found = next((x for x in cur.iterdir() if x.is_dir() and x.name.lower() == part), None)
                if found is not None:
                    try:
                        os.symlink(found.name, str(want), target_is_directory=True)
                        print(f"[fix] папка {found.name} -> {part}")
                    except OSError as e:
                        print(f"[fix] не удалось: {e}. Переименуй папку {found.name} в {part} на GitHub.")
            cur = want
    missing = []
    for d, files in EXPECTED.items():
        dp = root / d
        if not dp.exists():
            missing.append(f"{d}/ (папки нет)")
            continue
        for f in files:
            if (dp / f).exists():
                continue
            alt = next((x for x in dp.iterdir() if x.is_file() and x.name.lower() == f), None)
            if alt is not None:
                try:
                    os.symlink(alt.name, str(dp / f))
                    print(f"[fix] файл {alt.name} -> {f}")
                except OSError as e:
                    missing.append(f"{d}/{f} (назван {alt.name})")
            else:
                missing.append(f"{d}/{f}")
    if missing:
        sys.exit("❌ В репозитории не хватает файлов:\n  " + "\n  ".join(missing) +
                 "\nЗагрузи их на GitHub в эти папки (имена строчными) и сделай Manual Deploy.")

_fix_case()

_missing = [k for k in ("BOT_TOKEN", "SUPABASE_URL", "SUPABASE_KEY") if not os.getenv(k, "").strip()]
if _missing:
    sys.exit("❌ Не заданы переменные окружения: " + ", ".join(_missing) +
             "\nRender → твой сервис → Environment → добавь их и перезапусти (Manual Deploy).")

import asyncio
import html
import logging
import time

# совместимость: в aiogram тип называется BusinessMessagesDeleted
import aiogram.types as _t
if not hasattr(_t, "DeletedBusinessMessages") and hasattr(_t, "BusinessMessagesDeleted"):
    _t.DeletedBusinessMessages = _t.BusinessMessagesDeleted

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.config import cfg
from bot.handlers import admin, business, extras, payments, start
from bot.services import scheduler
from bot.services.gate import GateMiddleware
from bot.services.logs import audit, is_network_error

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
for _n in ("httpx", "httpcore"):  # без спама в логах Render
    logging.getLogger(_n).setLevel(logging.WARNING)

from bot.services.premium_emoji import prepare_method


class _PremiumBot(Bot):
    """Все методы бота проходят через __call__ — там подменяются обычные эмодзи на премиум."""
    async def __call__(self, method, request_timeout=None):
        return await super().__call__(prepare_method(method), request_timeout)


bot = _PremiumBot(cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
# порядок важен: админка первой (фильтр по ID), дальше остальное
dp.message.outer_middleware(GateMiddleware())
dp.callback_query.outer_middleware(GateMiddleware())
dp.include_routers(admin.router, payments.router, business.router, extras.router, start.router)

_tasks: set = set()
_seen: dict = {}
IGNORE = ("query is too old", "message is not modified", "message to edit not found", "query ID is invalid",
          "message can't be edited", "bot was blocked", "chat not found", "user is deactivated")


@dp.errors()
async def on_error(event: ErrorEvent):
    err = event.exception
    text = f"{type(err).__name__}: {err}"
    if is_network_error(err) or any(s in str(err) for s in IGNORE):
        logging.warning("пропущено (не баг): %s", text[:200])  # таймауты и мелочи — админу не пишем
        return True
    await audit("error", "unhandled", None, err=text[:300])
    logging.exception("Unhandled error", exc_info=err)
    sig = text[:80]
    if time.time() - _seen.get(sig, 0) > 600:  # одну и ту же ошибку — не чаще раза в 10 минут
        _seen[sig] = time.time()
        for aid in cfg.admin_ids:
            try:
                await bot.send_message(aid, f"🔴 <b>Ошибка</b>\n<code>{html.escape(text[:400])}</code>")
            except Exception:
                pass
    return True


@dp.startup()
async def on_startup(bot: Bot):
    await bot.set_my_commands([BotCommand(command="start", description="Запуск и инструкция"),
                               BotCommand(command="menu", description="Главное меню"),
                               BotCommand(command="buy", description="Купить подписку")])
    if cfg.webhook_base:
        await bot.set_webhook(f"{cfg.webhook_base}/webhook", secret_token=cfg.webhook_secret or None,
                              allowed_updates=dp.resolve_used_update_types())
    else:
        await bot.delete_webhook()
    t = asyncio.create_task(scheduler.run(bot))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
    logging.info("GhostSee started (%s)", "webhook" if cfg.webhook_base else "polling")


async def health(_request):
    return web.Response(text="ok")


async def canary_hit(request):
    """Публичный прозрачный маячок: записывает только токен и время открытия."""
    from html import escape as html_escape
    from bot.db import db
    token = request.match_info.get("token", "")
    rows = await db.select("gs_canary_tokens", {"token": f"eq.{token}"})
    if not rows:
        raise web.HTTPNotFound(text="Ссылка не найдена или отключена.")
    await db.insert("gs_canary_events", {"token": token}, returning=False)
    label = html_escape(rows[0].get("label") or "тестовая ссылка")
    page = ("<!doctype html><html lang='ru'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>GhostSee — тестовая ссылка</title>"
            "<body style='font:16px system-ui;max-width:620px;margin:12vh auto;padding:24px;color:#222'>"
            "<h2>Тестовая ссылка GhostSee</h2>"
            f"<p>Вы открыли: <b>{label}</b>.</p>"
            "<p>Владелец ссылки увидит факт и время открытия. IP-адрес, устройство и провайдер этой страницей не собираются.</p>"
            "</body></html>")
    return web.Response(text=page, content_type="text/html")




def main():
    if cfg.webhook_base:
        app = web.Application()
        app.router.add_get("/health", health)
        app.router.add_get("/", health)
        app.router.add_get("/canary/{token}", canary_hit)
        SimpleRequestHandler(dp, bot, secret_token=cfg.webhook_secret or None).register(app, path="/webhook")
        setup_application(app, dp, bot=bot)
        web.run_app(app, host="0.0.0.0", port=cfg.port, access_log=None)
    else:
        asyncio.run(dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types()))


if __name__ == "__main__":
    main()
