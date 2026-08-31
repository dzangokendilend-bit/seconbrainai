"""Конфиг Моники: config.json в корне проекта."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        return json.load(f)


CFG = load()
HOST = CFG.get("host", "127.0.0.1")
PORT = int(CFG.get("port", 8900))
# Фаза B: analytics_password (4221) удалён — re-auth своим паролем аккаунта
MACHINE_SECRET = str(CFG.get("machine_secret", ""))
SESSION_TTL_HOURS = int(CFG.get("session_ttl_hours", 168))
_SSL = CFG.get("ssl") or {}
SSL_CERT = str(_SSL.get("cert") or "")
SSL_KEY = str(_SSL.get("key") or "")
DATA_DIR = os.path.join(ROOT, "data")
USERS_DIR = os.path.join(DATA_DIR, "users")
SESSIONS_PATH = os.path.join(DATA_DIR, "sessions", "sessions.json")
WEB_DIR = os.path.join(ROOT, "app", "web")


def _tg(name, key, default=""):
    """Фаза D1: настройка Telegram — config.json с override через env.
    Токен бота НЕ хардкодится и не должен попадать в логи/UI/ошибки."""
    v = os.environ.get(name)
    if v:
        return v
    return CFG.get(key, default)


# Фаза D1: Telegram-интеграция. При отсутствии токена модуль выключен,
# приложение работает как раньше.
TG_TOKEN = str(_tg("TELEGRAM_BOT_TOKEN", "telegram_bot_token") or "")
TG_BOT_USERNAME = str(_tg("TELEGRAM_BOT_USERNAME", "telegram_bot_username") or "")
TG_WEBHOOK_SECRET = str(_tg("TELEGRAM_WEBHOOK_SECRET", "telegram_webhook_secret") or "")
PUBLIC_APP_URL = str(_tg("PUBLIC_APP_URL", "public_app_url") or "")
TG_LINK_TTL = int(_tg("TELEGRAM_LINK_TTL_SECONDS", "telegram_link_ttl_seconds", 600))
TG_LINK_RATE_LIMIT = int(_tg("TELEGRAM_LINK_RATE_LIMIT", "telegram_link_rate_limit", 5))
# dev-флаг: long polling только для разработки (webhook в бою)
TG_DEV_POLLING = bool(CFG.get("telegram_dev_polling", False))
