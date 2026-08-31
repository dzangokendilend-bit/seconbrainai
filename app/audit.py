# Моника 1.0 — Фаза A: append-only аудит + rate limits.
# data/users/<uid>/audit.jsonl — строки {ts, event, detail}.
# Маскирование: никаких ключей/паролей/токенов в detail — только имена
# сервисов, длины, префиксы, статусы. Аудит никогда не ломает основной
# запрос (все ошибки глушатся).
import json
import os
import threading
import time

import auth

# ключи detail, безопасные для записи в журнал
_SAFE_KEYS = {"service", "ok", "status", "path", "limit", "kind",
              "username", "error", "count", "prefix", "length",
              "skipped", "strategy"}

_MAX_LINE = 4000  # jsonl-строки <4KB — достаточно для простого append


def _path(uid):
    return os.path.join(auth.user_dir(uid), "audit.jsonl")


def _mask(detail):
    """Оставляем только безопасные ключи; всё остальное — только длина."""
    out = {}
    for k, v in (detail or {}).items():
        if k in _SAFE_KEYS:
            s = str(v)[:120]
            out[k] = s
        else:
            # неизвестный ключ — маскируем в длину (никаких значений)
            out[str(k)[:40] + "_len"] = len(str(v))
    return out


def log(uid, event, **detail):
    """Append одной jsonl-строки. Ни при каких условиях не бросает."""
    try:
        if not uid:
            return
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "event": str(event)[:40],
               "detail": _mask(detail)}
        line = json.dumps(rec, ensure_ascii=False)
        if len(line) > _MAX_LINE:
            line = line[:_MAX_LINE]
        os.makedirs(auth.user_dir(uid), exist_ok=True)
        with open(_path(uid), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def recent(uid, n=100):
    """Последние n записей (для будущего UI аудита)."""
    try:
        p = _path(uid)
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        out = []
        for line in lines[-n:]:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out
    except Exception:
        return []


# ── Rate limits (Фаза A, риски 2–3 из threat model) ──
# In-memory: {key: [timestamps]}; окно 60с, чистка при каждом обращении.
_HITS = {}
_HITS_LOCK = threading.Lock()


def rate_limit(key, limit, window=60.0):
    """True — разрешено; False — превышение (маршрут ответит 429)."""
    now = time.time()
    cutoff = now - window
    with _HITS_LOCK:
        arr = _HITS.setdefault(str(key), [])
        while arr and arr[0] < cutoff:
            arr.pop(0)
        if len(arr) >= limit:
            return False
        arr.append(now)
        # лёгкая чистка пустых ключей, чтобы dict не рос вечно
        if len(_HITS) > 1024:
            for k in [k for k, v in _HITS.items() if not v]:
                _HITS.pop(k, None)
        return True
