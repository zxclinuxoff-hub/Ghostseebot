from urllib.parse import quote

from aiogram.types import CopyTextButton, InlineKeyboardButton as B, InlineKeyboardMarkup as M

from .config import PLANS, cfg
from .services import billing_prices as BP


def start_kb(with_settings_url: bool = True) -> M:
    rows = [[B(text=f"📋 Скопировать @{cfg.bot_username}", copy_text=CopyTextButton(text=f"@{cfg.bot_username}"))]]
    if with_settings_url:
        rows.append([B(text="⚙️ Открыть настройки Telegram", url="tg://settings/edit")])
    rows.append([B(text="🏠 Главное меню", callback_data="menu")])
    return M(inline_keyboard=rows)


def main_menu() -> M:
    return M(inline_keyboard=[
        [B(text="👤 Личный кабинет", callback_data="cabinet"), B(text="👥 Рефералы", callback_data="refs")],
        [B(text="🛠 Команды и функции", callback_data="cmds"), B(text="💳 Купить подписку", callback_data="buy")],
        [B(text="🎰 Рулетка", callback_data="roulette"), B(text="⚙️ Настройки", callback_data="settings")],
        [B(text="💬 Поддержка / Инструкции", callback_data="support")],
    ])


def back_kb(extra=None) -> M:
    rows = list(extra or [])
    rows.append([B(text="⬅️ В меню", callback_data="back")])
    return M(inline_keyboard=rows)


def buy_kb(u) -> M:
    rows = []
    for key, p in PLANS.items():
        stars, pct = BP.price_for(u, key)
        label = f"{p['title']} — {stars}⭐" + (f" (−{pct}%)" if pct else "")
        rows.append([B(text=label, callback_data=f"pay:{key}")])
    return back_kb(rows)


def refs_kb(link: str) -> M:
    share = f"https://t.me/share/url?url={quote(link)}&text={quote('👻 GhostSee — видит удалённые сообщения и исчезающие фото. 7 дней бесплатно!')}"
    return back_kb([
        [B(text="📤 Поделиться", url=share)],
        [B(text="📢 Наш канал", url=cfg.channel_url)],
    ])


def channel_kb() -> M:
    return M(inline_keyboard=[
        [B(text="📢 Подписаться на канал", url=cfg.channel_url)],
        [B(text="✅ Я подписался", callback_data="check_sub")],
    ])


def roulette_kb() -> M:
    return back_kb([[B(text="🎰 Крутить", callback_data="spin")]])


def settings_kb(u) -> M:
    from .services import users as U
    def t(key, title):
        return [B(text=f"{'✅' if U.setting(u, key, key != 'silent') else '❌'} {title}", callback_data=f"set:{key}")]
    return back_kb([
        t("notify_deleted", "Удалённые сообщения"),
        t("notify_edited", "Изменённые сообщения"),
        t("silent", "Тихие уведомления (без звука)"),
    ])


def unmute_kb(bc: str, chat_id: int) -> M:
    return M(inline_keyboard=[[B(text="🔊 Размутить", callback_data=f"unmute:{bc}:{chat_id}")]])


def buy_shortcut() -> M:
    return M(inline_keyboard=[[B(text="💳 Купить подписку", callback_data="buy")]])


def admin_menu() -> M:
    return M(inline_keyboard=[
        [B(text="📊 Статистика", callback_data="adm:stats"), B(text="📜 Логи", callback_data="adm:logs")],
        [B(text="🤝 Партнёры", callback_data="adm:partners"), B(text="📣 Рассылка", callback_data="adm:broadcast")],
    ])
