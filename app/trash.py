# Фаза C: soft delete — корзина data/users/<uid>/trash/ с TTL 30 дней.
# Удаление заметки = перемещение в trash/<timestamp>_<relpath> (структура
# сохраняется) + запись в trash.json {id, orig_path, deleted_at, restore_path}.
# Восстановление — обратно на orig_path (занято → суффикс « (восстановлено)»).
# TTL-очистка — sweep()/sweep_all() (старт сервера + раз в час из jobs.py).
# Все пути vault — строго через term.safe_path (for_write=True).
import json
import os
import secrets
import time

import auth
import terminal as term

TRASH_TTL_DAYS = 30


def _dir(uid):
    return os.path.join(auth.user_dir(uid), "trash")


def _json_path(uid):
    return os.path.join(_dir(uid), "trash.json")


def _load(uid):
    try:
        with open(_json_path(uid), encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {}
    return d if isinstance(d, dict) else {}


def _save(uid, d):
    os.makedirs(_dir(uid), exist_ok=True)
    tmp = _json_path(uid) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _json_path(uid))


def trash_file(uid, rel):
    """Перемещает файл vault в корзину. Возвращает запись для UI/аудита."""
    vault = os.path.join(auth.user_dir(uid), "vault")
    full, norm = term.safe_path(vault, rel, for_write=True)
    if not os.path.exists(full) or os.path.isdir(full):
        raise ValueError("файл не найден: " + norm)
    os.makedirs(_dir(uid), exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    dest_rel = ts + "_" + norm
    dest = os.path.join(_dir(uid), dest_rel)
    if os.path.exists(dest):  # коллизия в ту же секунду — короткий суффикс
        dest_rel = ts + "_" + secrets.token_hex(3) + "_" + norm
        dest = os.path.join(_dir(uid), dest_rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    os.replace(full, dest)
    rec = {"id": secrets.token_hex(6),
           "orig_path": norm,
           "deleted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "restore_path": norm,
           "trash_path": dest_rel}
    d = _load(uid)
    d[rec["id"]] = rec
    _save(uid, d)
    return rec


def items(uid):
    """Список лежащих в корзине файлов (только с существующим файлом)."""
    d = _load(uid)
    out = []
    for rec in d.values():
        fp = os.path.join(_dir(uid), str(rec.get("trash_path") or ""))
        if os.path.exists(fp):
            out.append({"id": rec.get("id"),
                        "orig_path": rec.get("orig_path"),
                        "deleted_at": rec.get("deleted_at")})
    out.sort(key=lambda r: r.get("deleted_at") or "", reverse=True)
    return out


def restore(uid, item_id):
    """Возвращает файл на orig_path (занято → « (восстановлено)»).
    Возвращает фактический относительный путь."""
    d = _load(uid)
    rec = d.get(str(item_id or ""))
    if not rec:
        raise ValueError("запись корзины не найдена")
    src = os.path.join(_dir(uid), str(rec.get("trash_path") or ""))
    if not os.path.exists(src):
        raise ValueError("файл в корзине не найден")
    vault = os.path.join(auth.user_dir(uid), "vault")
    full, norm = term.safe_path(vault, rec.get("orig_path"), for_write=True)
    if os.path.exists(full):
        root, ext = os.path.splitext(norm)
        cand = root + " (восстановлено)" + ext
        full, norm = term.safe_path(vault, cand, for_write=True)
        i = 2
        while os.path.exists(full):
            full, norm = term.safe_path(
                vault, root + " (восстановлено-" + str(i) + ")" + ext,
                for_write=True)
            i += 1
    os.makedirs(os.path.dirname(full), exist_ok=True)
    os.replace(src, full)
    d.pop(rec.get("id"), None)
    _save(uid, d)
    return norm


def sweep(uid):
    """TTL-очистка корзины одного пользователя: записи/файлы старше
    TRASH_TTL_DAYS удаляются физически (включая осиротевшие файлы без записи)."""
    d = _load(uid)
    cutoff = time.time() - TRASH_TTL_DAYS * 86400
    changed = False
    for rid, rec in list(d.items()):
        fp = os.path.join(_dir(uid), str(rec.get("trash_path") or ""))
        try:
            if os.path.exists(fp) and os.path.getmtime(fp) > cutoff:
                continue
            if os.path.exists(fp):
                os.remove(fp)
            d.pop(rid, None)
            changed = True
        except OSError:
            continue
    troot = _dir(uid)
    if os.path.isdir(troot):
        for root, _dirs, files in os.walk(troot):
            for fn in files:
                if fn == "trash.json":
                    continue
                fp = os.path.join(root, fn)
                try:
                    if os.path.getmtime(fp) <= cutoff:
                        os.remove(fp)
                        changed = True
                except OSError:
                    pass
    if changed:
        _save(uid, d)
    # пустые подкаталоги убрать (структура <timestamp>_<relpath> даёт вложенность)
    if os.path.isdir(troot):
        for root, dirs, files in os.walk(troot, topdown=False):
            if root != troot and not dirs and not files:
                try:
                    os.rmdir(root)
                except OSError:
                    pass


def sweep_all():
    """TTL-очистка корзин всех пользователей (старт сервера + раз в час)."""
    users_dir = auth.config.USERS_DIR
    try:
        names = os.listdir(users_dir)
    except OSError:
        return
    for n in names:
        if os.path.exists(os.path.join(users_dir, n, "profile.json")):
            try:
                sweep(n)
            except Exception:
                pass
