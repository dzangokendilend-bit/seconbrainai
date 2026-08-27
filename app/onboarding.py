# Шаги онбординга «Моники» и валидация собранного профиля.
# Экраны (по решению Ивана, 7 шагов):
# 1 приветствие -> 2 микроопрос -> 3 профиль -> 4 модель ->
# 5 модули -> 6 API-ключи -> 7 пароль + резюме.
import re

import auth

# Единый реестр моделей (Фаза 5-B). ox alpha выведена из системы:
# сервис smart теперь = OpenRouter, конкретные модели выбирает пользователь.
# api_model — реальный id для запроса к провайдеру; id — внутренний идентификатор.
MODELS = [
    {"id": "glm-5.3-fast", "name": "GLM 5.3 Fast", "service": "glm",
     "role": "терминал и быстрые операции", "desc": "быстрая",
     "api_model": "glm-5.3-fast"},
    {"id": "orv-auto", "name": "OpenRouter Auto", "service": "smart",
     "role": "глубокая работа со second-brain", "desc": "глубокая · роутер сам выберет модель",
     "api_model": "openrouter/auto"},
    {"id": "orv-claude", "name": "Claude Sonnet (OpenRouter)", "service": "smart",
     "role": "глубокая работа со second-brain", "desc": "глубокая · аккуратный длинный текст",
     "api_model": "anthropic/claude-sonnet-4.5"},
    {"id": "gpt-5.6-luna", "name": "ChatGPT 5.6 Luna", "service": "luna",
     "role": "Telegram-бот и чат на сайте", "desc": "креативная · живой диалог",
     "api_model": "gpt-5.6-luna"},
]
DEFAULT_MODEL = "gpt-5.6-luna"
SOURCES = ["друзья", "TikTok", "Instagram", "другое"]
PURPOSES = ["личный дневник", "знания", "проекты", "другое"]
LANGUAGES = ["ru", "ua", "en"]
KEY_SERVICES = ["glm", "smart", "luna"]
KEY_LABELS = {
    "glm": ["GLM 5.3 Fast", "терминал и быстрые операции"],
    "smart": ["OpenRouter", "глубокие модели для second-brain"],
    "luna": ["ChatGPT 5.6 Luna", "Telegram-бот и чат на сайте"],
}


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
    """Миграция старых профилей: устаревший id -> ближайшая валидная модель.
    Старый 'smart' (ox alpha) -> первая модель сервиса smart."""
    if model_id in [m["id"] for m in MODELS]:
        return model_id
    legacy_service = {"smart": "smart", "ox-alpha": "smart"}.get(model_id)
    if legacy_service:
        for m in MODELS:
            if m["service"] == legacy_service:
                return m["id"]
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
