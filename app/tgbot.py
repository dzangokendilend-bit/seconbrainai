# Telegram-бот Моники per-user (MVP): long polling в отдельном потоке.
# Команды: /note текст — заметка в vault. Остальное — через Luna.
import json
import os
import threading
import time
import urllib.request

import auth
import config
import keys as keys_mod
import providers

_threads = {}


def _api(token, method, params=None, timeout=35):
    req = urllib.request.Request(
        "https://api.telegram.org/bot" + token + "/" + method,
        data=json.dumps(params or {}).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def tg_path(uid):
    return os.path.join(auth.user_dir(uid), "tg.json")


def load_cfg(uid):
    try:
        with open(tg_path(uid), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cfg(uid, token, chat_id):
    with open(tg_path(uid), "w", encoding="utf-8") as f:
        json.dump({"token": token, "chat_id": chat_id}, f)


def running(uid):
    t = _threads.get(uid)
    return bool(t and t.is_alive())


def start(uid):
    if running(uid):
        return
    t = threading.Thread(target=_poll, args=(uid,), daemon=True)
    _threads[uid] = t
    t.start()


def start_all():
    for username, uid in auth._load_index().items():
        try:
            p = auth.load_profile(uid)
            if p.get("modules", {}).get("telegram") and os.path.exists(tg_path(uid)):
                start(uid)
        except Exception:
            pass


def _poll(uid):
    cfgv = load_cfg(uid)
    token, chat_id = cfgv.get("token"), cfgv.get("chat_id")
    if not token or not chat_id:
        return
    off_path = os.path.join(auth.user_dir(uid), "tg_offset")
    try:
        offset = int(open(off_path).read().strip())
    except Exception:
        offset = 0
    while True:
        try:
            data = _api(token, "getUpdates", {"offset": offset, "timeout": 25})
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                with open(off_path, "w") as f:
                    f.write(str(offset))
                msg = upd.get("message") or {}
                if str((msg.get("chat") or {}).get("id")) != str(chat_id):
                    continue
                text = (msg.get("text") or "").strip()
                if text:
                    _handle(uid, token, chat_id, text)
        except Exception:
            time.sleep(20)


def _handle(uid, token, chat_id, text):
    def send(t):
        try:
            _api(token, "sendMessage", {"chat_id": chat_id, "text": t[:4000]})
        except Exception:
            pass
    vault = os.path.join(auth.user_dir(uid), "vault")
    if text.startswith("/note "):
        body = text[6:].strip()
        name = time.strftime("Из Telegram %Y-%m-%d %H-%M") + ".md"
        with open(os.path.join(vault, name), "w", encoding="utf-8", newline="\n") as f:
            f.write("---\ntitle: " + name[:-3] + "\ntags: [telegram, note]\n---\n\n" + body + "\n")
        send("Заметка сохранена в vault: " + name)
        return
    uk = keys_mod.load_keys(config.MACHINE_SECRET, uid)
    if not uk.get("luna"):
        send("Добавь ключ Luna в настройках — тогда смогу отвечать.")
        return
    try:
        reply = providers.chat("luna", uk["luna"], "gpt-5.6-luna", [
            {"role": "system",
             "content": "Ты — Моника, Telegram-бот пользователя. Отвечай кратко, тепло и по делу."},
            {"role": "user", "content": text[:4000]}])
    except Exception as e:
        send("Модель недоступна: " + str(e)[:200])
        return
    send(reply)
