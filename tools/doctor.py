# -*- coding: utf-8 -*-
"""tools/doctor.py — безопасные проверки готовности Моники (P0).

Запуск:  python tools/doctor.py

Вывод: [OK]/[WARN]/[ERROR] по каждой проверке. БЕЗ секретов, токенов и
абсолютных путей (пути печатаются относительные, значения — только
факты вкл/выкл). Код возврата: 0 — нет ERROR, 1 — есть ERROR.
"""
import json
import os
import subprocess
import sys
import urllib.request
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import config  # noqa: E402

RESULTS = []


def add(level, msg):
    RESULTS.append((level, msg))
    print("[%s] %s" % (level, msg))


def rel(path):
    """Относительный путь (без абсолютов в выводе)."""
    try:
        r = os.path.relpath(path, ROOT)
        return r if not r.startswith("..") else "<вне проекта>"
    except ValueError:
        return "<вне проекта>"


def check_git_tracked(relpath):
    """True если файл tracked в git (git ls-files)."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "--", relpath], cwd=ROOT,
            capture_output=True, text=True, timeout=10)
        return bool(out.stdout.strip())
    except Exception:
        return None  # git недоступен — проверка пропущена


def main():
    print("monica doctor — P0\n" + "-" * 40)

    # 1. конфиг загружен
    if isinstance(config.CFG, dict) and config.CFG:
        add("OK", "config.json загружен")
    else:
        add("WARN", "config.json пуст или отсутствует "
                    "(работают значения по умолчанию)")

    # 2. data dir
    prob = config.data_dir_problem()
    if prob:
        add("ERROR", "data dir: " + prob)
    else:
        add("OK", "data dir доступна и writable: " + rel(config.DATA_DIR))

    # 3. vault path (users/)
    if os.path.isdir(config.USERS_DIR):
        add("OK", "users/ (vault-хранилище) доступно: " + rel(config.USERS_DIR))
    else:
        add("WARN", "users/ ещё не создана (создастся при регистрации)")

    # 4. machine_secret
    if config.MACHINE_SECRET:
        add("OK", "machine_secret задан (значение скрыто)")
    else:
        add("ERROR", "MONICA_MACHINE_SECRET не задан — keys.enc "
                     "пользователей не расшифровывается")

    # 5-6. Telegram: вкл/выкл + ровно один транспорт
    polling = bool(config.TG_TOKEN and config.TG_DEV_POLLING)
    webhook = bool(config.TG_TOKEN and config.TG_WEBHOOK_SECRET
                   and config.PUBLIC_APP_URL)
    if not config.TG_TOKEN:
        add("INFO", "Telegram выключен (токен не задан)")
    else:
        add("OK", "Telegram включён (токен задан, значение скрыто)")
        if polling and webhook:
            add("ERROR", "конфликт транспортов: polling и webhook "
                         "включены одновременно — оставь один")
        elif polling:
            add("WARN", "транспорт: polling (dev-режим; для production "
                        "используй webhook)")
        elif webhook:
            add("OK", "транспорт: webhook")
        else:
            add("WARN", "транспорт не выбран: нужен telegram_dev_polling "
                        "или TELEGRAM_WEBHOOK_SECRET+PUBLIC_APP_URL")

    # 7. PUBLIC_APP_URL валиден если webhook
    if config.TG_WEBHOOK_SECRET and config.PUBLIC_APP_URL:
        u = urlparse(config.PUBLIC_APP_URL)
        if u.scheme == "https" and u.netloc:
            add("OK", "PUBLIC_APP_URL: https и домен заданы")
        else:
            add("ERROR", "PUBLIC_APP_URL должен быть https://… "
                         "(webhook Telegram работает только по HTTPS)")

    # 8. LLM-ключи (факты, без значений)
    present = [s for s, k in config.ENV_LLM_KEYS.items() if k]
    add("OK", "серверные fallback LLM-ключи (env): "
              + (", ".join(present) if present else "не заданы"))

    # 9. mock mode
    if config.CFG.get("mock_llm"):
        add("OK", "mock_llm: true — реальные провайдеры не вызываются")
    else:
        add("WARN", "mock_llm: false — real mode (запросы идут к "
                    "провайдерам по ключам пользователей/fallback)")

    # 10. backup dir
    try:
        os.makedirs(config.BACKUP_DIR, exist_ok=True)
        add("OK", "backup dir доступна: " + rel(config.BACKUP_DIR))
    except OSError as e:
        add("ERROR", "backup dir недоступна: " + str(e))

    # 11. .env / config.json не в git
    for f in (".env", "config.json"):
        tracked = check_git_tracked(f)
        if tracked is None:
            add("WARN", "git недоступен — не смог проверить " + f)
        elif tracked:
            add("ERROR", f + " ЗАТРЕКЧЕН в git — немедленно убери "
                         "(git rm --cached) и проверь историю")
        else:
            add("OK", f + " не в git tracked")

    # 12. health endpoint (если сервер запущен)
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:%d/health" % config.PORT, timeout=3) as r:
            body = json.loads(r.read().decode("utf-8"))
        if body.get("status") == "ok":
            add("OK", "health endpoint отвечает {\"status\": \"ok\"}")
        else:
            add("WARN", "health endpoint отвечает, но без status: ok")
    except Exception:
        add("WARN", "health endpoint не отвечает (сервер не запущен?)")

    # 13. конфликтующие dev/production флаги
    if config.CFG.get("mock_llm") and config.PUBLIC_APP_URL:
        add("WARN", "PUBLIC_APP_URL задан, но mock_llm: true — "
                    "похоже на production-URL при dev-конфиге")

    print("-" * 40)
    errs = sum(1 for l, _ in RESULTS if l == "ERROR")
    warns = sum(1 for l, _ in RESULTS if l == "WARN")
    print("Итого: %d проверок, ERROR: %d, WARN: %d" %
          (len(RESULTS), errs, warns))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
