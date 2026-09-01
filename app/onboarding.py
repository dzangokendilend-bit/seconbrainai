# Шаги онбординга «Моники» и валидация собранного профиля.
# Экраны (по решению Ивана, 7 шагов):
# 1 приветствие -> 2 микроопрос -> 3 профиль -> 4 модель ->
# 5 модули -> 6 API-ключи -> 7 пароль + резюме.
import re

import auth

# AI1: реестр моделей = MODEL_REGISTRY (app/model_registry.py) — единственный
# источник правды. Ровно 3 модели: glm-fast (OpenRouter), luna (OpenAI),
# groq-whisper (Groq, только speech-to-text — в чате не выбирается).
# Legacy (glm на open.bigmodel.cn, openrouter/auto, orv-claude) — из выбора убраны.
import model_registry

MODELS = [
    {"id": "glm-fast", "name": "GLM 5.3 Fast", "service": "openrouter",
     "role": "умная модель: чат, терминал, вики, digest", "desc": "основная",
     "api_model": model_registry.get("glm-fast")["model_id"]},
    {"id": "luna", "name": "ChatGPT Luna", "service": "openai",
     "role": "лёгкая модель: повседневный чат", "desc": "быстрая · живой диалог",
     "api_model": model_registry.get("luna")["model_id"]},
]
DEFAULT_MODEL = "glm-fast"
SOURCES = ["друзья", "TikTok", "Instagram", "другое"]
PURPOSES = ["личный дневник", "знания", "проекты", "другое"]
LANGUAGES = ["ru", "ua", "en"]
# AI1: ровно 3 сервиса ключей (по провайдерам MODEL_REGISTRY)
KEY_SERVICES = ["openrouter", "openai", "groq"]
KEY_LABELS = {
    "openrouter": ["OpenRouter (GLM 5.3 Fast)", "главная умная модель — чат, терминал, вики"],
    "openai": ["OpenAI Platform (ChatGPT Luna)", "лёгкая модель — повседневный чат"],
    "groq": ["Groq Whisper", "только расшифровка голосовых и аудио (медиа в чате)"],
}
# legacy-сервисы старых профилей: ключи сохранены, но в routing не участвуют
LEGACY_SERVICES = ("glm", "smart", "luna")


def service_for(model_id):
    """Сервис-исполнитель для id модели из реестра (None если неизвестна)."""
    for m in MODELS:
        if m["id"] == model_id:
            return m["service"]
    return None


def api_model(model_id):
    """Реальный id модели для запроса к провайдеру."""
    for m in MODELS:
        if m["id"] == model_id:
            return m.get("api_model") or model_id
    return None


def normalize_model(model_id):
    """Миграция старых профилей: устаревший id -> валидная модель AI1.
    Legacy (glm-5.3-fast, orv-auto, orv-claude, gpt-5.6-luna как id реестра,
    ox-alpha) -> glm-fast (primary)."""
    if model_id in [m["id"] for m in MODELS]:
        return model_id
    return DEFAULT_MODEL


def validate(payload):
    errs = []
    username = (payload.get("username") or "").strip()
    e = auth.username_error(username)
    if e:
        errs.append(e)
    password = payload.get("password") or ""
    if len(password) < 6:
        errs.append("пароль: минимум 6 символов")
    survey = payload.get("survey") or {}
    if (survey.get("source") or "") not in SOURCES:
        errs.append("не выбран источник («откуда узнали»)")
    prefs = payload.get("prefs") or {}
    if prefs.get("language") not in LANGUAGES:
        errs.append("язык интерфейса не выбран")
    if prefs.get("model") not in [m["id"] for m in MODELS]:
        errs.append("модель не выбрана")
    load = prefs.get("daily_load")
    if not isinstance(load, int) or not 1 <= load <= 10:
        errs.append("ползунок нагрузки: 1-10")
    modules = payload.get("modules") or {}
    for m in ("wikipedia", "telegram", "analytics"):
        if not isinstance(modules.get(m), bool):
            errs.append("модули не выбраны")
            break
    keys = payload.get("keys") or {}
    for svc in KEY_SERVICES:
        if not isinstance(keys.get(svc), str) or len(keys.get(svc).strip()) < 8:
            errs.append("ключ " + svc + ": пустой или слишком короткий (бета: ключи обязательны)")
    return errs, payload
