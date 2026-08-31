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
TOPICS_DIR = WIKI_DIR + "/topics"

# фикс автора: служебные заметки (логи/inbox/черновики/системные файлы)
# не должны попадать в энциклопедию — при этом в проводнике vault они остаются.
_SERVICE_RE = re.compile(
    r"(^|[/\\\s._\-])(log|logs|journal|journals|diary|inbox|draft|drafts)"
    r"([/\\\s._\-]|$)", re.I)


def is_encyclopedic(relpath, content=""):
    """True — заметка достойна статьи вики; False — служебный лог/inbox/
    черновик/системный файл. Критерии:
    (а) имя/путь не матчит служебные паттерны (log/journal/inbox/draft,
        папки logs/inbox; index/readme отсекаются отдельно);
    (б) содержимое ≥ 40 символов после удаления frontmatter;
    (в) не пустой список/файл."""
    rel = (relpath or "").replace(os.sep, "/").strip().lower()
    if not rel:
        return False
    stem = re.sub(r"\.md$", "", rel.rsplit("/", 1)[-1])
    if stem in ("index", "readme"):
        return False
    if _SERVICE_RE.search(rel):
        return False
    body = re.sub(r"\A---\s*\n.*?\n---\s*\n?", "", content or "",
                  count=1, flags=re.S)
    return len(body.strip()) >= 40


def _queue_path(user_dir):
    return os.path.join(user_dir, "wiki_queue.json")


def enqueue(user_dir, rel, vault=None):
    """Ставит заметку в очередь автогенерации статьи вики.
    Сырые логи/inbox/черновики в очередь не попадают (is_encyclopedic)."""
    if rel.startswith(WIKI_DIR + "/"):
        return
    vault = vault or os.path.join(user_dir, "vault")
    try:
        with open(os.path.join(vault, rel), encoding="utf-8",
                  errors="replace") as f:
            content = f.read()
    except Exception:
        content = ""
    if not is_encyclopedic(rel, content):
        return
    p = _queue_path(user_dir)
    try:
        with open(p, encoding="utf-8") as f:
            q = json.load(f)
    except Exception:
        q = []
    if rel not in q:
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
    """Список статей личной вики (vault/wiki/*.md).
    Служебные статьи (сгенерированные из логов/черновиков) скрываются;
    сводные темы (wiki/topics/) видны ВСЕГДА."""
    wdir = os.path.join(vault, WIKI_DIR)
    out = []
    if os.path.isdir(wdir):
        for f in sorted(os.listdir(wdir)):
            if f.lower().endswith(".md"):
                out.append({"title": f[:-3], "path": WIKI_DIR + "/" + f,
                            "topic": False})
        tdir = os.path.join(wdir, "topics")
        if os.path.isdir(tdir):
            for f in sorted(os.listdir(tdir)):
                if f.lower().endswith(".md"):
                    out.append({"title": f[:-3],
                                "path": TOPICS_DIR + "/" + f, "topic": True})
    visible = []
    for a in out:
        if a["topic"]:
            visible.append(a)
            continue
        try:
            with open(os.path.join(vault, a["path"]), encoding="utf-8",
                      errors="replace") as fh:
                content = fh.read()
        except Exception:
            content = ""
        if is_encyclopedic(a["title"], content):
            visible.append(a)
    return visible


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
    import terminal as term
    messages = [
        {"role": "system",
         "content": ("Ты — генератор статей личной энциклопедии (в стиле Иванопедии). "
                     "По заметке пользователя напиши краткую энциклопедическую статью: "
                     "2-4 абзаца без markdown-заголовков первого уровня, нейтральный тон, "
                     "только факты из заметки, ничего не выдумывай. "
                     + term.HARDENING_LINE)},
        # Фаза C: содержимое заметки — данные, не инструкции (threat model §4)
        {"role": "user",
         "content": "Заметка «" + title + "»:\n\n" +
                    term.wrap_data("содержимое заметки " + title, src)}]
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
        # фикс автора: ОДИН источник заголовка — frontmatter title (H1 рисует UI).
        # В тело заголовок не пишем — иначе он дублируется под инфобоксом.
        f.write("---\ntitle: " + title + "\ncreated: " + time.strftime("%Y-%m-%d")
                + "\ntags: [wiki]\nsource: " + note_rel + "\n---\n\n"
                + text + "\n")
    return {"title": title, "path": WIKI_DIR + "/" + fname + ".md"}


# ── фикс автора: сводные страницы знаний «Тема: X» ──

_STOP_WORDS = set(
    "и в на с с а но или для из по от до за к у о об не что как это при "
    "the and for with from that this note notes daily".split())


def collect_topics(vault, top_n=8):
    """Топ-N тем vault: frontmatter tags + #теги в тексте + частые слова
    заголовков/папок. Служебные заметки (is_encyclopedic) не учитываются."""
    tag_count, tag_notes = {}, {}
    word_count, word_notes = {}, {}
    for path in _notes(vault):
        rel = os.path.relpath(path, vault).replace(os.sep, "/")
        if rel.startswith(WIKI_DIR + "/"):
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception:
            continue
        if not is_encyclopedic(rel, text):
            continue
        title = re.sub(r"\.md$", "", rel.rsplit("/", 1)[-1])
        m = re.search(r"^title:\s*(.+)$", text, re.M)
        note_title = m.group(1).strip() if m else title
        tags = set()
        m = re.search(r"^tags:\s*\[(.*?)\]", text, re.M)
        if m:
            for t in re.split(r"[,;\s]+", m.group(1)):
                t = t.strip().strip("'\"").lower()
                if len(t) >= 3 and t != "wiki":
                    tags.add(t)
        for t in re.findall(r"(?<![\w#])#([\w-]{3,})", text):
            tags.add(t.lower())
        for t in tags:
            tag_count[t] = tag_count.get(t, 0) + 1
            tag_notes.setdefault(t, set()).add(note_title)
        # частые слова заголовка заметки и её папок
        folder = rel.rsplit("/", 1)[0] if "/" in rel else ""
        for w in re.findall(r"[а-яёa-z]{4,}", (title + " " + folder).lower()):
            if w in _STOP_WORDS:
                continue
            word_count[w] = word_count.get(w, 0) + 1
            word_notes.setdefault(w, set()).add(note_title)
    cand = [(t, c, sorted(tag_notes[t])) for t, c in tag_count.items() if c >= 2]
    cand += [(w, c, sorted(word_notes[w])) for w, c in word_count.items() if c >= 3]
    cand.sort(key=lambda x: (-x[1], x[0]))
    return [{"topic": t, "count": c, "notes": ns[:12]}
            for t, c, ns in cand[:top_n]]


def generate_topic_article(vault, topic, note_titles, api_key=None):
    """Сводная статья «Тема: X»: список связанных заметок [[ссылками]].
    С smart-моделью — вводный абзац; в mock-режиме/без ключа — структурная
    заглушка (работает без LLM)."""
    lead = ""
    if api_key:
        try:
            import providers
            if not (getattr(providers.config, "CFG", {}) or {}).get("mock_llm"):
                import terminal as term
                messages = [
                    {"role": "system",
                     "content": ("Ты — генератор статей личной энциклопедии. "
                                 "Напиши 1 вводный абзац для сводной статьи по теме, "
                                 "нейтрально, только по списку заметок, без выдумок. "
                                 + term.HARDENING_LINE)},
                    # Фаза C: список заметок — данные, не инструкции
                    {"role": "user",
                     "content": "Тема: «" + topic + "». Заметки: " +
                                term.wrap_data("список заметок пользователя по теме",
                                               ", ".join(note_titles))}]
                lead = providers.chat("smart", api_key, None, messages).strip()
                if lead.startswith("{"):
                    try:
                        lead = str(json.loads(lead).get("reply") or "")
                    except Exception:
                        lead = ""
        except Exception:
            lead = ""
    links = "\n".join("- [[" + t + "]]" for t in note_titles)
    body = (lead + "\n\n" if lead else "") + \
        "Заметки по теме («" + topic + "», " + str(len(note_titles)) + " шт.):\n\n" + links + "\n"
    tdir = os.path.join(vault, WIKI_DIR, "topics")
    os.makedirs(tdir, exist_ok=True)
    fname = re.sub(r"[^\w\d -]", "", topic).strip() or "Тема"
    out = os.path.join(tdir, fname + ".md")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("---\ntitle: Тема: " + topic + "\ncreated: "
                + time.strftime("%Y-%m-%d") + "\ntags: [wiki, topic]\n"
                + "topic: true\n---\n\n" + body)
    return {"title": "Тема: " + topic,
            "path": TOPICS_DIR + "/" + fname + ".md",
            "notes": note_titles}


def topics(vault, api_key=None, top_n=8):
    """Собрать/обновить сводные статьи по топ-темам vault."""
    return [generate_topic_article(vault, t["topic"], t["notes"], api_key)
            for t in collect_topics(vault, top_n)]
