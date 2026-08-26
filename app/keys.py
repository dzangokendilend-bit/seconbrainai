# Шифрование ключей API пользователей.
# stdlib-only: AES в питоне нет, поэтому потоковый шифр на базе
# HMAC-SHA256 (nonce + счётчик) и метка целостности HMAC.
# Честные пределы: это не AES. Задача — чтобы ключи не лежали в файлах
# открытым текстом и не утекали через скриншоты/логи/бэкапы хранилища.
# Машинный секрет — в config.json (вне git).
import hashlib
import hmac
import json
import os


def _keystream(key, nonce, length):
    out = b""
    counter = 0
    while len(out) < length:
        out += hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        counter += 1
    return out[:length]


def _key_for(machine_secret, user_id):
    return hashlib.pbkdf2_hmac("sha256", machine_secret.encode("utf-8"),
                               ("keys:" + user_id).encode("utf-8"), 100_000)


def keys_path(user_id):
    import config
    return os.path.join(config.USERS_DIR, user_id, "keys.enc")


def save_keys(machine_secret, user_id, obj):
    key = _key_for(machine_secret, user_id)
    nonce = os.urandom(16)
    pt = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    ct = bytes(a ^ b for a, b in zip(pt, _keystream(key, nonce, len(pt))))
    tag = hmac.new(key, nonce + ct, hashlib.sha256).digest()
    with open(keys_path(user_id), "wb") as f:
        f.write(nonce + tag + ct)


def load_keys(machine_secret, user_id):
    path = keys_path(user_id)
    if not os.path.exists(path):
        return {}
    with open(path, "rb") as f:
        blob = f.read()
    key = _key_for(machine_secret, user_id)
    nonce, tag, ct = blob[:16], blob[16:48], blob[48:]
    if not hmac.compare_digest(tag, hmac.new(key, nonce + ct, hashlib.sha256).digest()):
        raise ValueError("keys integrity check failed")
    pt = bytes(a ^ b for a, b in zip(ct, _keystream(key, nonce, len(ct))))
    return json.loads(pt.decode("utf-8"))


def mask(value):
    if not value:
        return ""
    if len(value) <= 8:
        return value[:2] + "..."
    return value[:5] + "..." + value[-4:]
