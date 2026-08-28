# Модули «Википедия» и «Полная аналитика»: работа строго в vault пользователя.
import json
import os
import re
import time


def _notes(vault):
    for root, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.lower().endswith(".md"):
                yield os.path.join(root, f)


def search(vault, query, limit=10):
    q = (query or "").strip().lower()
    if not q:
        return []
    terms = q.split()
    hits = []
    for path in _notes(vault):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception:
            continue
        low = text.lower()
        score = sum(low.count(t) for t in terms)
        name_hit = sum(t in os.path.basename(path).lower() for t in terms)
        score += name_hit * 5
        if score <= 0:
            continue
        rel = os.path.relpath(path, vault).replace(os.sep, "/")
        positions = [low.find(t) for t in terms if t in low]
        pos = max(positions) if positions else 0
        snippet = text[max(0, pos - 60):pos + 120].replace(chr(10), " ").strip()
        hits.append({"path": rel, "score": score, "snippet": "…" + snippet + "…"})
    hits.sort(key=lambda h: -h["score"])
    return hits[:limit]


def summary(vault):
    notes = words = 0
    tags = {}
    byday = {}
    week_ago = time.time() - 7 * 86400
    fresh = 0
    for path in _notes(vault):
        notes += 1
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        words += len(text.split())
        m = re.search(r"^tags:\s*\[(.*?)\]", text, re.M)
        if m:
            for t in re.split(r"[,;\s]+", m.group(1)):
                t = t.strip().strip("'\"")
                if t:
                    tags[t] = tags.get(t, 0) + 1
        st = os.path.getmtime(path)
        if st >= week_ago:
            fresh += 1
        day = time.strftime("%Y-%m-%d", time.localtime(st))
        byday[day] = byday.get(day, 0) + 1
    top_tags = sorted(tags.items(), key=lambda kv: -kv[1])[:8]
    return {"notes": notes, "words": words,
            "top_tags": top_tags,
            "changed_last_7d": fresh,
            "by_day": sorted(byday.items())[-14:]}


# ── Личная вики пользователя (Фаза 5-F) ──

WIKI_DIR = "wiki"


def _queue_path(user_dir):
    return os.path.join(user_dir, "wiki_queue.json")


def enqueue(user_dir, rel):
    """Ставит заметку в очередь автогенерации статьи вики."""
    p = _queue_path(user_dir)
    try:
        with open(p, encoding="utf-8") as f:
            q = json.load(f)
    except Exception:
        q = []
    if rel not in q and not rel.startswith(WIKI_DIR + "/"):
        q.append(rel)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(q, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)


def queued(user_dir):
    try:
        with open(_queue_path(user_dir), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def dequeue(user_dir, rel):
    q = [x for x in queued(user_dir) if x != rel]
    p = _queue_path(user_dir)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(q, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def articles(vault):
    """Список статей личной вики (vault/wiki/*.md)."""
    wdir = os.path.join(vault, WIKI_DIR)
    out = []
    if os.path.isdir(wdir):
        for f in sorted(os.listdir(wdir)):
            if f.lower().endswith(".md"):
                out.append({"title": f[:-3], "path": WIKI_DIR + "/" + f})
    return out


def backlinks(vault, title):
    """6-W: статьи вики, ссылающиеся на [[title]] (обратные ссылки)."""
    wdir = os.path.join(vault, WIKI_DIR)
    out = []
    if not os.path.isdir(wdir):
        return out
    needle = ("[[" + title).lower()
    for f in sorted(os.listdir(wdir)):
        if not f.lower().endswith(".md"):
            continue
        own = f[:-3].lower()
        if own == title.lower():
            continue
        try:
            with open(os.path.join(wdir, f), encoding="utf-8", errors="replace") as fh:
                if needle in fh.read().lower():
                    out.append(f[:-3])
        except Exception:
            continue
    return out


def generate_article(vault, note_rel, api_key):
    """Пишет энциклопедическую статью по заметке через smart-модель.
    Шаблон — стиль Иванопедии: front-matter + серифные секции."""
    import providers
    import terminal as term
    full, _ = term.safe_path(vault, note_rel)
    with open(full, encoding="utf-8", errors="replace") as f:
        src = f.read()[:8000]
    title = re.sub(r"\.md$", "", os.path.basename(note_rel))
    messages = [
        {"role": "system",
         "content": ("Ты — генератор статей личной энциклопедии (в стиле Иванопедии). "
                     "По заметке пользователя напиши краткую энциклопедическую статью: "
                     "2-4 абзаца без markdown-заголовков первого уровня, нейтральный тон, "
                     "только факты из заметки, ничего не выдумывай.")},
        {"role": "user", "content": "Заметка «" + title + "»:\n\n" + src}]
    text = providers.chat("smart", api_key, None, messages).strip()
    # mock-провайдер возвращает JSON {reply, ops} — берём только текст
    if text.startswith("{"):
        try:
            text = str(json.loads(text).get("reply") or text)
        except Exception:
            pass
    fname = re.sub(r"[^\w\d -]", "", title).strip() or "Без названия"
    wdir = os.path.join(vault, WIKI_DIR)
    os.makedirs(wdir, exist_ok=True)
    out = os.path.join(wdir, fname + ".md")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("---\ntitle: " + title + "\ncreated: " + time.strftime("%Y-%m-%d")
                + "\ntags: [wiki]\nsource: " + note_rel + "\n---\n\n"
                + "# " + title + "\n\n" + text + "\n")
    return {"title": title, "path": WIKI_DIR + "/" + fname + ".md"}
