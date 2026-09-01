# Моника 1.0 — Фаза D2: Telegram Control Center + Sticker Memory.
# Server-side настройки привязки (data/telegram/link_settings.json),
# память стикеров (data/telegram/stickers.json, дедуп по file_unique_id),
# история интеграционных событий (data/telegram/integration_events.json,
# только техметаданные — БЕЗ текстов сообщений/токенов/file_id).
#
# Идеи каталога стикеров перенесены из Сибериады (vajga/second-brain/tools/
# chat_server.py: stickers.json {type, file_id, desc, added}, дедуп по id,
# «помнить-и-описывать»), но адаптированы под модель Моники: per-user/per-link
# scope, дедуп по file_unique_id, лимиты 300/30ч, cooldown ответов,
# никакого LLM и никакого автоподбора в D2 (sticker_reply_enabled — только
# ручной preview/тестовая отправка).
#
# Безопасность: file_id/токены/тексты не попадают в events и audit;
# доступ — только по веб-сессии своего monica_user_id; test-send —
# единственная исходящая отправка в D2, только в private chat привязки.
import json
import os
import secrets
import threading
import time

import audit
import config
import tgbot

TG_DIR = os.path.join(config.DATA_DIR, "telegram")
SETTINGS_PATH = os.path.join(TG_DIR, "link_settings.json")
STICKERS_PATH = os.path.join(TG_DIR, "stickers.json")
EVENTS_PATH = os.path.join(TG_DIR, "integration_events.json")

# лимиты (спецификация D2)
MAX_STICKERS_PER_LINK = 300   # стикеров на одну привязку
NEW_PER_HOUR = 30             # новых стикеров в час на привязку
TEST_SEND_PER_HOUR = 10       # тестовых отправок в час на пользователя
EVENTS_KEEP = 100             # последних событий на пользователя
OFF_REPLY_COOLDOWN = 3600.0   # сек между ответами «функция выключена»

TEXT_MAX = 300   # смысл/тон/контексты
NAME_MAX = 60    # название
WEIGHT_MIN, WEIGHT_MAX = 0.0, 1.0

LOCK = threading.RLock()

# cooldown «функция выключена»: {link_key: last_ts}
_off_reply_ts = {}

DEFAULT_SETTINGS = {
    "link_id": None,
    "remember_stickers_enabled": False,
    "sticker_reply_enabled": False,
    "integration_event_logging_enabled": False,
    "updated_at": None,
}

TOGGLES = ("remember_stickers_enabled", "sticker_reply_enabled",
           "integration_event_logging_enabled")

EVENT_TYPES = {
    "linked": "Telegram подключён",
    "unlinked": "Telegram отвязан",
    "settings_changed": "Настройки интеграции изменены",
    "sticker_stored": "Стикер запомнен",
    "sticker_duplicate": "Стикер уже был в памяти",
    "sticker_updated": "Описание стикера изменено",
    "sticker_enabled": "Стикер включён",
    "sticker_disabled": "Стикер выключен",
    "sticker_deleted": "Стикер удалён",
    "sticker_rejected": "Стикер не сохранён",
    "command_received": "Команда получена",
    "command_rejected": "Команда отклонена",
    "rate_limited": "Слишком много запросов",
    "api_error": "Ошибка Telegram API",
    "test_send_requested": "Тестовая отправка запрошена",
    "test_sent": "Тестовая отправка выполнена",
    "test_failed": "Тестовая отправка не удалась",
}

# фильтры UI → event types
EVENT_FILTERS = {
    "stickers": {"sticker_stored", "sticker_duplicate", "sticker_updated",
                 "sticker_enabled", "sticker_disabled", "sticker_deleted",
                 "sticker_rejected", "test_send_requested", "test_sent",
                 "test_failed"},
    "link": {"linked", "unlinked", "settings_changed"},
    "commands": {"command_received", "command_rejected"},
    "errors": {"rate_limited", "api_error", "test_failed"},
}


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else default
    except Exception:
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


# ── link_key: уникальный ключ ПРИВЯЗКИ (изоляция повторных привязок) ──
# tgbot.set_link генерирует link_key и хранит в links.json: повторная
# привязка ДРУГОГО TG-аккаунта → новый ключ; старая библиотека остаётся
# данными пользователя, но автоматического доступа к ней нет.

def link_key_for_uid(uid):
    return (tgbot.get_link_by_uid(uid) or {}).get("link_key")


# ── settings (per monica_user_id, применяются сервером немедленно) ──

def get_settings(uid):
    with LOCK:
        rec = dict(DEFAULT_SETTINGS)
        rec.update(_load(SETTINGS_PATH, {}).get(uid) or {})
        return rec


def set_settings(uid, changes):
    """Сохранение toggles (только известные ключи, только bool)."""
    now = time.time()
    with LOCK:
        s = _load(SETTINGS_PATH, {})
        rec = dict(DEFAULT_SETTINGS)
        rec.update(s.get(uid) or {})
        rec["link_id"] = link_key_for_uid(uid) or rec.get("link_id")
        for k in TOGGLES:
            if k in changes:
                rec[k] = bool(changes[k])
        rec["updated_at"] = now
        s[uid] = rec
        _save(SETTINGS_PATH, s)
    return dict(rec)


def apply_settings_change(uid, changes):
    """set_settings + audit + событие истории. Входящие update читают
    settings при каждом update — применение немедленное, без рестарта."""
    rec = set_settings(uid, changes)
    changed = [k for k in TOGGLES if k in changes]
    for k in changed:
        audit.log(uid, "telegram_settings_changed", result="ok",
                  toggle=k, enabled=bool(rec.get(k)))
    log_event(uid, "settings_changed", "ok",
              {k: bool(rec.get(k)) for k in TOGGLES})
    return rec


# ── integration events (per user, последние ~100, safe metadata) ──

def log_event(uid, event_type, result, safe_metadata=None):
    """Добавляет событие в журнал. Журнал ЦЕЛИКОМ управляется toggle
    integration_event_logging_enabled (по умолчанию ВЫКЛ — ничего не
    пишется); security-журнал audit.jsonl ведётся всегда независимо.
    Метаданные — только технические (типы/статусы/короткие id), без
    текстов сообщений, update JSON, токенов и file_id."""
    try:
        if not get_settings(uid).get("integration_event_logging_enabled"):
            return
        meta = {}
        for k, v in (safe_metadata or {}).items():
            if isinstance(v, (bool, int, float)):
                meta[str(k)[:40]] = v
            elif isinstance(v, str):
                meta[str(k)[:40]] = v[:120]
        rec = {"event_id": secrets.token_hex(8),
               "monica_user_id": uid,
               "telegram_link_id": link_key_for_uid(uid),
               "event_type": str(event_type)[:40],
               "timestamp": time.time(),
               "result": str(result)[:40],
               "safe_metadata": meta}
        with LOCK:
            ev = _load(EVENTS_PATH, {})
            arr = ev.get(uid) or []
            arr.append(rec)
            ev[uid] = arr[-EVENTS_KEEP:]
            _save(EVENTS_PATH, ev)
    except Exception:
        pass


def get_events(uid, filt=None, limit=100):
    """Безопасная выдача истории (новые сверху). Тексты/токены/file_id
    сюда не пишутся по построению — выдача не может их утечь."""
    with LOCK:
        arr = list(reversed(_load(EVENTS_PATH, {}).get(uid) or []))
    allowed = EVENT_FILTERS.get(filt)
    out = []
    for e in arr:
        if allowed and e.get("event_type") not in allowed:
            continue
        out.append({"event_id": e.get("event_id"),
                    "event_type": e.get("event_type"),
                    "event_label": EVENT_TYPES.get(e.get("event_type"), "Событие"),
                    "timestamp": e.get("timestamp"),
                    "result": e.get("result"),
                    "safe_metadata": e.get("safe_metadata") or {}})
        if len(out) >= max(1, min(int(limit or 100), EVENTS_KEEP)):
            break
    return out


# ── sticker memory (per link_key) ──

def remember_sticker(uid, link_key, sticker_obj):
    """Сохранение входящего стикера (уже прошедшего проверки private/linked/
    not-forwarded в handle_incoming_sticker_message). Server-side toggle
    remember_stickers_enabled проверяется ЗДЕСЬ — немедленное применение к
    входящим update без рестарта. Дедуп по telegram_file_unique_id —
    стабильный идентификатор файла в Telegram.
    Возвращает (action, rec|None): stored/duplicate/limit/rate_limited/
    disabled."""
    if not get_settings(uid).get("remember_stickers_enabled"):
        audit.log(uid, "telegram_sticker_rejected",
                  result="rejected", error_code="toggle_off")
        return "disabled", None
    fuid = str((sticker_obj or {}).get("file_unique_id") or "")
    if not fuid:
        audit.log(uid, "telegram_sticker_rejected",
                  result="rejected", error_code="no_unique_id")
        return "rejected", None
    now = time.time()
    with LOCK:
        data = _load(STICKERS_PATH, {})
        items = data.get(link_key) or []
        rec = next((x for x in items
                    if x.get("telegram_file_unique_id") == fuid), None)
        if rec:
            rec["updated_at"] = now
            data[link_key] = items
            _save(STICKERS_PATH, data)
            audit.log(uid, "telegram_sticker_deduplicated", result="ok")
            return "duplicate", dict(rec)
        if sum(1 for x in items if (x.get("created_at") or 0) > now - 3600) >= NEW_PER_HOUR:
            audit.log(uid, "telegram_sticker_rate_limited",
                      result="limited", error_code="new_per_hour")
            return "rate_limited", None
        if len(items) >= MAX_STICKERS_PER_LINK:
            audit.log(uid, "telegram_sticker_rejected",
                      result="rejected", error_code="max_total")
            return "limit", None
        stype = sticker_obj.get("type") or "static"
        if stype not in ("static", "animated", "video"):
            stype = "static"
        rec = {"sticker_id": secrets.token_hex(8),
               "telegram_file_id": str(sticker_obj.get("file_id") or "")[:200],
               "telegram_file_unique_id": fuid[:200],
               "type": stype,
               "emoji": str(sticker_obj.get("emoji") or "")[:16],
               "set_name": str(sticker_obj.get("set_name") or "")[:80],
               "width": int(sticker_obj.get("width") or 0),
               "height": int(sticker_obj.get("height") or 0),
               "file_size": int(sticker_obj.get("file_size") or 0),
               "created_at": now,
               "updated_at": now,
               "enabled": True,
               "name": "",
               "meaning": "",
               "tone": "",
               "allowed_contexts": "",
               "blocked_contexts": "",
               "usage_weight": 0.5,
               "last_used_at": None,
               "usage_count": 0}
        items.append(rec)
        data[link_key] = items
        _save(STICKERS_PATH, data)
    audit.log(uid, "telegram_sticker_received", result="stored", kind=stype)
    log_event(uid, "sticker_stored", "ok", {"type": stype})
    return "stored", dict(rec)


def sticker_reply_allowed(uid):
    """Cooldown для ответа «функция выключена» — не спамить в Telegram."""
    key = link_key_for_uid(uid) or "unknown"
    now = time.time()
    with LOCK:
        if now - _off_reply_ts.get(key, 0) < OFF_REPLY_COOLDOWN:
            return False
        _off_reply_ts[key] = now
    return True


# ── metadata API (браузер, строго свой scope) ──

def sticker_public(rec, with_file_id=False):
    """Безопасный dict для браузера. file_id/file_unique_id НЕ отдаются —
    preview идёт через серверный прокси /api/tg/stickers/<id>/preview."""
    out = {"sticker_id": rec.get("sticker_id"),
           "type": rec.get("type"),
           "emoji": rec.get("emoji"),
           "set_name": rec.get("set_name"),
           "width": rec.get("width"),
           "height": rec.get("height"),
           "file_size": rec.get("file_size"),
           "created_at": rec.get("created_at"),
           "updated_at": rec.get("updated_at"),
           "enabled": bool(rec.get("enabled")),
           "name": rec.get("name") or "",
           "meaning": rec.get("meaning") or "",
           "tone": rec.get("tone") or "",
           "allowed_contexts": rec.get("allowed_contexts") or "",
           "blocked_contexts": rec.get("blocked_contexts") or "",
           "usage_weight": rec.get("usage_weight"),
           "last_used_at": rec.get("last_used_at"),
           "usage_count": rec.get("usage_count")}
    if with_file_id:
        out["telegram_file_id"] = rec.get("telegram_file_id")
    return out


def _items_of(link_key):
    return _load(STICKERS_PATH, {}).get(link_key) or []


def list_stickers(uid, link_key):
    with LOCK:
        return [sticker_public(r) for r in _items_of(link_key)]


def get_sticker(uid, link_key, sticker_id, with_file_id=False):
    with LOCK:
        rec = next((r for r in _items_of(link_key)
                    if r.get("sticker_id") == sticker_id), None)
        return sticker_public(rec, with_file_id) if rec else None


def update_sticker(uid, link_key, sticker_id, fields):
    """Обновление метаданных. Валидация: название ≤60, остальные ≤300,
    вес — число 0..1. Возвращает (rec|None, error_code|None)."""
    now = time.time()
    with LOCK:
        data = _load(STICKERS_PATH, {})
        items = data.get(link_key) or []
        rec = next((r for r in items
                    if r.get("sticker_id") == sticker_id), None)
        if not rec:
            return None, "not_found"
        upd = {}
        for k, maxlen in (("name", NAME_MAX), ("meaning", TEXT_MAX),
                          ("tone", TEXT_MAX),
                          ("allowed_contexts", TEXT_MAX),
                          ("blocked_contexts", TEXT_MAX)):
            if k in fields:
                v = str(fields.get(k) or "").strip()
                if len(v) > maxlen:
                    return None, "too_long"
                upd[k] = v
        if "usage_weight" in fields:
            try:
                w = float(fields.get("usage_weight"))
            except (TypeError, ValueError):
                return None, "bad_weight"
            if not (WEIGHT_MIN <= w <= WEIGHT_MAX):
                return None, "bad_weight"
            upd["usage_weight"] = round(w, 2)
        if "enabled" in fields:
            upd["enabled"] = bool(fields.get("enabled"))
        if not upd:
            return dict(rec), None
        rec.update(upd)
        rec["updated_at"] = now
        data[link_key] = items
        _save(STICKERS_PATH, data)
    if upd.get("enabled") is True:
        audit.log(uid, "telegram_sticker_enabled", result="ok")
        log_event(uid, "sticker_enabled", "ok")
    elif upd.get("enabled") is False:
        audit.log(uid, "telegram_sticker_disabled", result="ok")
        log_event(uid, "sticker_disabled", "ok")
    if set(upd) - {"enabled"}:
        audit.log(uid, "telegram_sticker_metadata_updated", result="ok")
        log_event(uid, "sticker_updated", "ok")
    return dict(rec), None


def toggle_sticker(uid, link_key, sticker_id, enabled):
    return update_sticker(uid, link_key, sticker_id, {"enabled": bool(enabled)})


def delete_sticker(uid, link_key, sticker_id):
    """Удаление метаданных Моники (не из Telegram pack). file_id в audit
    не пишется; после удаления тестовая отправка невозможна."""
    with LOCK:
        data = _load(STICKERS_PATH, {})
        items = data.get(link_key) or []
        rec = next((r for r in items
                    if r.get("sticker_id") == sticker_id), None)
        if not rec:
            return False
        items.remove(rec)
        data[link_key] = items
        _save(STICKERS_PATH, data)
    audit.log(uid, "telegram_sticker_deleted", result="ok")
    log_event(uid, "sticker_deleted", "ok")
    return True


# ── test send (ЕДИНСТВЕННАЯ исходящая отправка в D2) ──

def _tg_send_sticker(chat_id, file_id, stype):
    """Транспорт тестовой отправки; в тестах подменяется. Никогда не бросает."""
    method = ("sendAnimation" if stype in ("animated", "video")
              else "sendSticker")
    tgbot._api(config.TG_TOKEN, method,
               {"chat_id": chat_id, "sticker": file_id})


def test_send(uid, sticker_id):
    """Отправка сохранённого стикера в private chat ТЕКУЩЕЙ привязки.
    Активная привязка + enabled стикер + rate limit 10/час; при ошибке
    Telegram API — безопасный код ошибки без token/response body."""
    link = tgbot.get_link_by_uid(uid)
    link_key = (link or {}).get("link_key")
    if not link or not link_key or link.get("status") != "active":
        return False, "not_linked"
    rec = get_sticker(uid, link_key, sticker_id, with_file_id=True)
    if not rec:
        return False, "not_found"
    if not rec.get("enabled"):
        return False, "disabled"
    # rate limit — только на фактическую отправку (не на scope-проверки)
    if not audit.rate_limit("tgtst:" + uid, TEST_SEND_PER_HOUR, 3600.0):
        audit.log(uid, "telegram_sticker_test_requested",
                  result="rate_limited", error_code="per_hour")
        log_event(uid, "rate_limited", "limited", {"kind": "test_send"})
        return False, "rate_limited"
    audit.log(uid, "telegram_sticker_test_requested", result="ok")
    log_event(uid, "test_send_requested", "ok")
    try:
        _tg_send_sticker(link.get("telegram_chat_id"),
                         rec["telegram_file_id"], rec.get("type"))
    except Exception:
        audit.log(uid, "telegram_sticker_test_failed", result="error",
                  error_code="api")
        log_event(uid, "test_failed", "error")
        return False, "api_error"
    with LOCK:
        data = _load(STICKERS_PATH, {})
        items = data.get(link_key) or []
        r = next((x for x in items
                  if x.get("sticker_id") == sticker_id), None)
        if r:
            r["last_used_at"] = time.time()
            r["usage_count"] = int(r.get("usage_count") or 0) + 1
            data[link_key] = items
            _save(STICKERS_PATH, data)
    audit.log(uid, "telegram_sticker_test_sent", result="ok")
    log_event(uid, "test_sent", "ok")
    return True, "ok"


# ── мост из tgbot: обработка входящего стикера ──

MSG_STICKER_UNLINKED = ("Сначала подключи Telegram к Монике через "
                        "Настройки → Интеграции.")
MSG_STICKER_SAVED = ("Запомнила стикер. Его можно описать и настроить "
                     "в Монике: Настройки → Интеграции → Telegram → "
                     "Память стикеров.")
MSG_STICKER_OFF = ("Память стикеров сейчас выключена. Включи её в Монике: "
                   "Настройки → Интеграции → Telegram.")
MSG_STICKER_LIMIT = ("Память стикеров заполнена (максимум 300). "
                     "Освободи место в Монике: Настройки → Интеграции → "
                     "Telegram.")
MSG_STICKER_RATE = "Слишком много новых стикеров за час. Подожди немного."


def handle_incoming_sticker_message(msg, send):
    """Вызывается из tgbot._handle для private-сообщений со стикером.
    Правила D2: только private chat, только от привязанного пользователя,
    не пересланный. Возвращает True — update обработан как стикер."""
    st = msg.get("sticker")
    if not isinstance(st, dict):
        return False
    chat = msg.get("chat") or {}
    frm = msg.get("from") or {}
    tg_uid = str(frm.get("id") or "")
    chat_id = chat.get("id")
    uid = tgbot.get_uid_by_tg(tg_uid) if tg_uid else None
    # пересланный стикер не запоминаем (источник — не сам пользователь)
    if (msg.get("forward_origin") or msg.get("forward_from")
            or msg.get("forward_sender_name") or msg.get("forward_date")):
        if uid:
            audit.log(uid, "telegram_sticker_rejected",
                      result="rejected", error_code="forwarded")
        return True
    if not uid:
        send(chat_id, MSG_STICKER_UNLINKED)
        return True
    stype = ("video" if st.get("is_video")
             else "animated" if st.get("is_animated") else "static")
    action, _rec = remember_sticker(uid, link_key_for_uid(uid), {
        "file_id": st.get("file_id"),
        "file_unique_id": st.get("file_unique_id"),
        "type": stype,
        "emoji": st.get("emoji"),
        "set_name": st.get("set_name"),
        "width": st.get("width"),
        "height": st.get("height"),
        "file_size": st.get("file_size")})
    if action == "stored":
        send(chat_id, MSG_STICKER_SAVED)
    elif action == "disabled":
        if sticker_reply_allowed(uid):
            send(chat_id, MSG_STICKER_OFF)
    elif action == "limit":
        send(chat_id, MSG_STICKER_LIMIT)
    elif action == "rate_limited":
        send(chat_id, MSG_STICKER_RATE)
    return True
