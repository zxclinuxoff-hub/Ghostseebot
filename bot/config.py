import os
from dataclasses import dataclass


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _supabase_url() -> str:
    u = _env("SUPABASE_URL").rstrip("/")
    if u.endswith("/rest/v1"):
        u = u[: -len("/rest/v1")]
    return u if (not u or u.startswith("http")) else "https://" + u


def _ids(s: str) -> tuple:
    return tuple(int(x) for x in s.replace(" ", "").split(",") if x)


@dataclass(frozen=True)
class Config:
    bot_token: str = _env("BOT_TOKEN", "")
    admin_ids: tuple = _ids(_env("ADMIN_IDS", "8657771492"))
    supabase_url: str = _supabase_url()
    supabase_key: str = _env("SUPABASE_KEY", "")
    webhook_base: str = (_env("WEBHOOK_BASE_URL") or _env("RENDER_EXTERNAL_URL")).rstrip("/")  # Render задаёт RENDER_EXTERNAL_URL сам
    webhook_secret: str = _env("WEBHOOK_SECRET", "")
    port: int = int(_env("PORT", "8080"))
    channel: str = _env("CHANNEL", "@ghostsee_channel")
    bot_username: str = _env("BOT_USERNAME", "ghostseebot")
    trial_days: int = 7
    ai_key: str = _env("AI_API_KEY", "")
    ai_model: str = _env("AI_MODEL", "claude-haiku-5-5")

    @property
    def channel_url(self) -> str:
        return "https://t.me/" + self.channel.lstrip("@")

    @property
    def support_url(self) -> str:
        return _env("SUPPORT_URL") or f"tg://user?id={self.admin_ids[0]}"


cfg = Config()

# Единая подписка «Всё включено»
PLANS = {
    "m1": {"title": "1 месяц", "days": 30, "stars": 40},
    "m3": {"title": "3 месяца", "days": 90, "stars": 100},   # выгода 20⭐
    "y1": {"title": "1 год", "days": 365, "stars": 360},     # выгода 120⭐
}
# Добавь в конец файла Bot/config.py
LOG_CHAT_ID = -1004377590810
