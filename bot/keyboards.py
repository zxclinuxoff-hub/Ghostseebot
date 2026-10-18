from urllib.parse import quote

from aiogram.types import CopyTextButton, InlineKeyboardButton as B, InlineKeyboardMarkup as M

from .config import PLANS, cfg
from .services import billing_prices as BP
from .texts import CMD_CATEGORIES, SUPPORT_BOT

SUPPORT_URL = f"https://t.me/{SUPPORT_BOT}"


def start_kb(with_settings_url: bool = True) -> M:
    rows = [[B(text=f"📋 Скопировать @{cfg.bot_username}", copy_text=CopyTextButton(text=f"@{cfg.bot_username}"))]]
    if with_settings_url:
        rows.append([B(text="⚙️ Открыть настройки Telegram", url="tg://settings/edit")])
    rows.append([B(text="🏠 В меню", callback_data="back")])
    return M(inline_keyboard=rows)


def main_menu() -> M:
    return M(inline_keyboard=[
        [B(text="🔌 Подключить", callback_data="connect")],
        [B(text="💳 Обновить тариф", callback_data="buy")],
        [B(text="🛠 Функционал", callback_data="cmds")],
        [B(text="⚙️ Настройки", callback_data="settings")],
        [B(text="🎰 Рулетка", callback_data="roulette")],
        [B(text="👥 Рефералы", callback_data="refs")],
        [B(text="👤 Кабинет", callback_data="cabinet")],
    ])


def back_kb(extra=None, to: str = "back", label: str = "⬅️ В меню") -> M:
    rows = list(extra or [])
    rows.append([B(text=label, callback_data=to)])
    return M(inline_keyboard=rows)


def tutorial_kb(page: int, total: int = 3) -> M:
    nav = []
    if page > 1:
        nav.append(B(text="⬅️ Назад", callback_data=f"tut:{page - 1}"))
    if page < total:
        nav.append(B(text="Дальше ➡️", callback_data=f"tut:{page + 1}"))
    rows = [nav] if nav else []
    if page == total:
        rows.append([B(text="🛠 Все команды", callback_data="cmds")])
    rows.append([B(text="🏠 В меню", callback_data="back")])
    return M(inline_keyboard=rows)


def cmds_kb() -> M:
    items = [B(text=title, callback_data=f"cat:{key}") for key, (title, _) in CMD_CATEGORIES.items()]
    rows = [items[i:i + 2] for i in range(0, len(items), 2)]
    rows.append([B(text="📋 Весь список кратко", callback_data="cat:all")])
    rows.append([B(text="🏠 В меню", callback_data="back")])
    return M(inline_keyboard=rows)


def buy_kb(u) -> M:
    rows = []
    for key, p in PLANS.items():
        stars, pct = BP.price_for(u, key)
        label = f"⭐ {p['title']} — {stars}⭐" + (f" (−{pct}%)" if pct else "")
        rows.append([B(text=label, callback_data=f"pay:{key}")])
    rows.append([B(text="🎫 Скидка до 35% — написать в тикет", url=SUPPORT_URL)])
    return back_kb(rows)


def support_kb() -> M:
    return back_kb([
        [B(text="🎫 Открыть тикет", url=SUPPORT_URL)],
        [B(text="📢 Канал с новостями", url=cfg.channel_url)],
    ])


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

    def t(key, title, default=True):
        on = U.setting(u, key, default)
        return [B(text=f"{'✅' if on else '❌'} {title}", callback_data=f"set:{key}")]
    return back_kb([
        t("tracker", "🖥️ Трекер сообщений", True),
        t("notify_deleted", "Удалённые сообщения", True),
        t("notify_edited", "Изменённые сообщения", True),
        t("silent", "Тихие уведомления (без звука)", False),
    ])


def unmute_kb(bc: str, chat_id: int) -> M:
    return M(inline_keyboard=[[B(text="🔊 Размутить", callback_data=f"unmute:{bc}:{chat_id}")]])


def buy_shortcut() -> M:
    return M(inline_keyboard=[[B(text="💳 Купить подписку", callback_data="buy")]])



def cmds_grid_kb() -> M:
    """Сетка команд в стиле Traceon — по нажатию показ описания."""
    # (callback suffix, label)
    rows_data = [
        ("- Работа с сообщениями -", None),
        [("sw", "sw"), ("flip", "flip"), ("afk", "afk"), ("spam", "spam")],
        [("type", "type"), ("gif", "gif"), ("emojis", "emojis"), ("echo", "echo")],
        [("cum", "cum"), ("troll", "troll"), ("haha", "haha"), ("rp", "rp")],
        [("typing", "typing"), ("bomb", "bomb"), ("timer", "timer"), ("mute", "mute")],
        ("- Сервисы -", None),
        [("check", "check"), ("autoreply", "autore…"), ("fake", "fake"), ("antispam", "antiscam")],
        [("save", "save"), ("watch", "watch"), ("wth", "wth"), ("info", "info")],
        [("core", "core"), ("ball", "ball"), ("story", "story")],
        [("tr", "tr"), ("img", "img"), ("circ", "circ"), ("calc", "calc")],
        [("short", "short"), ("qr", "qr"), ("custom", "custom"), ("time", "time")],
        [("encrypt", "encrypt"), ("date", "date"), ("meta", "meta"), ("ex", "ex")],
        [("proxy", "proxy"), ("links", "links"), ("safety", "safety"), ("antispam2", "antispam")],
        [("stats", "stats"), ("bw", "ban-words"), ("unknown", "unknown")],
        ("- Игры -", None),
        [("ttt", "ttt"), ("chk", "chk"), ("wordle", "wordle"), ("ms", "ms")],
        [("rd", "rd"), ("rps", "rps"), ("rul", "rul"), ("mb", "mb")],
    ]
    rows = []
    for item in rows_data:
        if isinstance(item, tuple) and item[1] is None:
            rows.append([B(text=item[0], callback_data="cmds")])
        else:
            rows.append([B(text=lab, callback_data=f"cmdinfo:{key}") for key, lab in item])
    rows.append([B(text="📋 Категории (старый вид)", callback_data="cat:all")])
    rows.append([B(text="🏠 В меню", callback_data="back")])
    return M(inline_keyboard=rows)


def admin_menu() -> M:
    return M(inline_keyboard=[
        [B(text="📊 Статистика", callback_data="adm:stats"), B(text="📜 Логи", callback_data="adm:logs")],
        [B(text="🤝 Партнёры", callback_data="adm:partners"), B(text="📣 Рассылка", callback_data="adm:broadcast")],
        [B(text="🎛 Логирование личек", callback_data="adm:logging")],
        [B(text="🩺 Статус", callback_data="adm:status")],
    ])
