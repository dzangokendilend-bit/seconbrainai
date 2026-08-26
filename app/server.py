"""Моника 1.0 — точка входа. Фаза 0: каркас.

Фазы:
  0. Каркас + /health                                   <- текущая
  1. auth.py + onboarding.py (регистрация/вход/онбординг)
  2. чат + терминал (providers.py, terminal.py)
  3. модули: Википедия / Telegram-бот / Полная аналитика
  4. полировка
"""
import os
import http.server
import socketserver
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=config.WEB_DIR, **kw)

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path == "/health":
            body = b'{"ok": true, "service": "monica", "phase": 0}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with Server((config.HOST, config.PORT), Handler) as httpd:
        print(f"Monica 1.0 (phase 0) -> http://{config.HOST}:{config.PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("остановлено")
