# Моника 1.0 — точка входа. Фаза 1: пользователи и онбординг.
import base64
import json
import os
import sys
import urllib.parse
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auth
import config
import keys as keys_mod
import onboarding

COOKIE = "monica_session"
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
                        "languages": onboarding.LANGUAGES})
            return
        if path in ("/", "/index.html"):
            self._serve_file("index.html", "text/html; charset=utf-8")
            return
        if path.startswith("/web/"):
            name = os.path.basename(path)
            ctype = "application/javascript" if name.endswith(".js") else "text/plain"
            self._serve_file(name, ctype)
            return
        self.send_error(404)

    def _serve_file(self, name, ctype):
        fp = os.path.join(config.WEB_DIR, name)
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
            self._json({"ok": True, "keys_masked":
                        {s: keys_mod.mask(k) for s, k in cur.items()}})
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

        self._json({"error": "неизвестный маршрут"}, 404)


def hmac_guard(password):
    import hmac as h
    return bool(password) and h.compare_digest(str(password), config.ANALYTICS_PASSWORD)


class Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with Server((config.HOST, config.PORT), Handler) as httpd:
        print(f"Monica 1.0 (phase 1) -> http://{config.HOST}:{config.PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("остановлено")
