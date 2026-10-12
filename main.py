import asyncio
import html
import logging
import time

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.config import cfg
from bot.handlers import admin, business, payments, start
from bot.services import scheduler
from bot.services.logs import audit

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

bot = Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
# порядок важен: админка первой (фильтр по ID), дальше остальное
dp.include_routers(admin.router, payments.router, business.router, start.router)

_tasks: set = set()
_last_err = {"t": 0.0}


@dp.errors()
async def on_error(event: ErrorEvent):
    err = event.exception
    await audit("error", "unhandled", None, err=f"{type(err).__name__}: {err}"[:300])
    logging.exception("Unhandled error", exc_info=err)
    if time.time() - _last_err["t"] > 30:  # не спамим админу
        _last_err["t"] = time.time()
        for aid in cfg.admin_ids:
            try:
                await bot.send_message(aid, f"🔴 <b>Ошибка</b>\n<code>{html.escape(type(err).__name__ + ': ' + str(err)[:400])}</code>")
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


def main():
    if cfg.webhook_base:
        app = web.Application()
        app.router.add_get("/health", lambda r: web.Response(text="ok"))
        app.router.add_get("/", lambda r: web.Response(text="ghostsee"))
        SimpleRequestHandler(dp, bot, secret_token=cfg.webhook_secret or None).register(app, path="/webhook")
        setup_application(app, dp, bot=bot)
        web.run_app(app, host="0.0.0.0", port=cfg.port)
    else:
        asyncio.run(dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types()))


if __name__ == "__main__":
    main()
