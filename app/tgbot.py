# Моника 1.0 — Фаза D1: безопасная привязка Telegram + минимальный TG-MVP.
# Один бот на инстанс (токен администратора в config.json / env, НЕ в коде).
# Привязка пользователя — одноразовый URL-safe код (в хранилище только
# sha256-хеш), команды-allowlist: /start /help /status /open /unlink.
# Только private chat. Telegram input — недоверенный: не попадает в system
# prompt, не влияет на filesystem/vault/настройки/модели. Никакого чтения
# vault, записи, shell, стикеров, проактивных сообщений в D1.
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.request

import audit
import auth
import config

TG_DIR = os.path.join(config.DATA_DIR, "telegram")
TOKENS_PATH = os.path.join(TG_DIR, "link_tokens.json")
LINKS_PATH = os.path.join(TG_DIR, "links.json")
SEEN_PATH = os.path.join(TG_DIR, "seen_updates.json")

MAX_ATTEMPTS = 5   # попыток использования кода → аннулирование
SEEN_KEEP = 1000   # сколько последних update_id помним (дедуп)
CMD_RATE = 20      # команд в минуту на telegram_user_id+chat_id
START_RATE = 10    # попыток /start с кодом на telegram_user_id (окно 10 мин)
MSG_MAX = 4096     # лимит Telegram — дублируем собственной проверкой

LOCK = threading.RLock()

# Нейтральные ответы: без деталей (никаких user id / путей / причин).
MSG_INVALID_CODE = ("Код привязки недействителен или истёк. "
                    "Создай новый код в настройках Моники.")
MSG_GROUP = "Для безопасности подключение и команды доступны только в личном чате."
MSG_CONNECTED = "Telegram подключён к Монике. Теперь можно написать /help."
MSG_CONFLICT = "Этот Telegram-аккаунт уже связан."
MSG_UNKNOWN = "Эта команда пока недоступна. Используй /help."
MSG_RATE = "Слишком много команд. Подожди немного и попробуй снова."
MSG_ALREADY = "Моника уже подключена к этому Telegram. Напиши /help."
MSG_GREET = ("Привет! Это бот Моники. Чтобы связать Telegram со своим аккаунтом, "
             "открой настройки Моники → Интеграции → Telegram и отправь мне код: "
             "/start <код>")
MSG_HELP = ("Доступные команды:\n"
            "/start — привязать Telegram к Монике\n"
            "/help — этот список\n"
            "/status — статус подключения\n"
            "/open — открыть Монику в вебе\n"
            "/unlink — как отвязать Telegram")
MSG_UNLINK = ("Отвязка выполняется через настройки Моники: "
              "Настройки → Интеграции → Telegram → «Отвязать Telegram».")

# in-memory заметки для UI (conflict и т.п.): {uid: {"code": ..., "ts": ...}}
_NOTICES = {}

_threads = {}  # совместимость старых вызовов больше не нужна; оставлен пустым


# ── Telegram API (stdlib urllib; все ошибки глушатся — сервер не падает) ──

def _api(token, method, params=None, timeout=35):
    req = urllib.request.Request(
        "https://api.telegram.org/bot" + token + "/" + method,
        data=json.dumps(params or {}).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def make_sender(token=None):
    """Транспорт отправки: send(chat_id, text). В тестах подменяется."""
    tok = token or config.TG_TOKEN

    def send(chat_id, text):
        try:
            _api(tok, "sendMessage",
                 {"chat_id": chat_id, "text": str(text)[:MSG_MAX]})
        except Exception:
            pass
    return send


# ── хранилище (атомарная запись tmp + os.replace) ──

def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def _hash(token):
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def tg_hash(tg_user_id):
    """Короткий sha256-префикс telegram_user_id для audit log."""
    return _hash("tg:" + str(tg_user_id))[:12]


def _tg_audit(uid, event, **detail):
    if uid:
        audit.log(uid, event, **detail)
    else:
        audit.log_global(event, **detail)


# ── linking tokens: одноразовые, TTL, hash-only, rate-limited ──

def create_link_token(uid, ip=""):
    """Новый одноразовый код привязки. Предыдущий активный код того же
    пользователя инвалидируется. Rate limit: на uid и на IP (audit.rate_limit).
    Возвращает (token, expires_at) или (None, None) при превышении лимита."""
    if not audit.rate_limit("tglink:" + uid, config.TG_LINK_RATE_LIMIT, 3600.0):
        _tg_audit(uid, "telegram_link_token_created", result="rate_limited")
        return None, None
    if ip and not audit.rate_limit("tglink_ip:" + ip,
                                   config.TG_LINK_RATE_LIMIT * 2, 3600.0):
        _tg_audit(uid, "telegram_link_token_created", result="rate_limited")
        return None, None
    token = secrets.token_urlsafe(24)  # 32 символа ≤ 64 (лимит start parameter)
    now = time.time()
    with LOCK:
        recs = _load(TOKENS_PATH, [])
        for r in recs:
            if (r.get("monica_user_id") == uid
                    and not r.get("used_at") and not r.get("revoked_at")):
                r["revoked_at"] = now  # новый код инвалидирует старый
        recs.append({"token_hash": _hash(token), "monica_user_id": uid,
                     "created_at": now, "expires_at": now + config.TG_LINK_TTL,
                     "used_at": None, "revoked_at": None, "attempts": 0})
        _save(TOKENS_PATH, recs[-200:])
    _tg_audit(uid, "telegram_link_token_created", result="ok")
    return token, now + config.TG_LINK_TTL


def active_token_meta(uid):
    """Метаданные активного (не использованного/не отозванного/не истёкшего)
    кода пользователя — БЕЗ самого токена (он хранится только как хеш)."""
    now = time.time()
    for r in _load(TOKENS_PATH, []):
        if (r.get("monica_user_id") == uid and not r.get("used_at")
                and not r.get("revoked_at") and r.get("expires_at", 0) > now):
            return {"expires_at": r["expires_at"]}
    return None


def revoke_active_tokens(uid):
    now = time.time()
    revoked = False
    with LOCK:
        recs = _load(TOKENS_PATH, [])
        for r in recs:
            if (r.get("monica_user_id") == uid and not r.get("used_at")
                    and not r.get("revoked_at")):
                r["revoked_at"] = now
                revoked = True
        if revoked:
            _save(TOKENS_PATH, recs)
    if revoked:
        _tg_audit(uid, "telegram_link_token_revoked", result="ok")
    return revoked


def consume_link_token(token):
    """Проверка кода из /start. Возвращает (monica_user_id | None, error_code).
    Код принимается ТОЛЬКО здесь (вызывается из обработчика Telegram /start),
    никаким произвольным API endpoint. Неудачная попытка расходует attempts;
    attempts > MAX_ATTEMPTS → код аннулируется."""
    th = _hash(token)
    now = time.time()
    with LOCK:
        recs = _load(TOKENS_PATH, [])
        rec = next((r for r in recs if r.get("token_hash") == th), None)
        if not rec:
            return None, "not_found"
        uid = rec.get("monica_user_id")
        if rec.get("used_at"):
            return None, "used"
        if rec.get("revoked_at"):
            return None, "revoked"
        if rec.get("expires_at", 0) < now:
            _tg_audit(uid, "telegram_link_token_expired", result="expired")
            return None, "expired"
        rec["attempts"] = int(rec.get("attempts") or 0) + 1
        if rec["attempts"] > MAX_ATTEMPTS:
            rec["revoked_at"] = now
            _save(TOKENS_PATH, recs)
            _tg_audit(uid, "telegram_link_attempt_failed",
                      result="annulled", error_code="attempts")
            return None, "attempts"
        _save(TOKENS_PATH, recs)
        return uid, "ok"


def mark_token_used(token):
    th = _hash(token)
    with LOCK:
        recs = _load(TOKENS_PATH, [])
        changed = False
        for r in recs:
            if r.get("token_hash") == th and not r.get("used_at"):
                r["used_at"] = time.time()
                changed = True
        if changed:
            _save(TOKENS_PATH, recs)


# ── привязки: data/telegram/links.json {monica_user_id: link} ──

def get_link_by_uid(uid):
    return _load(LINKS_PATH, {}).get(uid)


def get_uid_by_tg(tg_user_id):
    for uid, l in _load(LINKS_PATH, {}).items():
        if (str(l.get("telegram_user_id")) == str(tg_user_id)
                and l.get("status") == "active"):
            return uid
    return None


def set_link(uid, tg_user_id, chat_id, username, display_name):
    with LOCK:
        links = _load(LINKS_PATH, {})
        old = links.get(uid) or {}
        if (old.get("telegram_user_id") == str(tg_user_id)
                and old.get("link_key")):
            # повторная привязка того же TG-аккаунта — ключ привязки
            # сохраняется (библиотека стикеров остаётся доступной)
            link_key = old["link_key"]
        else:
            # новая привязка (в т.ч. ДРУГОГО TG-аккаунта) — новый ключ:
            # автоматического доступа к старой библиотеке нет (D2)
            link_key = secrets.token_hex(8)
        links[uid] = {"telegram_user_id": str(tg_user_id),
                      "telegram_chat_id": chat_id,
                      "username": username or "",
                      "display_name": display_name or "",
                      "link_key": link_key,
                      "linked_at": time.strftime("%Y-%m-%d %H:%M"),
                      "last_seen_at": time.time(),
                      "status": "active"}
        _save(LINKS_PATH, links)


def unlink(uid):
    """Отвязка: привязка удаляется, все linking tokens инвалидируются,
    бот перестаёт отвечать этому Telegram user ID. История аудита НЕ
    удаляется; личные данные не удаляются молча — доступ просто прекращается.
    Повторная привязка возможна (в т.ч. другого TG-аккаунта). Настройки
    и библиотека стикеров D2 ОСТАЮТСЯ данными пользователя, но неактивны
    (доступ к библиотеке привязан к link_key конкретной привязки)."""
    had_link = get_link_by_uid(uid) is not None
    with LOCK:
        links = _load(LINKS_PATH, {})
        if uid in links:
            links.pop(uid)
            _save(LINKS_PATH, links)
    revoke_active_tokens(uid)
    _tg_audit(uid, "telegram_unlinked", result="ok")
    if had_link:
        try:
            import tgstickers
            tgstickers.log_event(uid, "unlinked", "ok")
        except Exception:
            pass


def touch_last_seen(tg_user_id, min_interval=60.0):
    """Обновление «последней активности» для карточки Telegram (не чаще
    раза в минуту, чтобы не перезаписывать links.json на каждый update)."""
    now = time.time()
    with LOCK:
        links = _load(LINKS_PATH, {})
        for l in links.values():
            if (str(l.get("telegram_user_id")) == str(tg_user_id)
                    and l.get("status") == "active"):
                if now - (l.get("last_seen_at") or 0) >= min_interval:
                    l["last_seen_at"] = now
                    _save(LINKS_PATH, links)
                return


# ── дедуп update_id (data/telegram/seen_updates.json, последние ~1000) ──

def seen_and_mark(update_id):
    with LOCK:
        seen = _load(SEEN_PATH, [])
        if update_id in seen:
            return False
        seen.append(update_id)
        _save(SEEN_PATH, seen[-SEEN_KEEP:])
        return True


# ── заметки для UI (conflict и т.п.) ──

def set_notice(uid, code):
    if code:
        _NOTICES[uid] = {"code": code, "ts": time.time()}
    else:
        _NOTICES.pop(uid, None)


def pop_notice(uid):
    rec = _NOTICES.pop(uid, None)
    return rec["code"] if rec else None


# ── обработка update (единая точка, тестируется без сети) ──

def handle_update(update, send):
    """Обработчик одного Telegram update. send(chat_id, text) — транспорт
    (реальный sendMessage или mock в тестах). Исключения не пробрасываются."""
    try:
        return _handle(update, send)
    except Exception:
        _tg_audit(None, "telegram_link_attempt_failed",
                  result="error", error_code="handler")
        return {"ok": False}


def _handle(update, send):
    upd_id = update.get("update_id")
    if upd_id is not None and not seen_and_mark(upd_id):
        audit.log_global("telegram_update_duplicate", result="skipped")
        return {"ok": True, "duplicate": True}
    msg = update.get("message") or {}
    chat = msg.get("chat") or {}
    frm = msg.get("from") or {}
    text = str(msg.get("text") or "").strip()[:MSG_MAX]
    # Фаза D2: стикеры обрабатываются наравне с текстом (private-only,
    # привязанный пользователь, не пересланные — проверки в tgstickers)
    has_sticker = isinstance(msg.get("sticker"), dict)
    if not text and not has_sticker:
        return {"ok": True}
    if chat.get("type") != "private":
        # в группе — один короткий отказ, никаких команд и привязок
        send(chat.get("id"), MSG_GROUP)
        return {"ok": True, "group": True}
    tg_uid = str(frm.get("id") or "")
    chat_id = chat.get("id")
    if not tg_uid or chat_id is None:
        return {"ok": True}
    touch_last_seen(tg_uid)
    if not audit.rate_limit("tgcmd:%s:%s" % (tg_uid, chat_id), CMD_RATE, 60.0):
        _tg_audit(get_uid_by_tg(tg_uid), "telegram_command_rate_limited",
                  result="limited", tg_user_hash=tg_hash(tg_uid))
        send(chat_id, MSG_RATE)
        return {"ok": True, "rate_limited": True}
    # Фаза D2: память стикеров — до командной ветки (у стикера нет текста)
    if has_sticker:
        try:
            import tgstickers
            if tgstickers.handle_incoming_sticker_message(msg, send):
                return {"ok": True, "sticker": True}
        except Exception:
            _tg_audit(get_uid_by_tg(tg_uid), "telegram_sticker_rejected",
                      result="error", error_code="handler")
        return {"ok": True}
    cmd, _, arg = text.partition(" ")
    cmd = cmd.split("@", 1)[0].lower()  # /cmd@botname → /cmd
    arg = arg.strip()[:80]
    if cmd == "/start":
        return _cmd_start(tg_uid, chat_id, frm, arg, send)
    if cmd == "/help":
        _tg_audit(get_uid_by_tg(tg_uid), "telegram_command_received",
                  result="help", tg_user_hash=tg_hash(tg_uid))
        send(chat_id, MSG_HELP)
        return {"ok": True}
    if cmd == "/status":
        _tg_audit(get_uid_by_tg(tg_uid), "telegram_command_received",
                  result="status", tg_user_hash=tg_hash(tg_uid))
        send(chat_id, "Подключено" if get_uid_by_tg(tg_uid) else "Не подключено")
        return {"ok": True}
    if cmd == "/open":
        _tg_audit(get_uid_by_tg(tg_uid), "telegram_command_received",
                  result="open", tg_user_hash=tg_hash(tg_uid))
        send(chat_id, config.PUBLIC_APP_URL if config.PUBLIC_APP_URL
             else "Веб-ссылка пока не настроена.")
        return {"ok": True}
    if cmd == "/unlink":
        _tg_audit(get_uid_by_tg(tg_uid), "telegram_command_received",
                  result="unlink", tg_user_hash=tg_hash(tg_uid))
        # сам НЕ отвязывает — только через веб с confirm
        send(chat_id, MSG_UNLINK)
        return {"ok": True}
    _tg_audit(get_uid_by_tg(tg_uid), "telegram_command_received",
              result="unknown", tg_user_hash=tg_hash(tg_uid))
    send(chat_id, MSG_UNKNOWN)
    return {"ok": True}


def _cmd_start(tg_uid, chat_id, frm, arg, send):
    if arg:
        # rate limit попыток /start с кодом на telegram_user_id
        if not audit.rate_limit("tgstart:" + tg_uid, START_RATE, 600.0):
            send(chat_id, MSG_INVALID_CODE)
            return {"ok": True}
        uid, err = consume_link_token(arg)
        if not uid:
            _tg_audit(get_uid_by_tg(tg_uid), "telegram_link_attempt_failed",
                      result="failed", error_code=err, tg_user_hash=tg_hash(tg_uid))
            send(chat_id, MSG_INVALID_CODE)
            return {"ok": True, "linked": False}
        with LOCK:
            owner = get_uid_by_tg(tg_uid)
            if owner and owner != uid:
                # Telegram user уже привязан к ДРУГОМУ аккаунту — нейтрально,
                # НЕ перепривязываем (transfer flow не делаем)
                mark_token_used(arg)
                _tg_audit(uid, "telegram_link_conflict",
                          result="conflict", tg_user_hash=tg_hash(tg_uid))
                set_notice(uid, "conflict")
                send(chat_id, MSG_CONFLICT)
                return {"ok": True, "conflict": True}
            set_link(uid, tg_uid, chat_id, frm.get("username"),
                     frm.get("first_name"))
        mark_token_used(arg)
        set_notice(uid, None)
        _tg_audit(uid, "telegram_linked", result="ok",
                  tg_user_hash=tg_hash(tg_uid))
        try:
            import tgstickers
            tgstickers.log_event(uid, "linked", "ok")
        except Exception:
            pass
        send(chat_id, MSG_CONNECTED)
        return {"ok": True, "linked": True}
    # /start без кода — привязка или приветствие
    if get_uid_by_tg(tg_uid):
        send(chat_id, MSG_ALREADY)
    else:
        send(chat_id, MSG_GREET)
    return {"ok": True}


# ── транспорт: dev polling (явный dev-флаг) / webhook (маршрут в server.py) ──

_poller_started = False


def start_all():
    """Вызывается при старте сервера. Polling — ТОЛЬКО при явном
    telegram_dev_polling: true в конфиге и наличии токена; иначе модуль
    просто выключен (webhook поднимается маршрутом /api/telegram/webhook/<secret>)."""
    global _poller_started
    if _poller_started or not config.TG_TOKEN or not config.TG_DEV_POLLING:
        return
    _poller_started = True
    threading.Thread(target=_poll_loop, daemon=True).start()


def _poll_loop():
    # меню команд Bot API — только allowlist из 5 команд (best-effort)
    try:
        _api(config.TG_TOKEN, "setMyCommands", {"commands": [
            {"command": "start", "description": "Привязать Telegram к Монике"},
            {"command": "help", "description": "Список команд"},
            {"command": "status", "description": "Статус подключения"},
            {"command": "open", "description": "Открыть Монику в вебе"},
            {"command": "unlink", "description": "Как отвязать Telegram"}]})
    except Exception:
        pass
    offset = 0
    send = make_sender()
    while True:
        try:
            data = _api(config.TG_TOKEN, "getUpdates",
                        {"offset": offset, "timeout": 25})
            for upd in data.get("result", []):
                offset = upd.get("update_id", offset - 1) + 1
                handle_update(upd, send)
        except Exception:
            time.sleep(20)
