# AI1: MODEL_REGISTRY — единственный источник правды о моделях Моники.
# Ровно 3 модели: glm-fast (OpenRouter), luna (OpenAI), groq-whisper (Groq).
# URL строится ТОЛЬКО здесь: base_url + endpoint ровно один раз
# (гарантия: нет /v1/v1 и двойного /chat/completions).
# Ключи — только env/.env (OPENROUTER_API_KEY / OPENAI_API_KEY / GROQ_API_KEY).
# GLM_API_KEY — legacy, в routing не участвует.
import urllib.error

import config

MODELS = {
    "glm-fast": {
        "provider": "openrouter", "kind": "chat",
        "display": "GLM 5.3 Fast", "role": "primary",
        "base_url": "https://openrouter.ai/api/v1",
        "endpoint": "/chat/completions",
        # проверено live: GET https://openrouter.ai/api/v1/models + ping 200
        "model_id": "z-ai/glm-5.3-flash",
        "env_key": "OPENROUTER_API_KEY", "enabled": True,
    },
    "luna": {
        "provider": "openai", "kind": "chat",
        "display": "ChatGPT Luna", "role": "light",
        "base_url": "https://api.openai.com/v1",
        "endpoint": "/chat/completions",
        # проверено live: GET https://api.openai.com/v1/models (id существует)
        # + ping: ключ принят; новым моделям OpenAI нужен max_completion_tokens
        "model_id": "gpt-5.6-luna",
        "env_key": "OPENAI_API_KEY", "enabled": True,
    },
    "groq-whisper": {
        "provider": "groq", "kind": "transcription",
        "display": "Groq Whisper", "role": "speech_to_text",
        "base_url": "https://api.groq.com/openai/v1",
        "endpoint": "/audio/transcriptions",
        "model_id": "whisper-large-v3-turbo",
        "env_key": "GROQ_API_KEY", "enabled": True,
    },
}

DEFAULT_CHAT = "glm-fast"
# безопасные ключи, разрешённые клиенту для chat-роутинга
CHAT_KEYS = ("glm-fast", "luna")
PROVIDERS = ("openrouter", "openai", "groq")

# ── безопасные коды ошибок (сырой «HTTP Error 404» пользователю не показывается) ──
ERROR_MESSAGES = {
    "API_KEY_MISSING": "Для этой модели не настроен API-ключ",
    "API_KEY_UNAUTHORIZED": "Провайдер не принял API-ключ. Проверь ключ и доступ к модели",
    "MODEL_ACCESS_DENIED": "Нет доступа к этой модели на твоём тарифе провайдера",
    "PROVIDER_ENDPOINT_NOT_FOUND": "Провайдер не нашёл такой endpoint — проверь конфигурацию",
    "MODEL_NOT_FOUND": "Модель недоступна или её идентификатор указан неверно",
    "PROVIDER_RATE_LIMITED": "Провайдер ограничил частоту запросов. Попробуй позже",
    "PROVIDER_BILLING_REQUIRED": "У провайдера исчерпана квота или требуется оплата",
    "PROVIDER_TIMEOUT": "Провайдер не ответил вовремя. Попробуй ещё раз",
    "PROVIDER_NETWORK_ERROR": "Сеть недоступна или провайдер не отвечает",
    "MODEL_NOT_ALLOWED": "Эта модель пока недоступна в закрытом тестировании",
}


def get(key):
    """Запись реестра или None."""
    return MODELS.get(key)


def chat_model(key):
    """Валидация chat-ключа против allowlist (клиент не может прислать своё)."""
    if key in CHAT_KEYS and MODELS.get(key, {}).get("kind") == "chat":
        return MODELS[key]
    return None


def build_url(key):
    """base_url + endpoint РОВНО ОДИН раз. Гарантии: без /v1/v1 и без
    двойного /chat/completions (проверяется юнит-тестами на точные URL)."""
    m = MODELS.get(key)
    if not m:
        raise KeyError("неизвестная модель: " + str(key))
    base = m["base_url"].rstrip("/")
    ep = m["endpoint"]
    if not ep.startswith("/"):
        ep = "/" + ep
    # защита от дублирования: endpoint уже в base_url (legacy-конфиг) — не дублируем
    if base.endswith(ep):
        return base
    return base + ep


def env_key_name(key):
    """Имя env-переменной ключа для модели (или None)."""
    m = MODELS.get(key)
    return (m or {}).get("env_key")


def resolve_env_key(key):
    """Серверный fallback-ключ модели из env/.env (строка или "")."""
    name = env_key_name(key)
    return str(config.env(name) or "") if name else ""


def provider_env_key(provider):
    """Fallback-ключ по имени провайдера (openrouter/openai/groq)."""
    for m in MODELS.values():
        if m["provider"] == provider:
            return str(config.env(m["env_key"]) or "")
    return ""


def http_error_to_code(status, body=""):
    """HTTP-статус (+ опциональное тело) → безопасный код ошибки.
    Никогда не возвращает сырые детали провайдера."""
    low = str(body or "").lower()
    if status == 401:
        return "API_KEY_UNAUTHORIZED"
    if status == 403:
        return "MODEL_ACCESS_DENIED"
    if status == 404:
        # 404 на model id vs endpoint: OpenAI/OpenRouter пишут model в теле
        if "model" in low and ("not found" in low or "no endpoints" in low
                               or "no allowed" in low):
            return "MODEL_NOT_FOUND"
        return "PROVIDER_ENDPOINT_NOT_FOUND"
    if status == 429:
        return "PROVIDER_RATE_LIMITED"
    if status and 400 <= status < 500:
        if "insufficient" in low or "billing" in low or "quota" in low:
            return "PROVIDER_BILLING_REQUIRED"
        if "model" in low and ("not found" in low or "does not exist" in low):
            return "MODEL_NOT_FOUND"
        return "PROVIDER_ENDPOINT_NOT_FOUND"
    if status and status >= 500:
        return "PROVIDER_NETWORK_ERROR"
    return "PROVIDER_NETWORK_ERROR"


def safe_error(code):
    """{code, message} для клиента — без ключей, URL и тел запросов."""
    return {"code": code, "message": ERROR_MESSAGES.get(code, code)}
