# История изменений vault (Фаза 5-E): history.jsonl, append/list/undo.
# Лимит 500 записей. Undo — единственное удаление в системе: откат
# создания файла терминалом/редактором. Всё строго внутри vault (safe_path).
import json
import os
import secrets
import time

import terminal as term

LIMIT = 500


def _load(hist_path):
    if not os.path.exists(hist_path):
        return []
    out = []
    with open(hist_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out


def _save(hist_path, recs):
    tmp = hist_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, hist_path)


def record(hist_path, rec):
    """Добавляет запись мутации {op, path, to?, prev?} в журнал."""
    recs = _load(hist_path)
    entry = {"id": secrets.token_hex(4), "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    entry.update(rec)
    recs.append(entry)
    if len(recs) > LIMIT:
        recs = recs[-LIMIT:]
    _save(hist_path, recs)
    return entry


def recent(hist_path, n=50):
    """Последние n записей, новые сверху."""
    return list(reversed(_load(hist_path)[-n:]))


def undo(vault, hist_path, rec_id):
    """Инверсия операции по id записи. Возвращает (ok, сообщение)."""
    rec = next((r for r in _load(hist_path) if r.get("id") == rec_id), None)
    if not rec:
        return False, "запись не найдена"
    op = rec.get("op")
    try:
        if op == "create_note":
            full, rel = term.safe_path(vault, rec["path"])
            if not os.path.exists(full):
                return False, "файл уже отсутствует: " + rel
            os.remove(full)  # единственное разрешённое удаление — откат созданного
            return True, "откачено создание: " + rel
        if op == "edit_note":
            full, rel = term.safe_path(vault, rec["path"])
            prev = rec.get("prev")
            if prev is None:
                # правка файла, которого раньше не было (перезапись create) — снять файл
                if os.path.exists(full):
                    os.remove(full)
                    return True, "откачено создание: " + rel
                return False, "файл уже отсутствует: " + rel
            with open(full, "w", encoding="utf-8", newline="\n") as f:
                f.write(prev)
            return True, "восстановлена прежняя версия: " + rel
        if op == "rename":
            cur, cur_rel = term.safe_path(vault, rec["to"])
            orig, orig_rel = term.safe_path(vault, rec["path"])
            if not os.path.exists(cur):
                return False, "файл уже отсутствует: " + cur_rel
            if os.path.exists(orig):
                return False, "цель отката уже существует: " + orig_rel
            os.makedirs(os.path.dirname(orig), exist_ok=True)
            os.rename(cur, orig)
            return True, "переименование откачено: " + cur_rel + " -> " + orig_rel
        if op == "move":
            cur, cur_rel = term.safe_path(vault, rec["to"])
            orig, orig_rel = term.safe_path(vault, rec["path"])
            if not os.path.exists(cur):
                return False, "файл уже отсутствует: " + cur_rel
            if os.path.exists(orig):
                return False, "цель отката уже существует: " + orig_rel
            os.makedirs(os.path.dirname(orig), exist_ok=True)
            os.replace(cur, orig)
            return True, "перемещение откачено: " + cur_rel + " -> " + orig_rel
        return False, "операция не требует отката: " + str(op)
    except ValueError as e:
        return False, str(e)
    except OSError as e:
        return False, "ошибка файловой системы: " + str(e)
