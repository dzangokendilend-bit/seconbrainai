# Модули «Википедия» и «Полная аналитика»: работа строго в vault пользователя.
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
