# Моника 1.0 — точка входа. Фаза 1: пользователи и онбординг.
import base64
import io
import json
import os
import re
import sys
import time
import urllib.parse
import zipfile
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit
import auth
import budget
import config
import history as hist
import keys as keys_mod
import media
import onboarding
import providers
import terminal as term
import modules as mon_mods
import tgbot

COOKIE = "monica_session"
# Фаза 5-B: карта модель -> сервис генерируется из единого реестра onboarding.MODELS
MODEL_SERVICE = {m["id"]: m["service"] for m in onboarding.MODELS}


def resolve_model(uid, kind="light"):
    """6-M2: chat_kind из prefs решает, какая пара работает в чате.
    kind: light (повседневный чат) | smart (терминал/хранилище/pro)."""
    p = auth.load_profile(uid)
    prefs = (p.get("onboarding", {}).get("prefs") or {})
    if kind == "light" and prefs.get("chat_kind") == "smart":
        kind = "smart"
    cust = prefs.get(kind) or {}
    if isinstance(cust, dict) and str(cust.get("api_model") or "").strip():
        svc = cust.get("provider") if cust.get("provider") in onboarding.KEY_SERVICES else "smart"
        return svc, str(cust["api_model"]).strip()
    model = onboarding.normalize_model(prefs.get("model"))
    return (onboarding.service_for(model) or "luna", onboarding.api_model(model) or model)


def build_user_content(uid, text, files):
    """6-M: маршрутизация медиа-вложений. Возвращает (content, media_notes).
    content — строка или массив частей (vision) для сообщения user."""
    groq_key = keys_mod.load_keys(config.MACHINE_SECRET, uid).get("groq")
    vision, addon, saved, errors = media.analyze_files(uid, files, groq_key)
    notes = []
    if saved:
        notes.append("Сохранено в attachments: " + ", ".join(saved))
    if errors:
        notes.append("⚠️ " + "; ".join(errors))
    tail = ("\n\n" + addon if addon else "") + ("\n\n" + "\n".join(notes) if notes else "")
    if vision:
        content = [{"type": "text", "text": (text or "Опиши вложения.") + tail}] + vision
    else:
        content = text + tail
    return content, "\n".join(notes)


CHAT_SYSTEM = ("Ты — Моника, личный ИИ-ассистент пользователя внутри веб-сервиса Моника. "
               "Дружелюбно, просто, без воды. Помогаешь с заметками, модулями и вопросами. "
               "Если нужен ключ или модуль не включён — подскажи зайти в настройки. "
               "Работаешь только с данными этого пользователя.")
MAX_BODY = 24 * 1024 * 1024  # 6-M: медиа-вложения (5 файлов ≤10МБ → base64)


class Handler(BaseHTTPRequestHandler):
    server_version = "Monica/1.0"

    def log_message(self, fmt, *args):
        pass

    # ── служебное ──

    def _json(self, obj, status=200, set_cookie=None, clear_cookie=False):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if set_cookie:
            self.send_header("Set-Cookie",
                             COOKIE + "=" + set_cookie + "; HttpOnly; Path=/; "
                             "SameSite=Lax; Max-Age=" + str(config.SESSION_TTL_HOURS * 3600))
        if clear_cookie:
            self.send_header("Set-Cookie", COOKIE + "=; HttpOnly; Path=/; Max-Age=0")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length > MAX_BODY:
            return None
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None

    def _uid(self):
        c = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        return auth.session_uid(c[COOKIE].value) if COOKIE in c else None

    # ── GET ──

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/health":
            self._json({"ok": True, "service": "monica", "phase": 1})
            return
        if path == "/api/me":
            uid = self._uid()
            if not uid:
                self._json({"state": "guest"})
                return
            p = auth.load_profile(uid)
            masked = {svc: keys_mod.mask(k)
                      for svc, k in keys_mod.load_keys(config.MACHINE_SECRET, uid).items()}
            self._json({"state": "app", "profile": {
                "user_id": uid, "username": p["username"],
                "avatar": "/api/avatar/" + uid if p.get("avatar") else None,
                "hint": p.get("hint", ""),
                "created": p.get("created", ""),
                "modules": p.get("modules", {}),
                "onboarding": p.get("onboarding", {}),
                "keys_masked": masked,
                "keys_status": p.get("keys_status", {})}})
            return
        if path.startswith("/api/avatar/"):
            uid = path.split("/")[-1]
            d = auth.user_dir(uid)
            if os.path.isdir(d):
                for name in ("avatar.png", "avatar.jpg"):
                    fp = os.path.join(d, name)
                    if os.path.exists(fp):
                        mime = "image/png" if name.endswith("png") else "image/jpeg"
                        with open(fp, "rb") as f:
                            body = f.read()
                        self.send_response(200)
                        self.send_header("Content-Type", mime)
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                        return
            self.send_error(404)
            return
        if path == "/api/models":
            self._json({"models": onboarding.MODELS,
                        "sources": onboarding.SOURCES,
                        "purposes": onboarding.PURPOSES,
                        "languages": onboarding.LANGUAGES,
                        "key_labels": onboarding.KEY_LABELS,
                        "default_model": onboarding.DEFAULT_MODEL})
            return
        if path == "/api/budget":
            # Фаза A: дневной лимит токенов — статус для UI настроек
            uid = self._uid()
            if not uid:
                self._json({"error": "нужен вход"}, 401)
                return
            self._json({"ok": True, "budget": budget.status(uid)})
            return
        if path == "/api/audit":
            # Фаза A: последние 100 записей аудита (UI — позже)
            uid = self._uid()
            if not uid:
                self._json({"error": "нужен вход"}, 401)
                return
            self._json({"ok": True, "events": audit.recent(uid, 100)})
            return
        if path in ("/", "/index.html"):
            self._serve_file("index.html", "text/html; charset=utf-8")
            return
        if path == "/favicon.ico":
            self._serve_file("favicon.svg", "image/svg+xml")
            return
        if path.startswith("/web/"):
            self._serve_file(path[len("/web/"):])
            return
        self.send_error(404)

    def _serve_file(self, rel, ctype=None):
        # Браузеры блокируют CSS с не-CSS MIME — карта обязательна
        # (баг 27.08: theme.css уезжал как text/plain и тема не применялась).
        ext_map = {".css": "text/css; charset=utf-8",
                   ".js": "application/javascript",
                   ".html": "text/html; charset=utf-8",
                   ".png": "image/png", ".jpg": "image/jpeg",
                   ".svg": "image/svg+xml", ".ico": "image/x-icon",
                   ".woff2": "font/woff2", ".woff": "font/woff"}
        ext = os.path.splitext(rel)[1].lower()
        ctype = ext_map.get(ext, ctype or "application/octet-stream")
        # подпапки разрешены (fonts/…), выход за web-каталог — нет
        full = os.path.realpath(os.path.join(config.WEB_DIR, rel))
        wroot = os.path.realpath(config.WEB_DIR)
        if not full.startswith(wroot + os.sep):
            self.send_error(404)
            return
        fp = full
        if not os.path.exists(fp):
            self.send_error(404)
            return
        with open(fp, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ── POST ──

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        body = self._body()
        if body is None:
            self._json({"error": "пустой или слишком большой запрос"}, 400)
            return

        if path == "/api/check-username":
            e = auth.username_error((body.get("username") or "").strip())
            self._json({"ok": e is None, "error": e})
            return

        if path == "/api/hint":
            uid = auth.find_uid(body.get("username"))
            hint = auth.load_profile(uid).get("hint", "") if uid else ""
            self._json({"hint": hint})
            return

        if path == "/api/analytics/check":
            ok = hmac_guard(body.get("password"))
            self._json({"ok": ok}, 200 if ok else 403)
            return

        if path == "/api/onboarding/complete":
            errs, payload = onboarding.validate(body)
            if payload.get("modules", {}).get("analytics"):
                if not hmac_guard(body.get("analytics_password")):
                    errs.append("аналитика: неверный пароль закрытого тестирования")
            if errs:
                self._json({"error": "; ".join(errs)}, 400)
                return
            p = auth.create_user(
                (body.get("username") or "").strip(),
                body.get("password") or "",
                body.get("hint"),
                {"onboarding": {
                    "survey": payload.get("survey"),
                    "prefs": payload.get("prefs"),
                    "completed": True,
                 },
                 "modules": payload.get("modules")})
            if payload.get("modules", {}).get("analytics"):
                p["modules"]["analytics_unlocked"] = True
                auth.save_profile(p["user_id"], p)
            if body.get("avatar"):
                try:
                    p["avatar"] = auth.save_avatar(p["user_id"], body["avatar"])
                    auth.save_profile(p["user_id"], p)
                except Exception as e:
                    p["avatar"] = None
            keys_mod.save_keys(config.MACHINE_SECRET, p["user_id"],
                               {k: (v or "").strip() for k, v in (body.get("keys") or {}).items()})
            token, _ = auth.create_session(p["user_id"])
            self._json({"ok": True, "username": p["username"]}, 200, set_cookie=token)
            return

        if path == "/api/login":
            # Фаза A: rate limit 10/мин на IP (риск 3 — brute-force)
            if not audit.rate_limit("login:" + self.client_address[0], 10):
                self._json({"error": "слишком много запросов, подожди минуту"}, 429)
                return
            uid = auth.verify_login(body.get("username"), body.get("password"))
            if not uid:
                fail_uid = auth.find_uid(body.get("username"))
                if fail_uid:
                    audit.log(fail_uid, "login_fail")
                self._json({"error": "неверный юзернейм или пароль"}, 401)
                return
            audit.log(uid, "login_ok")
            token, _ = auth.create_session(uid)
            self._json({"ok": True}, 200, set_cookie=token)
            return

        # ── всё дальше требует сессию ──
        uid = self._uid()
        if not uid:
            self._json({"error": "нужен вход"}, 401)
            return

        # Фаза A: rate limits 30/мин на uid (chat/stream, terminal)
        if path in ("/api/chat", "/api/chat/stream"):
            if not audit.rate_limit("chat:" + uid, 30):
                self._json({"error": "слишком много запросов, подожди минуту"}, 429)
                return
        elif path == "/api/terminal":
            if not audit.rate_limit("term:" + uid, 30):
                self._json({"error": "слишком много запросов, подожди минуту"}, 429)
                return

        if path == "/api/logout":
            c = cookies.SimpleCookie(self.headers.get("Cookie", ""))
            auth.drop_session(c[COOKIE].value)
            self._json({"ok": True}, 200, clear_cookie=True)
            return

        if path == "/api/keys":
            svc = body.get("service")
            value = (body.get("value") or "").strip()
            if svc not in onboarding.KEY_SERVICES or len(value) < 8:
                self._json({"error": "сервис неизвестен или ключ короткий"}, 400)
                return
            cur = keys_mod.load_keys(config.MACHINE_SECRET, uid)
            cur[svc] = value
            keys_mod.save_keys(config.MACHINE_SECRET, uid, cur)
            audit.log(uid, "key_save", service=svc, length=len(value))
            resp = {"ok": True, "keys_masked":
                    {s: keys_mod.mask(k) for s, k in cur.items()}}
            if body.get("check"):
                res = providers.ping(svc, value)
                resp["check"] = {"ok": res.get("status") == "ok",
                                 "status": res.get("status"),
                                 "message": res.get("detail")}
            self._json(resp)
            return

        if path == "/api/modules":
            p = auth.load_profile(uid)
            mods = p.get("modules", {})
            mod = body.get("module")
            if mod not in ("wikipedia", "telegram", "analytics"):
                self._json({"error": "неизвестный модуль"}, 400)
                return
            enabled = body.get("enabled") is True
            if mod == "analytics" and enabled:
                if not p.get("modules", {}).get("analytics_unlocked") and \
                        not hmac_guard(body.get("password")):
                    self._json({"error": "нужен пароль закрытого тестирования"}, 403)
                    return
                mods["analytics_unlocked"] = True
            mods[mod] = enabled
            p["modules"] = mods
            auth.save_profile(uid, p)
            self._json({"ok": True, "modules": mods})
            return

        if path == "/api/prefs/model":
            # Фаза 5-B: смена модели по умолчанию (чат/настройки)
            mid = body.get("model")
            if mid not in MODEL_SERVICE:
                self._json({"error": "неизвестная модель"}, 400)
                return
            p = auth.load_profile(uid)
            prefs = p.setdefault("onboarding", {}).setdefault("prefs", {})
            prefs["model"] = mid
            auth.save_profile(uid, p)
            self._json({"ok": True, "model": mid})
            return

        if path == "/api/profile/username":
            # Фаза 5-D: смена юзернейма (сессии живут — хранят uid)
            p, err = auth.change_username(uid, (body.get("username") or "").strip())
            if err:
                self._json({"error": err}, 400)
                return
            audit.log(uid, "username_change", username=p["username"])
            self._json({"ok": True, "username": p["username"]})
            return

        if path == "/api/prefs/kind":
            # 6-M2: какая пара работает в чате — лёгкая или сложная
            kind = body.get("kind")
            if kind not in ("light", "smart"):
                self._json({"error": "kind: light|smart"}, 400)
                return
            p = auth.load_profile(uid)
            prefs = p.setdefault("onboarding", {}).setdefault("prefs", {})
            prefs["chat_kind"] = kind
            auth.save_profile(uid, p)
            self._json({"ok": True, "kind": kind})
            return

        if path == "/api/prefs/custom-models":
            # 6-N: правка пары light/smart из настроек (синхронно с онбордингом)
            p = auth.load_profile(uid)
            prefs = p.setdefault("onboarding", {}).setdefault("prefs", {})
            for kind in ("light", "smart"):
                cust = body.get(kind)
                if isinstance(cust, dict):
                    prefs[kind] = {
                        "provider": cust.get("provider") if cust.get("provider") in onboarding.KEY_SERVICES else prefs.get(kind, {}).get("provider", "glm"),
                        "api_model": str(cust.get("api_model") or "").strip()[:120]}
            auth.save_profile(uid, p)
            self._json({"ok": True, "light": prefs.get("light"), "smart": prefs.get("smart")})
            return

        if path == "/api/profile/export":
            # 6-N: экспорт данных — zip (vault + профиль без секретов + история)
            udir = auth.user_dir(uid)
            p = auth.load_profile(uid)
            safe_profile = {k: v for k, v in p.items() if k not in ("keys_status",)}
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("profile.json", json.dumps(safe_profile, ensure_ascii=False, indent=2))
                hp = os.path.join(udir, "history.jsonl")
                if os.path.exists(hp):
                    z.write(hp, "history.jsonl")
                vault = os.path.join(udir, "vault")
                for root, dirs, files in os.walk(vault):
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    for f in files:
                        fp = os.path.join(root, f)
                        rel = os.path.relpath(fp, vault).replace(os.sep, "/")
                        try:
                            z.write(fp, "vault/" + rel)
                        except OSError:
                            pass
            data = buf.getvalue()
            fname = "monica-export-" + time.strftime("%Y%m%d-%H%M") + ".zip"
            audit.log(uid, "export")
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", "attachment; filename=" + fname)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/api/profile/avatar":
            try:
                name = auth.save_avatar(uid, body.get("avatar"))
            except ValueError as e:
                self._json({"error": str(e)}, 400)
                return
            if not name:
                self._json({"error": "нужен dataURL png/jpeg"}, 400)
                return
            p = auth.load_profile(uid)
            p["avatar"] = name
            auth.save_profile(uid, p)
            self._json({"ok": True, "avatar": name})
            return

        if path == "/api/profile/password":
            # Фаза 5-D: смена пароля — старый обязателен, все сессии инвалидируются
            if not auth.verify_password(uid, body.get("old_password") or ""):
                audit.log(uid, "password_change", ok=False, error="wrong_password")
                self._json({"error": "текущий пароль неверен"}, 403)
                return
            p, err = auth.change_password(uid, body.get("new_password") or "")
            if err:
                self._json({"error": err}, 400)
                return
            audit.log(uid, "password_change", ok=True)
            self._json({"ok": True, "relogin": True})
            return

        if path == "/api/profile/key-check":
            # Фаза 5-D: проверка живости уже сохранённого ключа
            svc = body.get("service")
            if svc not in onboarding.KEY_SERVICES:
                self._json({"error": "сервис неизвестен"}, 400)
                return
            user_keys = keys_mod.load_keys(config.MACHINE_SECRET, uid)
            if not user_keys.get(svc):
                self._json({"error": "ключ не задан"}, 400)
                return
            res = providers.ping(svc, user_keys[svc])
            ok = res.get("status") == "ok"
            # Фаза A: keys_status хранит {status, checked_at} (расширенные состояния)
            p = auth.load_profile(uid)
            st = p.setdefault("keys_status", {})
            st[svc] = {"status": res.get("status"), "ok": ok,
                       "message": res.get("detail"),
                       "checked_at": time.strftime("%Y-%m-%d %H:%M")}
            auth.save_profile(uid, p)
            audit.log(uid, "key_check", service=svc, status=res.get("status"))
            self._json({"ok": ok, "status": res.get("status"),
                        "message": res.get("detail")})
            return

        if path == "/api/chat":
            text = (body.get("message") or "").strip()
            if not text:
                self._json({"error": "пустое сообщение"}, 400)
                return
            service, api_mdl = resolve_model(uid, "light")  # 6-O4: лёгкая модель
            user_keys = keys_mod.load_keys(config.MACHINE_SECRET, uid)
            if not user_keys.get(service):
                self._json({"error": "нет ключа для сервиса " + service + " — добавь в настройках"}, 400)
                return
            history = body.get("history") or []
            messages = [{"role": "system", "content": CHAT_SYSTEM}]
            for m in history[-20:]:
                if isinstance(m, dict) and m.get("role") in ("user", "assistant"):
                    messages.append({"role": m["role"], "content": str(m.get("content"))[:4000]})
            # 6-M: медиа-вложения (изображения → vision, аудио → Whisper, файлы → текст)
            media_notes = ""
            if body.get("files"):
                content, media_notes = build_user_content(uid, text, body["files"])
                messages.append({"role": "user", "content": content})
            else:
                messages.append({"role": "user", "content": text})
            # 6-S: общая инструкция проекта (задаётся пользователем в панели проектов)
            pi = str(body.get("project_instruction") or "")[:500].strip()
            if pi:
                messages[0]["content"] += "\n\nКонтекст проекта пользователя: " + pi
            # Фаза A: бюджет — резерв до запроса, commit по фактическому usage
            est = max(1000, sum(len(m["content"]) for m in messages
                                if isinstance(m.get("content"), str)) // 2)
            if not budget.reserve(uid, est, kind="light"):
                self._json({"error": "дневной лимит токенов исчерпан, сброс в полночь",
                            "budget": budget.status(uid)}, 429)
                return
            try:
                reply, usage = providers.chat(service, user_keys[service], api_mdl,
                                              messages, with_usage=True)
            except Exception as e:
                budget.release(uid, est)
                self._json({"error": "модель недоступна: " + str(e)}, 502)
                return
            if config.CFG.get("mock_llm"):
                # mock возвращает JSON {reply, ops} — для чата берём только текст.
                try:
                    reply = json.loads(reply).get("reply", reply)
                except Exception:
                    pass
            total = (usage or {}).get("total_tokens") if isinstance(usage, dict) else None
            if not total:
                total = max(1, len(str(reply)) // 4)
            budget.commit(uid, total, kind="light", est=est)
            self._json({"reply": reply, "model": api_mdl, "media_notes": media_notes})
            return

        if path == "/api/chat/stream":
            text = (body.get("message") or "").strip()
            if not text:
                self._json({"error": "пустое сообщение"}, 400)
                return
            service, api_mdl = resolve_model(uid, "light")  # 6-O4: лёгкая модель
            user_keys = keys_mod.load_keys(config.MACHINE_SECRET, uid)
            if not user_keys.get(service):
                self._json({"error": "нет ключа для сервиса " + service + " — добавь в настройках"}, 400)
                return
            history = body.get("history") or []
            messages = [{"role": "system", "content": CHAT_SYSTEM}]
            for m in history[-20:]:
                if isinstance(m, dict) and m.get("role") in ("user", "assistant"):
                    messages.append({"role": m["role"], "content": str(m.get("content"))[:4000]})
            # 6-M: медиа-вложения
            if body.get("files"):
                content, _notes = build_user_content(uid, text, body["files"])
                messages.append({"role": "user", "content": content})
            else:
                messages.append({"role": "user", "content": text})
            # 6-S: общая инструкция проекта
            pi = str(body.get("project_instruction") or "")[:500].strip()
            if pi:
                messages[0]["content"] += "\n\nКонтекст проекта пользователя: " + pi
            # Фаза A: бюджет — резерв до запроса (429 до старта стрима)
            est = max(1000, sum(len(m["content"]) for m in messages
                                if isinstance(m.get("content"), str)) // 2)
            if not budget.reserve(uid, est, kind="light"):
                self._json({"error": "дневной лимит токенов исчерпан, сброс в полночь",
                            "budget": budget.status(uid)}, 429)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            usage_out = {}
            sent = 0
            try:
                for delta in providers.chat_stream(service, user_keys[service], api_mdl,
                                                   messages, usage_out=usage_out):
                    if delta:
                        sent += len(delta)
                        self.wfile.write(delta.encode("utf-8"))
                        self.wfile.flush()
                total = usage_out.get("total_tokens") or max(1, sent // 4)
                budget.commit(uid, total, kind="light", est=est)
            except Exception as e:
                budget.release(uid, est)
                try:
                    self.wfile.write(("\n\n⚠️ модель прервалась: " + str(e)).encode("utf-8"))
                    self.wfile.flush()
                except Exception:
                    pass
            return

        if path == "/api/terminal":
            text = (body.get("message") or "").strip()
            if not text:
                self._json({"error": "пустое сообщение"}, 400)
                return
            user_keys = keys_mod.load_keys(config.MACHINE_SECRET, uid)
            svc, api_mdl = resolve_model(uid, "smart")  # 6-O4: сложная модель
            if not user_keys.get(svc):
                self._json({"error": "терминалу нужен ключ сервиса " + svc + " — добавь в настройках"}, 400)
                return
            vault = os.path.join(auth.user_dir(uid), "vault")
            messages = [{"role": "system", "content": term.system_prompt(vault)},
                        {"role": "user", "content": text[:4000]}]
            # Фаза A: терминал тоже расходует бюджет (smart-модель)
            est = max(1000, len(text) // 2)
            if not budget.reserve(uid, est, kind="smart"):
                self._json({"error": "дневной лимит токенов исчерпан, сброс в полночь",
                            "budget": budget.status(uid)}, 429)
                return
            try:
                raw, usage = providers.chat(svc, user_keys[svc], api_mdl,
                                            messages, with_usage=True)
            except Exception as e:
                budget.release(uid, est)
                self._json({"error": "модель недоступна: " + str(e)}, 502)
                return
            total = (usage or {}).get("total_tokens") if isinstance(usage, dict) else None
            if not total:
                total = max(1, len(str(raw)) // 4)
            budget.commit(uid, total, kind="smart", est=est)
            reply, ops = term.parse_model_reply(raw)
            clean, errs = term.validate_ops(vault, ops)
            for e in errs:
                reply += chr(10) + "⚠️ " + e
            self._json({"reply": reply, "ops": clean,
                        "note": "подтверди выполнение операций" if clean else None})
            return

        if path == "/api/terminal/execute":
            vault = os.path.join(auth.user_dir(uid), "vault")
            clean, errs = term.validate_ops(vault, body.get("ops"))
            if errs:
                self._json({"error": "; ".join(errs)}, 400)
                return
            if not clean:
                self._json({"error": "нет операций для выполнения"}, 400)
                return
            results, records = term.execute(vault, clean)
            hp = os.path.join(auth.user_dir(uid), "history.jsonl")
            for rec in records:
                hist.record(hp, rec)
                if rec.get("op") == "create_note":
                    mon_mods.enqueue(auth.user_dir(uid), rec["path"])
            audit.log(uid, "vault_write", count=len(clean))
            self._json({"results": results})
            return

        if path == "/api/session/archive":
            # 6-S3: сессия сохраняется в vault/inbox как .md (без записей в history)
            vault = os.path.join(auth.user_dir(uid), "vault")
            title = str(body.get("title") or "сессия").strip()[:60] or "сессия"
            msgs = body.get("msgs") or []
            if not isinstance(msgs, list) or not msgs:
                self._json({"error": "пустая сессия"}, 400)
                return
            slug = "".join(c if c.isalnum() else "-" for c in title.lower()).strip("-")[:40] or "session"
            try:
                full, rel = term.safe_path(vault, "inbox/" + slug + ".md")
            except ValueError as e:
                self._json({"error": str(e)}, 400)
                return
            os.makedirs(os.path.dirname(full), exist_ok=True)
            lines = ["---", "title: " + title,
                     "created: " + str(body.get("started") or "")[:10],
                     "source: сессия с Моникой", "---", "", "# " + title, ""]
            for m in msgs[-200:]:
                if not isinstance(m, dict):
                    continue
                who = "**Ты**" if m.get("role") == "user" else "**Моника**"
                lines += ["", who + ": " + str(m.get("content"))[:4000]]
            with open(full, "w", encoding="utf-8", newline="\n") as f:
                f.write(("\n".join(lines))[:100_000])
            audit.log(uid, "session_archive", path=rel)
            self._json({"ok": True, "path": rel})
            return

        # ── Фаза 5-E: Терминал 2.0 — дерево/чтение/запись/история/undo ──
        if path == "/api/vault/tree":
            vault = os.path.join(auth.user_dir(uid), "vault")
            self._json({"tree": term.vault_tree(vault)})
            return

        if path == "/api/vault/read":
            vault = os.path.join(auth.user_dir(uid), "vault")
            try:
                full, rel = term.safe_path(vault, body.get("path"))
            except ValueError as e:
                self._json({"error": str(e)}, 400)
                return
            if not os.path.exists(full) or os.path.isdir(full):
                self._json({"error": "файл не найден"}, 404)
                return
            with open(full, encoding="utf-8", errors="replace") as f:
                content = f.read(200_000)
            self._json({"ok": True, "path": rel, "content": content})
            return

        if path == "/api/vault/write":
            vault = os.path.join(auth.user_dir(uid), "vault")
            try:
                full, rel = term.safe_path(vault, body.get("path"))
            except ValueError as e:
                self._json({"error": str(e)}, 400)
                return
            content = str(body.get("content") or "")[:100_000]
            prev = None
            if os.path.exists(full):
                with open(full, encoding="utf-8", errors="replace") as f:
                    prev = f.read()[:50_000]
            else:
                os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            audit.log(uid, "vault_write", path=rel)
            hp = os.path.join(auth.user_dir(uid), "history.jsonl")
            rec = hist.record(hp, {"op": "edit_note" if prev is not None else "create_note",
                                   "path": rel, "prev": prev})
            if prev is None:
                mon_mods.enqueue(auth.user_dir(uid), rel)
            self._json({"ok": True, "path": rel, "record_id": rec["id"]})
            return

        if path == "/api/vault/history":
            hp = os.path.join(auth.user_dir(uid), "history.jsonl")
            self._json({"history": hist.recent(hp)})
            return

        if path == "/api/vault/undo":
            vault = os.path.join(auth.user_dir(uid), "vault")
            hp = os.path.join(auth.user_dir(uid), "history.jsonl")
            ok, msg = hist.undo(vault, hp, body.get("id"))
            audit.log(uid, "vault_undo", ok=ok)
            self._json({"ok": ok, "message": msg}, 200 if ok else 400)
            return

        # ── Фаза 5-F: личная вики ──
        if path == "/api/wiki/articles":
            vault = os.path.join(auth.user_dir(uid), "vault")
            if body.get("path"):
                try:
                    full, _rel = term.safe_path(vault, body.get("path"))
                except ValueError as e:
                    self._json({"error": str(e)}, 400)
                    return
                if not os.path.exists(full) or os.path.isdir(full):
                    self._json({"error": "статья не найдена"}, 404)
                    return
                with open(full, encoding="utf-8", errors="replace") as f:
                    self._json({"ok": True, "content": f.read(200_000)})
                return
            self._json({"articles": mon_mods.articles(vault),
                        "queued": len(mon_mods.queued(auth.user_dir(uid)))})
            return

        if path == "/api/wiki/regen":
            p = auth.load_profile(uid)
            if not p.get("modules", {}).get("wikipedia"):
                self._json({"error": "модуль Википедия выключен"}, 403)
                return
            user_keys = keys_mod.load_keys(config.MACHINE_SECRET, uid)
            if not user_keys.get("smart"):
                self._json({"error": "генерации нужен ключ OpenRouter (smart) — добавь в настройках"}, 400)
                return
            vault = os.path.join(auth.user_dir(uid), "vault")
            udir = auth.user_dir(uid)
            notes = [body["note"]] if body.get("note") else mon_mods.queued(udir)[:2]
            done, errs = [], []
            for rel in notes:
                try:
                    art = mon_mods.generate_article(vault, rel, user_keys["smart"])
                    mon_mods.dequeue(udir, rel)
                    done.append(art)
                except Exception as e:
                    errs.append(str(rel) + ": " + str(e))
            self._json({"ok": True, "generated": done, "errors": errs})
            return

        if path == "/api/wiki/search":
            p = auth.load_profile(uid)
            if not p.get("modules", {}).get("wikipedia"):
                self._json({"error": "модуль Википедия выключен"}, 403)
                return
            vault = os.path.join(auth.user_dir(uid), "vault")
            self._json({"results": mon_mods.search(vault, body.get("query", ""))})
            return

        if path == "/api/wiki/extract":
            p = auth.load_profile(uid)
            if not p.get("modules", {}).get("wikipedia"):
                self._json({"error": "модуль Википедия выключен"}, 403)
                return
            title = re.sub(r"[^\w\d -]", "", body.get("title") or "").strip()[:80]
            if not title:
                self._json({"error": "укажи название выжимки"}, 400)
                return
            vault = os.path.join(auth.user_dir(uid), "vault")
            src, rel = term.safe_path(vault, body.get("source_path"))
            with open(src, encoding="utf-8", errors="replace") as f:
                src_text = f.read()
            ex_dir = os.path.join(vault, "Выжимки")
            os.makedirs(ex_dir, exist_ok=True)
            out = os.path.join(ex_dir, title + ".md")
            with open(out, "w", encoding="utf-8", newline="\n") as f:
                f.write("---\ntitle: Выжимка — " + title + "\ntags: [extract]\n"
                        "source: " + rel + "\ncreated: " + time.strftime("%Y-%m-%d")
                        + "\n---\n\n# Выжимка — " + title + "\n\nИсточник: [[" + rel + "]]\n\n"
                        + src_text[:3000] + "\n")
            self._json({"ok": True, "path": "Выжимки/" + title + ".md"})
            return
        if path == "/api/analytics/summary":
            p = auth.load_profile(uid)
            if not p.get("modules", {}).get("analytics"):
                self._json({"error": "модуль Полная аналитика выключен"}, 403)
                return
            vault = os.path.join(auth.user_dir(uid), "vault")
            self._json(mon_mods.summary(vault))
            return

        if path == "/api/wiki/backlinks":
            # 6-W: обратные ссылки — какие статьи вики ссылаются на [[title]]
            vault = os.path.join(auth.user_dir(uid), "vault")
            title = re.sub(r"\.md$", "", os.path.basename(str(body.get("title") or ""))).strip()
            if not title:
                self._json({"error": "укажи статью"}, 400)
                return
            self._json({"backlinks": mon_mods.backlinks(vault, title)})
            return

        if path == "/api/tg/setup":
            token = (body.get("token") or "").strip()
            chat_id = str(body.get("chat_id") or "").strip()
            if len(token) < 20 or not chat_id:
                self._json({"error": "нужны token бота и твой chat_id"}, 400)
                return
            try:
                me_bot = tgbot._api(token, "getMe")
            except Exception as e:
                self._json({"error": "токен не работает: " + str(e)[:120]}, 400)
                return
            tgbot.save_cfg(uid, token, chat_id)
            p = auth.load_profile(uid)
            if p.get("modules", {}).get("telegram"):
                tgbot.start(uid)
            self._json({"ok": True, "bot": "@" + str(me_bot.get("result", {}).get("username", "?"))})
            return

        if path == "/api/tg/status":
            p = auth.load_profile(uid)
            cfgv = tgbot.load_cfg(uid)
            self._json({"configured": bool(cfgv.get("token")),
                        "poller": tgbot.running(uid),
                        "module": bool(p.get("modules", {}).get("telegram"))})
            return

        self._json({"error": "неизвестный маршрут"}, 404)


    # ── PUT ──

    def do_PUT(self):
        # Фаза A: смена дневного лимита токенов (валидация 1000..10 000 000)
        path = urllib.parse.urlparse(self.path).path
        if path != "/api/budget":
            self.send_error(404)
            return
        body = self._body()
        if body is None:
            self._json({"error": "пустой или слишком большой запрос"}, 400)
            return
        uid = self._uid()
        if not uid:
            self._json({"error": "нужен вход"}, 401)
            return
        try:
            limit = int(body.get("limit"))
        except (TypeError, ValueError):
            self._json({"error": "limit должен быть числом"}, 400)
            return
        if not 1000 <= limit <= 10_000_000:
            self._json({"error": "лимит должен быть от 1000 до 10 000 000"}, 400)
            return
        budget.set_limit(uid, limit)
        audit.log(uid, "budget_change", limit=limit)
        self._json({"ok": True, "budget": budget.status(uid)})


def hmac_guard(password):
    import hmac as h
    return bool(password) and h.compare_digest(str(password), config.ANALYTICS_PASSWORD)


class Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    # Фаза 8-prep: опциональный HTTPS — config.json → "ssl": {"cert": "...", "key": "..."}
    scheme = "http"
    if config.SSL_CERT and config.SSL_KEY:
        import ssl
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(config.SSL_CERT, config.SSL_KEY)
        _orig_new = Server.get_request
        def _get_request(self, *a, **kw):
            sock, addr = _orig_new(self, *a, **kw)
            try:
                return ctx.wrap_socket(sock, server_side=True), addr
            except ssl.SSLError:
                try:
                    sock.close()
                except OSError:
                    pass
                raise
        Server.get_request = _get_request
        scheme = "https"
    with Server((config.HOST, config.PORT), Handler) as httpd:
        tgbot.start_all()
        print(f"Monica 1.0 -> {scheme}://{config.HOST}:{config.PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("остановлено")
