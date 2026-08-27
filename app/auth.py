# Пользователи, пароли, сессии Моники.
import hashlib
import hmac
import json
import os
import re
import secrets
import time

import config

USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{3,24}$")
INDEX_PATH = os.path.join(config.USERS_DIR, "index.json")


def _load_index():
    try:
        with open(INDEX_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_index(idx):
    os.makedirs(config.USERS_DIR, exist_ok=True)
    tmp = INDEX_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)
    os.replace(tmp, INDEX_PATH)


def hash_password(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                               bytes.fromhex(salt), 200_000).hex()


def username_error(username):
    if not USERNAME_RE.match(username or ""):
        return "юзернейм: 3-24 символа, латиница/цифры/_/-"
    if username.lower() in _load_index():
        return "такой юзернейм уже занят"
    return None


def user_dir(uid):
    return os.path.join(config.USERS_DIR, uid)


def profile_path(uid):
    return os.path.join(user_dir(uid), "profile.json")


def load_profile(uid):
    with open(profile_path(uid), encoding="utf-8") as f:
        return json.load(f)


def save_profile(uid, profile):
    tmp = profile_path(uid) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    os.replace(tmp, profile_path(uid))


def create_user(username, password, hint, profile_extra):
    idx = _load_index()
    uid = "u_" + secrets.token_hex(8)
    salt = secrets.token_hex(16)
    os.makedirs(os.path.join(user_dir(uid), "vault"), exist_ok=True)
    welcome = (
        "---\ntitle: Добро пожаловать\ncreated: " + time.strftime("%Y-%m-%d") +
        "\ntags: [monica, start]\n---\n\n# Добро пожаловать\n\n"
        "Это твоя личная база заметок в Монике. Создавай папки, заметки,\n"
        "связывай их — терминал и ассистент работают только здесь.\n")
    with open(os.path.join(user_dir(uid), "vault", "Добро пожаловать.md"),
              "w", encoding="utf-8", newline="\n") as f:
        f.write(welcome)
    profile = {
        "user_id": uid,
        "username": username,
        "password_hash": hash_password(password, salt),
        "salt": salt,
        "hint": (hint or "")[:200],
        "avatar": profile_extra.get("avatar"),
        "created": time.strftime("%Y-%m-%d %H:%M"),
        "onboarding": profile_extra.get("onboarding", {}),
        "modules": profile_extra.get("modules", {}),
    }
    save_profile(uid, profile)
    idx[username.lower()] = uid
    _save_index(idx)
    return profile


def find_uid(username):
    return _load_index().get((username or "").lower())


def verify_login(username, password):
    uid = find_uid(username)
    if not uid or not os.path.exists(profile_path(uid)):
        return None
    p = load_profile(uid)
    expect = hmac.compare_digest(p["password_hash"], hash_password(password, p["salt"]))
    return uid if expect else None


def save_avatar(uid, data_url):
    # dataURL вида data:image/png;base64,... — только png/jpg, до ~300 КБ.
    import base64
    m = re.match(r"^data:image/(png|jpeg);base64,(.+)$", data_url or "", re.S)
    if not m:
        return None
    ext = "png" if m.group(1) == "png" else "jpg"
    raw = base64.b64decode(m.group(2))
    if len(raw) > 300 * 1024:
        raise ValueError("аватарка больше 300 КБ")
    name = "avatar." + ext
    with open(os.path.join(user_dir(uid), name), "wb") as f:
        f.write(raw)
    return name


# ── Профиль: смена юзернейма/пароля (Фаза 5-D) ──

def change_username(uid, new_username):
    """Валидация + уникальность + обновление index.json и профиля.
    Сессии хранят uid, поэтому живут — перелогин не нужен."""
    e = username_error(new_username)
    if e:
        return None, e
    p = load_profile(uid)
    idx = _load_index()
    old_key = p["username"].lower()
    if old_key in idx:
        idx.pop(old_key)
    idx[new_username.lower()] = uid
    _save_index(idx)
    p["username"] = new_username
    save_profile(uid, p)
    return p, None


def verify_password(uid, password):
    p = load_profile(uid)
    return hmac.compare_digest(p["password_hash"], hash_password(password, p["salt"]))


def change_password(uid, new_password):
    if len(new_password or "") < 6:
        return None, "пароль: минимум 6 символов"
    p = load_profile(uid)
    salt = secrets.token_hex(16)
    p["salt"] = salt
    p["password_hash"] = hash_password(new_password, salt)
    save_profile(uid, p)
    drop_all_sessions(uid)  # безопасность: все устройства перелогинятся
    return p, None


# ── Сессии ──

def _sessions_path():
    os.makedirs(os.path.dirname(config.SESSIONS_PATH), exist_ok=True)
    return config.SESSIONS_PATH


def _load_sessions():
    try:
        with open(_sessions_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_sessions(s):
    tmp = _sessions_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)
    os.replace(tmp, _sessions_path())


def create_session(uid):
    s = _load_sessions()
    token = secrets.token_hex(32)
    ttl = config.SESSION_TTL_HOURS * 3600
    s[token] = {"uid": uid, "exp": time.time() + ttl}
    _save_sessions(s)
    return token, ttl


def session_uid(token):
    if not token:
        return None
    s = _load_sessions()
    rec = s.get(token)
    if not rec or rec["exp"] < time.time():
        return None
    return rec["uid"]


def drop_session(token):
    s = _load_sessions()
    if token in s:
        s.pop(token)
        _save_sessions(s)


def drop_all_sessions(uid):
    """Инвалидация всех сессий пользователя (после смены пароля)."""
    s = _load_sessions()
    left = {t: r for t, r in s.items() if r.get("uid") != uid}
    if len(left) != len(s):
        _save_sessions(left)
