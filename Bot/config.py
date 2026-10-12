import os
from dataclasses import dataclass


def _ids(s: str) -> tuple:
    return tuple(int(x) for x in s.replace(" ", "").split(",") if x)


@dataclass(frozen=True)
class Config:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    admin_ids: tuple = _ids(os.getenv("ADMIN_IDS", "8657771492"))
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_key: str = os.getenv("SUPABASE_KEY", "")
    webhook_base: str = os.getenv("WEBHOOK_BASE_URL", "").rstrip("/")
    webhook_secret: str = os.getenv("WEBHOOK_SECRET", "")
    port: int = int(os.getenv("PORT", "8080"))
    channel: str = os.getenv("CHANNEL", "@ghostsee_channel")
    bot_username: str = os.getenv("BOT_USERNAME", "ghostseebot")
    trial_days: int = 7
    ai_key: str = os.getenv("AI_API_KEY", "")
    ai_model: str = os.getenv("AI_MODEL", "claude-haiku-5-5")

    @property
    def channel_url(self) -> str:
        return "https://t.me/" + self.channel.lstrip("@")

    @property
    def support_url(self) -> str:
        return os.getenv("SUPPORT_URL") or f"tg://user?id={self.admin_ids[0]}"


cfg = Config()

# Единая подписка «Всё включено»
PLANS = {
    "m1": {"title": "1 месяц", "days": 30, "stars": 40},
    "m3": {"title": "3 месяца", "days": 90, "stars": 100},   # выгода 20⭐
    "y1": {"title": "1 год", "days": 365, "stars": 360},     # выгода 120⭐
}
