# AI1: диагностический лог ИИ-вызовов. Включается только MONICA_AI_DEBUG=true.
# Пишет в data/audit/ai_debug.jsonl. НИКОГДА не пишет: ключи, Authorization,
# полный prompt, содержимое заметок/чата, request/response body, TG-сообщения,
# cookies, session tokens. Только whitelisted-поля.
import json
import os
import time

import config

# whitelist полей (всё остальное молча отбрасывается)
_ALLOWED = ("ts", "provider", "model", "endpoint", "http_status",
            "latency_ms", "request_id", "usage", "error_code")


def _path():
    return os.path.join(config.DATA_DIR, "audit", "ai_debug.jsonl")


def enabled():
    return str(config.env("MONICA_AI_DEBUG") or "").lower() in ("1", "true", "yes")


def log_event(**fields):
    """Безопасная запись события вызова провайдера. Без секретов."""
    if not enabled():
        return
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    for k in _ALLOWED:
        if k in fields and fields[k] is not None:
            rec[k] = fields[k]
    try:
        os.makedirs(os.path.dirname(_path()), exist_ok=True)
        with open(_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass  # лог не должен ломать основной поток
