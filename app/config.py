"""Конфиг Моники: config.json в корне проекта."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        return json.load(f)


CFG = load()
HOST = CFG.get("host", "127.0.0.1")
PORT = int(CFG.get("port", 8900))
ANALYTICS_PASSWORD = str(CFG.get("analytics_password", ""))
MACHINE_SECRET = str(CFG.get("machine_secret", ""))
SESSION_TTL_HOURS = int(CFG.get("session_ttl_hours", 168))
_SSL = CFG.get("ssl") or {}
SSL_CERT = str(_SSL.get("cert") or "")
SSL_KEY = str(_SSL.get("key") or "")
DATA_DIR = os.path.join(ROOT, "data")
USERS_DIR = os.path.join(DATA_DIR, "users")
SESSIONS_PATH = os.path.join(DATA_DIR, "sessions", "sessions.json")
WEB_DIR = os.path.join(ROOT, "app", "web")
