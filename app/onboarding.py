# Шаги онбординга «Моники» и валидация собранного профиля.
# Экраны (по решению Ивана, 7 шагов):
# 1 приветствие -> 2 микроопрос -> 3 профиль -> 4 модель ->
# 5 модули -> 6 API-ключи -> 7 пароль + резюме.
import re

import auth

MODELS = [
    {"id": "glm-5.3-fast", "name": "GLM 5.3 Fast", "service": "glm",
     "role": "терминал и быстрые операции"},
    {"id": "smart", "name": "Умная модель (ядро анализа, аналог ox alpha)",
     "service": "smart", "role": "глубокая работа со second-brain"},
    {"id": "gpt-5.6-luna", "name": "ChatGPT 5.6 Luna", "service": "luna",
     "role": "Telegram-бот и чат на сайте"},
]
SOURCES = ["друзья", "TikTok", "Instagram", "другое"]
PURPOSES = ["личный дневник", "знания", "проекты", "другое"]
LANGUAGES = ["ru", "ua", "en"]
KEY_SERVICES = ["glm", "smart", "luna"]


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
