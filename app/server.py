# Моника 1.0 — точка входа. Фаза 1: пользователи и онбординг.
import base64
import json
import os
import re
import sys
import time
import urllib.parse
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auth
import config
import history as hist
import keys as keys_mod
import onboarding
import providers
import terminal as term
import modules as mon_mods
import tgbot

COOKIE = "monica_session"
# Фаза 5-B: карта модель -> сервис генерируется из единого реестра onboarding.MODELS
MODEL_SERVICE = {m["id"]: m["service"] for m in onboarding.MODELS}
CHAT_SYSTEM = ("Ты — Моника, личный ИИ-ассистент пользователя внутри веб-сервиса Моника. "
               "Дружелюбно, просто, без воды. Помогаешь с заметками, модулями и вопросами. "
               "Если нужен ключ или модуль не включён — подскажи зайти в настройки. "
               "Работаешь только с данными этого пользователя.")
MAX_BODY = 2 * 1024 * 1024  # 2 МБ (аватарки dataURL)


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
                "modules": p.get("modules", {}),
                "onboarding": p.get("onboarding", {}),
                "keys_masked": masked}})
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
            uid = auth.verify_login(body.get("username"), body.get("password"))
            if not uid:
                self._json({"error": "неверный юзернейм или пароль"}, 401)
                return
            token, _ = auth.create_session(uid)
            self._json({"ok": True}, 200, set_cookie=token)
            return

        # ── всё дальше требует сессию ──
        uid = self._uid()
        if not uid:
            self._json({"error": "нужен вход"}, 401)
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
            resp = {"ok": True, "keys_masked":
                    {s: keys_mod.mask(k) for s, k in cur.items()}}
            if body.get("check"):
                ok, msg = providers.ping(svc, value)
                resp["check"] = {"ok": ok, "message": msg}
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
            self._json({"ok": True, "username": p["username"]})
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
                self._json({"error": "текущий пароль неверен"}, 403)
                return
            p, err = auth.change_password(uid, body.get("new_password") or "")
            if err:
                self._json({"error": err}, 400)
                return
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
            ok, msg = providers.ping(svc, user_keys[svc])
            self._json({"ok": ok, "message": msg})
            return

        if path == "/api/chat":
            text = (body.get("message") or "").strip()
            if not text:
                self._json({"error": "пустое сообщение"}, 400)
                return
            p = auth.load_profile(uid)
            model = onboarding.normalize_model(
                (p.get("onboarding", {}).get("prefs") or {}).get("model"))
            service = MODEL_SERVICE.get(model, "luna")
            user_keys = keys_mod.load_keys(config.MACHINE_SECRET, uid)
            if not user_keys.get(service):
                self._json({"error": "нет ключа для сервиса " + service + " — добавь в настройках"}, 400)
                return
            history = body.get("history") or []
            messages = [{"role": "system", "content": CHAT_SYSTEM}]
            for m in history[-20:]:
                if isinstance(m, dict) and m.get("role") in ("user", "assistant"):
                    messages.append({"role": m["role"], "content": str(m.get("content"))[:4000]})
            messages.append({"role": "user", "content": text})
            try:
                reply = providers.chat(service, user_keys[service],
                                       onboarding.api_model(model), messages)
            except Exception as e:
                self._json({"error": "модель недоступна: " + str(e)}, 502)
                return
            if config.CFG.get("mock_llm"):
                # mock возвращает JSON {reply, ops} — для чата берём только текст.
                try:
                    reply = json.loads(reply).get("reply", reply)
                except Exception:
                    pass
            self._json({"reply": reply, "model": model})
            return

        if path == "/api/chat/stream":
            text = (body.get("message") or "").strip()
            if not text:
                self._json({"error": "пустое сообщение"}, 400)
                return
            p = auth.load_profile(uid)
            model = onboarding.normalize_model(
                (p.get("onboarding", {}).get("prefs") or {}).get("model"))
            service = MODEL_SERVICE.get(model, "luna")
            user_keys = keys_mod.load_keys(config.MACHINE_SECRET, uid)
            if not user_keys.get(service):
                self._json({"error": "нет ключа для сервиса " + service + " — добавь в настройках"}, 400)
                return
            history = body.get("history") or []
            messages = [{"role": "system", "content": CHAT_SYSTEM}]
            for m in history[-20:]:
                if isinstance(m, dict) and m.get("role") in ("user", "assistant"):
                    messages.append({"role": m["role"], "content": str(m.get("content"))[:4000]})
            messages.append({"role": "user", "content": text})
            api_mdl = onboarding.api_model(model)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                for delta in providers.chat_stream(service, user_keys[service], api_mdl, messages):
                    if delta:
                        self.wfile.write(delta.encode("utf-8"))
                        self.wfile.flush()
            except Exception as e:
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
            if not user_keys.get("glm"):
                self._json({"error": "терминалу нужен ключ GLM — добавь в настройках"}, 400)
                return
            vault = os.path.join(auth.user_dir(uid), "vault")
            messages = [{"role": "system", "content": term.system_prompt(vault)},
                        {"role": "user", "content": text[:4000]}]
            try:
                raw = providers.chat("glm", user_keys["glm"], "glm-5.3-fast", messages)
            except Exception as e:
                self._json({"error": "модель недоступна: " + str(e)}, 502)
                return
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
            self._json({"results": results})
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


def hmac_guard(password):
    import hmac as h
    return bool(password) and h.compare_digest(str(password), config.ANALYTICS_PASSWORD)


class Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with Server((config.HOST, config.PORT), Handler) as httpd:
        tgbot.start_all()
        print(f"Monica 1.0 (phase 3) -> http://{config.HOST}:{config.PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("остановлено")
