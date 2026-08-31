# Моника 1.0 — Фаза A: дневной лимит токенов.
# Хранение: data/users/<uid>/budget.json
#   {date: "YYYY-MM-DD", limit: 200000,
#    used: {light: N, smart: N, total: N}, reserved: N}
# Атомарность: lock-файл budget.lock (O_CREAT|O_EXCL, retry ~2с) +
# перезапись JSON через tmp + os.replace (паттерн auth.py).
# Сброс: при любом чтении если date != сегодня — used обнуляется.
import datetime
import json
import os
import time

import auth

DEFAULT_LIMIT = 200000   # утверждено автором
LOCK_TIMEOUT = 2.0       # сек ожидания lock-файла
STALE_LOCK = 10.0        # зависший lock старше — ломаем


def _today():
    return time.strftime("%Y-%m-%d")


def _path(uid):
    return os.path.join(auth.user_dir(uid), "budget.json")


def _lock_path(uid):
    return os.path.join(auth.user_dir(uid), "budget.lock")


def _save(uid, data):
    tmp = _path(uid) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, _path(uid))


def _load(uid):
    """Чтение с гарантированным сбросом по дате. Вызывать под lock для мутаций."""
    data = None
    if os.path.exists(_path(uid)):
        try:
            with open(_path(uid), encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = None
    if not isinstance(data, dict):
        data = {}
    data.setdefault("date", _today())
    data.setdefault("limit", DEFAULT_LIMIT)
    data.setdefault("used", {})
    data.setdefault("reserved", 0)
    if data.get("date") != _today():
        data["date"] = _today()
        data["used"] = {}
        data["reserved"] = 0
        try:
            _save(uid, data)
        except OSError:
            pass
    return data


class _Lock:
    """lock-файл: os.open O_CREAT|O_EXCL, retry с таймаутом ~2с."""

    def __init__(self, uid):
        self.uid = uid
        self.fd = None

    def __enter__(self):
        deadline = time.time() + LOCK_TIMEOUT
        while True:
            try:
                self.fd = os.open(_lock_path(self.uid),
                                  os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except FileExistsError:
                try:
                    age = time.time() - os.path.getmtime(_lock_path(self.uid))
                except OSError:
                    age = 0
                if age > STALE_LOCK:  # зависший процесс — ломаем lock
                    try:
                        os.remove(_lock_path(self.uid))
                    except OSError:
                        pass
                    continue
                if time.time() >= deadline:
                    raise TimeoutError("budget lock timeout")
                time.sleep(0.02)

    def __exit__(self, *exc):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            try:
                os.remove(_lock_path(self.uid))
            except OSError:
                pass
        return False


def reserve(uid, est_tokens, kind="light"):
    """Атомарно зарезервировать est токенов. False — лимит исчерпан."""
    est = max(0, int(est_tokens or 0))
    with _Lock(uid):
        d = _load(uid)
        limit = int(d.get("limit") or 0)
        used_total = int(d["used"].get("total", 0))
        reserved = int(d.get("reserved", 0))
        if limit > 0 and used_total + reserved + est > limit:
            return False
        d["reserved"] = reserved + est
        _save(uid, d)
    return True


def commit(uid, actual_tokens, kind="light", est=0):
    """Списать фактические токены (и снять резерв est, если передан)."""
    n = max(0, int(actual_tokens or 0))
    with _Lock(uid):
        d = _load(uid)
        used = d["used"]
        used[kind] = int(used.get(kind, 0)) + n
        used["total"] = int(used.get("total", 0)) + n
        d["reserved"] = max(0, int(d.get("reserved", 0)) - max(0, int(est or 0)))
        _save(uid, d)


def release(uid, est_tokens):
    """Снять резерв (например, при ошибке запроса к LLM)."""
    with _Lock(uid):
        d = _load(uid)
        d["reserved"] = max(0, int(d.get("reserved", 0)) - max(0, int(est_tokens or 0)))
        _save(uid, d)


def set_limit(uid, limit):
    with _Lock(uid):
        d = _load(uid)
        d["limit"] = int(limit)
        _save(uid, d)


def status(uid):
    """{limit, used_total, remaining, reset_at, by_model, reserved}."""
    d = _load(uid)
    limit = int(d.get("limit") or 0)
    used = d.get("used") or {}
    used_total = int(used.get("total", 0))
    remaining = max(0, limit - used_total) if limit > 0 else None
    now = datetime.datetime.now()
    reset_at = (datetime.datetime(now.year, now.month, now.day)
                + datetime.timedelta(days=1)).strftime("%Y-%m-%dT00:00:00")
    return {"limit": limit,
            "used_total": used_total,
            "remaining": remaining,
            "reset_at": reset_at,
            "by_model": {"light": int(used.get("light", 0)),
                         "smart": int(used.get("smart", 0))},
            "reserved": int(d.get("reserved", 0))}
