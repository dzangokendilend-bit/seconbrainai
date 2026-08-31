# Фаза B: аналитика — re-auth токены и heatmap активности за 365 дней.
# Re-auth вместо статического пароля 4221: POST /api/analytics/reauth
# проверяет пароль АККАУНТА (auth.verify_login) и выдаёт короткоживущий
# токен (15 мин, в памяти процесса). Все /api/analytics/* требуют заголовок
# X-Analytics-Token.
# Источники heatmap:
#  - заметки: history.jsonl (create_note/edit_note с ts) + mtime .md в vault;
#  - чаты/импорты: activity.jsonl {ts, kind} — события, которых нет в
#    history.jsonl (чтобы не дублировать, заметки туда не пишутся).
import datetime
import json
import os
import secrets
import time

import auth

TTL = 15 * 60  # 15 минут
_TOKENS = {}   # uid -> {token, expires} — только память процесса


def issue_token(uid):
    tok = secrets.token_urlsafe(32)
    _TOKENS[uid] = {"token": tok, "expires": time.time() + TTL}
    return tok


def check_token(uid, token):
    rec = _TOKENS.get(uid)
    if not rec or rec["expires"] < time.time():
        return False
    return secrets.compare_digest(rec["token"], str(token or ""))


def track(uid, kind, **meta):
    """Событие активности → activity.jsonl. Никогда не бросает.
    Пишем только то, чего нет в history.jsonl: chat, import."""
    try:
        rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": str(kind)[:20]}
        rec.update(meta)
        os.makedirs(auth.user_dir(uid), exist_ok=True)
        with open(os.path.join(auth.user_dir(uid), "activity.jsonl"),
                  "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def heatmap(uid, days=365):
    """[{date: "YYYY-MM-DD", notes: N, chats: N, imports: N}] — последние
    `days` дней подряд до сегодня (локальная дата, Europe/Kiev системная)."""
    udir = auth.user_dir(uid)
    agg = {}  # date -> [notes, chats, imports]

    def bump(date, idx, n=1):
        if not date:
            return
        a = agg.setdefault(date, [0, 0, 0])
        a[idx] += n

    # 1) заметки из history.jsonl (правки/создания терминалом и редактором)
    hp = os.path.join(udir, "history.jsonl")
    if os.path.exists(hp):
        try:
            with open(hp, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if rec.get("op") in ("create_note", "edit_note"):
                        bump(str(rec.get("ts", ""))[:10], 0)
        except OSError:
            pass
    # 2) заметки по mtime файлов vault (создание/правка вне history)
    vault = os.path.join(udir, "vault")
    for root, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in files:
            if fn.lower().endswith((".md", ".txt", ".markdown")):
                try:
                    mt = os.path.getmtime(os.path.join(root, fn))
                    bump(time.strftime("%Y-%m-%d", time.localtime(mt)), 0)
                except OSError:
                    pass
    # 3) чаты и импорты из activity.jsonl
    ap = os.path.join(udir, "activity.jsonl")
    if os.path.exists(ap):
        try:
            with open(ap, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    kind = rec.get("kind")
                    if kind == "chat":
                        bump(str(rec.get("ts", ""))[:10], 1)
                    elif kind == "import":
                        bump(str(rec.get("ts", ""))[:10], 2)
        except OSError:
            pass
    # 4) ровно `days` дней подряд, включая нули
    today = datetime.date.today()
    out = []
    for i in range(days - 1, -1, -1):
        key = (today - datetime.timedelta(days=i)).isoformat()
        n, c, im = agg.get(key, [0, 0, 0])
        out.append({"date": key, "notes": n, "chats": c, "imports": im})
    return out
