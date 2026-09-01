"""Конфиг Моники — единый слой секретов и настроек (P0).

Приоритет источников:
  1. переменные окружения (env)          — высший приоритет
  2. .env в корне проекта (KEY=VALUE)    — секреты и переопределения
  3. config.json                         — НЕ-секретные настройки
     (mock_llm, providers base_url/model, host/port, ssl, флаги)

Секреты (machine_secret, telegram_bot_token, webhook_secret, LLM-ключи)
берутся ТОЛЬКО из env/.env. config.json с секретами ещё работает как
устаревший fallback (миграционный период), но при старте печатается
warning «перенесите в .env» — без вывода значений.

MONICA_DATA_DIR — каталог mutable-данных (users/, telegram/, sessions/,
audit/, backups/, tmp/). По умолчанию <проект>/data.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── .env: простой stdlib-парсер (KEY=VALUE, # комментарии, кавычки) ──

def parse_dotenv(text):
    """Разбор текста .env → dict. Без интерполяции и экспорта.
    Пустые значения пропускаются (не перекрывают config.json)."""
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        if k and v:
            out[k] = v
    return out


def _load_dotenv(path):
    try:
        with open(path, encoding="utf-8") as f:
            return parse_dotenv(f.read())
    except OSError:
        return {}


_DOTENV = _load_dotenv(os.path.join(ROOT, ".env"))


def env(name, default=""):
    """env → .env → default. Пустая строка в env НЕ перекрывает .env."""
    v = os.environ.get(name)
    if v is None or v == "":
        v = _DOTENV.get(name, "")
    return v if v else default


def load():
    try:
        with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


CFG = load()

# ── не-секретные настройки (config.json + env-переопределения) ──
HOST = env("MONICA_HOST") or str(CFG.get("host", "127.0.0.1"))
PORT = int(env("PORT") or CFG.get("port", 8900))
SESSION_TTL_HOURS = int(CFG.get("session_ttl_hours", 168))
_SSL = CFG.get("ssl") or {}
SSL_CERT = str(_SSL.get("cert") or "")
SSL_KEY = str(_SSL.get("key") or "")

# ── секреты: env/.env только; config.json — устаревший fallback ──
MACHINE_SECRET = str(env("MONICA_MACHINE_SECRET")
                     or CFG.get("machine_secret") or "")

# ── Telegram (Фаза D1 + P0: env/.env приоритетнее config.json) ──
TG_TOKEN = str(env("TELEGRAM_BOT_TOKEN")
               or CFG.get("telegram_bot_token") or "")
TG_BOT_USERNAME = str(env("TELEGRAM_BOT_USERNAME")
                      or CFG.get("telegram_bot_username") or "")
TG_WEBHOOK_SECRET = str(env("TELEGRAM_WEBHOOK_SECRET")
                        or CFG.get("telegram_webhook_secret") or "")
PUBLIC_APP_URL = str(env("PUBLIC_APP_URL")
                     or CFG.get("public_app_url") or "")
TG_LINK_TTL = int(env("TELEGRAM_LINK_TTL_SECONDS")
                  or CFG.get("telegram_link_ttl_seconds", 600))
TG_LINK_RATE_LIMIT = int(env("TELEGRAM_LINK_RATE_LIMIT")
                         or CFG.get("telegram_link_rate_limit", 5))
# dev-флаг: long polling только для разработки. env-override для doctor/CI.
TG_DEV_POLLING = str(env("TELEGRAM_DEV_POLLING") or "").lower() in (
    "1", "true", "yes") or bool(CFG.get("telegram_dev_polling", False))

# ── серверные fallback LLM-ключи (env only; НЕ отправляются клиенту) ──
# Используются, только если у пользователя нет своего ключа сервиса.
ENV_LLM_KEYS = {
    "glm": str(env("GLM_API_KEY") or ""),
    "smart": str(env("OPENROUTER_API_KEY") or ""),
    "luna": str(env("OPENAI_API_KEY") or ""),
}

# ── data directory (P0): MONICA_DATA_DIR или dev-default <проект>/data ──
DATA_DIR = os.path.abspath(env("MONICA_DATA_DIR")
                           or os.path.join(ROOT, "data"))
USERS_DIR = os.path.join(DATA_DIR, "users")
SESSIONS_PATH = os.path.join(DATA_DIR, "sessions", "sessions.json")
TMP_DIR = os.path.join(DATA_DIR, "tmp")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
WEB_DIR = os.path.join(ROOT, "app", "web")

# секретные ключи config.json — для startup-warning (значения не выводятся)
_SECRET_CFG_KEYS = ("machine_secret", "telegram_bot_token",
                    "telegram_webhook_secret")


def data_dir_problem():
    """Проверка DATA_DIR: None если всё хорошо, иначе текст проблемы.
    DATA_DIR должен существовать/создаваться, быть доступным на запись
    и НЕ совпадать с каталогом исходного кода (ROOT, ROOT/app)."""
    bad = os.path.abspath(DATA_DIR) in (os.path.abspath(ROOT),
                                        os.path.abspath(os.path.join(ROOT, "app")))
    if bad:
        return "MONICA_DATA_DIR не может быть каталогом исходного кода"
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except OSError as e:
        return "DATA_DIR не создаётся: " + str(e)
    probe = os.path.join(DATA_DIR, ".write_probe")
    try:
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
    except OSError as e:
        return "DATA_DIR недоступна для записи: " + str(e)
    return None


def secrets_in_config():
    """Список имён секретных ключей, оставшихся в config.json (без значений)."""
    return [k for k in _SECRET_CFG_KEYS if str(CFG.get(k) or "").strip()]


def startup_report():
    """Безопасный startup report при запуске сервера. Никаких значений
    секретов, токенов и raw env — только факты вкл/выкл."""
    lines = []
    if TG_TOKEN and TG_DEV_POLLING and (TG_WEBHOOK_SECRET and PUBLIC_APP_URL):
        lines.append("[ERROR] Telegram: polling и webhook включены "
                     "одновременно — выбери один транспорт")
    elif TG_TOKEN and TG_DEV_POLLING:
        lines.append("[OK] Telegram polling enabled")
    elif TG_TOKEN and TG_WEBHOOK_SECRET and PUBLIC_APP_URL:
        lines.append("[OK] Telegram webhook enabled")
    elif TG_TOKEN:
        lines.append("[WARN] Telegram token задан, но транспорт не выбран "
                     "(telegram_dev_polling или webhook)")
    else:
        lines.append("[INFO] Telegram disabled (токен не задан)")
    if CFG.get("mock_llm"):
        lines.append("[OK] Mock LLM mode (реальные провайдеры не вызываются)")
    else:
        lines.append("[WARN] Real LLM mode is enabled (mock_llm: false)")
    present = [s for s, k in ENV_LLM_KEYS.items() if k]
    lines.append("[INFO] Server fallback LLM keys (env): "
                 + (", ".join(present) if present else "нет"))
    lines.append("[INFO] Data dir: " + DATA_DIR)
    prob = data_dir_problem()
    if prob:
        lines.append("[ERROR] Data dir: " + prob)
    else:
        lines.append("[OK] Data dir доступна для записи")
    if not MACHINE_SECRET:
        lines.append("[ERROR] MONICA_MACHINE_SECRET не задан — "
                     "ключи пользователей не будут расшифровываться")
    leftover = secrets_in_config()
    if leftover:
        lines.append("[WARN] Секреты обнаружены в config.json ("
                     + ", ".join(leftover)
                     + ") — перенесите в .env (значения скрыты)")
    for l in lines:
        print(l, file=sys.stderr)
    return lines
