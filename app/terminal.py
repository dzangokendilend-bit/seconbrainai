# Терминал Моники: песочница над vault пользователя.
# Промпт требует от модели строгий JSON {reply, ops}; сервер валидирует
# операции по белому списку и чинит пути. Исполнение — только после
# подтверждения пользователя (кнопка в интерфейсе). Удалений в MVP нет.
import json
import os

import config

ALLOWED_OPS = {"create_note", "edit_note", "rename", "move", "read", "list"}

SYSTEM = """Ты — ИИ терминала веб-сервиса Моника. Помогаешь пользователю работать с ЕГО личным vault заметок.

ЖЁСТКИЕ ЗАПРЕТЫ (нарушение недопустимо):
- не трогай системные файлы и ядро Моники (всё вне vault пользователя);
- не меняй конфиги инфраструктуры;
- не выходи за пределы vault этого пользователя, не работай с чужими данными;
- никаких действий против других людей (слежка, взлом, манипуляции);
- удалений файлов в этой версии нет — если просят, вежливо откажись.

МОЖНО: создавать заметки, переименовывать, перемещать, читать, предлагать наведение порядка (архивация, теги, структура) — с объяснением зачем.

ФИЛОСОФИЯ ХРАНИЛИЩА (подход Karpathy «LLM Wiki»):
- vault — не склад файлов, а живая вики, которую поддерживаешь ТЫ: связная, перекрёстно-ссылочная база знаний, которая накапливается со временем.
- Когда пользователь приносит новый материал (заметку, выжимку, сессию из папки inbox) — предложи интеграцию: краткая выжимка, обновление связанных заметок, перекрёстные ссылки в формате [[имя заметки]], обновление index.md (каталог со ссылками и однострочными описаниями) и дописывание log.md (хронология в формате "## [дата] действие | объект").
- Хорошие ответы, сравнения и структуры — предлагай сохранять как новые заметки вики, чтобы знания не терялись в чате.
- АУДИТ хранилища (противоречия между заметками, устаревшие утверждения, страницы-сироты без входящих ссылок, недостающие страницы, дыры в данных) проводи ТОЛЬКО когда пользователь явно попросит («проведи аудит», «наведи порядок», «проверь хранилище»). По собственной инициативе аудит не запускай и не предлагай его навязчиво.

ФОРМАТ ОТВЕТА — строго JSON, без markdown-обёртки:
{"reply": "текст пользователю", "ops": []}
Доступные операции (пути ОТНОСИТЕЛЬНЫЕ от корня vault):
- {"op": "create_note", "path": "папка/имя.md", "content": "текст заметки"}
- {"op": "edit_note", "path": "существующий/файл.md", "content": "новый текст целиком"}
- {"op": "rename", "path": "старое/имя.md", "to": "новое_имя.md"}
- {"op": "move", "path": "путь/файл.md", "to": "другая/папка"}
- {"op": "read", "path": "файл.md"}
- {"op": "list", "path": "папка"}
Если просьба запрещённая — reply с отказом и объяснением, ops: [].
"""
def vault_tree(vault, limit=200):
    """limit=200 — для промпта терминала (LLM не нужен весь vault);
    маршрут /api/vault/tree передаёт больший лимит: и Терминал, и Википедия
    показывают РЕАЛЬНУЮ структуру vault целиком (реворк вики)."""
    out = []
    for root, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), vault).replace(os.sep, "/")
            out.append(rel)
            if len(out) >= limit:
                return out
    return out


def system_prompt(vault):
    tree = vault_tree(vault)
    return SYSTEM + "\n\nТекущий vault (пути):\n" + (chr(10).join(tree) if tree else "(пуст)")


def parse_model_reply(raw):
    """Пытается вытащить JSON {reply, ops}; иначе весь текст = reply."""
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(raw[start:end + 1])
            return str(data.get("reply") or ""), data.get("ops") or []
    except Exception:
        pass
    return raw, []


def _is_inside(root_n, target_n):
    """Принадлежность target корню root (оба normcase'нуты realpath'ы).
    os.path.commonpath сравнивает ПО КОМПОНЕНТАМ: /vault и /vault-backup
    — разные корни (простой startswith без границы каталога пропустил бы)."""
    try:
        return os.path.commonpath([root_n, target_n]) == root_n
    except ValueError:  # разные диски Windows
        return False


def safe_path(vault, rel, for_write=False):
    r"""security-аудит (hardening): ЕДИНАЯ каноническая проверка пути для
    всех файловых endpoints (vault/read|write, wiki/read|extract, terminal,
    history.undo, importer). Возвращает (canonical_full, normalized_rel).

    ВАЖНО про URL-encoding: parse_qs/urllib декодируют percent-encoding
    РОВНО ОДИН раз ДО обработчика (двойной decode не выполняется) — сюда
    приходит уже декодированное значение, поэтому %2Fetc%2Fpasswd виден
    здесь как /etc/passwd и отвергается как абсолютный путь.

    Алгоритм:
      1) null byte → reject (иначе ValueError уже в open() -> 500);
      2) ДО любой нормализации, ДО удаления слешей и ДО join с корнем:
         исходный ввод (после strip) отвергается, если выглядит
         абсолютным/UNC/drive/drive-relative — начинается с "/" или "\\"
         (включая //server/share и \\server\share), содержит ":" (диск C:,
         drive-relative C:relative.md, NTFS alternate data stream) или
         смешанные разделители "/" и "\\". Абсолютный путь НЕ превращается
         в относительный — отклоняется;
      3) backslash -> "/", разбор по компонентам: пустые и all-dot
         (".", "..", "...", "....") → reject (".." — traversal, "...."
         Win32 молча нормализует — path confusion);
      4) join с vault root; realpath цели и корня разрешает symlinks:
         symlink внутри vault, ведущий наружу, раскрывается в реальный
         путь вне корня и отвергается шагом 5 (и для чтения, и для записи);
      5) принадлежность: _is_inside(normcase(realpath(root)),
         normcase(realpath(target))) — покомпонентное commonpath-сравнение
         с границей каталога; normcase — platform-aware регистр Windows;
      6) для записи (for_write=True): канонический realpath РОДИТЕЛЬСКОГО
         каталога проходит ту же проверку — конечный файл может не
         существовать, но symlink родительской директории наружу не
         позволяет выйти из vault."""
    raw = str(rel or "")
    if chr(0) in raw:
        raise ValueError("недопустимый путь: null byte")
    s = raw.strip()
    if not s:
        raise ValueError("пустой путь")
    if s.startswith("/") or s.startswith("\\"):
        raise ValueError("абсолютные и UNC-пути запрещены: " + raw)
    if ":" in s:
        raise ValueError("диск/двоеточие в пути запрещены: " + raw)
    if "/" in s and "\\" in s:
        raise ValueError("смешанные разделители запрещены: " + raw)
    norm = s.replace("\\", "/")
    parts = [p for p in norm.split("/") if p != ""]
    if not parts or any(set(p) <= {"."} for p in parts):
        raise ValueError("недопустимый путь: " + raw)
    full = os.path.realpath(os.path.join(vault, *parts))
    vroot = os.path.realpath(vault)
    fn, fv = os.path.normcase(full), os.path.normcase(vroot)
    if fn != fv and not _is_inside(fv, fn):
        raise ValueError("выход за пределы vault: " + raw)
    if for_write:
        pdir = os.path.normcase(os.path.realpath(os.path.dirname(full)))
        if not _is_inside(fv, pdir):
            raise ValueError("родительский каталог вне vault: " + raw)
    return full, "/".join(parts)


def validate_ops(vault, ops):
    clean, errs = [], []
    for op in ops or []:
        name = op.get("op") if isinstance(op, dict) else None
        if name not in ALLOWED_OPS:
            errs.append("операция запрещена: " + str(name))
            continue
        try:
            if name in ("create_note", "edit_note"):
                _, rel = safe_path(vault, op.get("path"))
                clean.append({"op": name, "path": rel,
                              "content": str(op.get("content") or "")[:50000]})
            elif name in ("rename", "move"):
                _, rel = safe_path(vault, op.get("path"))
                _, rel2 = safe_path(vault, op.get("to"))
                clean.append({"op": name, "path": rel, "to": rel2})
            else:
                _, rel = safe_path(vault, op.get("path") or "")
                clean.append({"op": name, "path": rel})
        except ValueError as e:
            errs.append(str(e))
    return clean, errs


def execute(vault, ops):
    """Фаза 5-E: исполняет операции и возвращает (сообщения, записи_истории).
    Каждая мутация даёт запись для undo; прежнее содержимое бэкапится (до 50КБ)."""
    res, records = [], []
    for op in ops:
        try:
            # мутации — с canonical-проверкой родительского каталога
            full, rel = safe_path(vault, op["path"], for_write=True)
            if op["op"] == "create_note":
                os.makedirs(os.path.dirname(full), exist_ok=True)
                existed = os.path.exists(full)
                prev = None
                if existed:
                    with open(full, encoding="utf-8", errors="replace") as f:
                        prev = f.read()[:50000]
                with open(full, "w", encoding="utf-8", newline="\n") as f:
                    f.write(op.get("content") or "")
                res.append(("перезаписано: " if existed else "создано: ") + rel)
                records.append({"op": "edit_note" if existed else "create_note",
                                "path": rel, "prev": prev})
            elif op["op"] == "edit_note":
                if not os.path.exists(full):
                    raise ValueError("файл не найден: " + rel)
                with open(full, encoding="utf-8", errors="replace") as f:
                    prev = f.read()[:50000]
                with open(full, "w", encoding="utf-8", newline="\n") as f:
                    f.write(op.get("content") or "")
                res.append("правка сохранена: " + rel)
                records.append({"op": "edit_note", "path": rel, "prev": prev})
            elif op["op"] == "rename":
                full2, rel2 = safe_path(vault, op["to"], for_write=True)
                os.makedirs(os.path.dirname(full2), exist_ok=True)
                if os.path.exists(full2):
                    raise ValueError("цель уже существует: " + rel2)
                os.rename(full, full2)
                res.append("переименовано: " + rel + " -> " + rel2)
                records.append({"op": "rename", "path": rel, "to": rel2})
            elif op["op"] == "move":
                full2, rel2 = safe_path(vault, op["to"], for_write=True)
                os.makedirs(full2, exist_ok=True)
                dest = os.path.join(full2, os.path.basename(full))
                os.replace(full, dest)
                dest_rel = os.path.relpath(dest, vault).replace(os.sep, "/")
                res.append("перемещено: " + rel + " -> " + dest_rel)
                records.append({"op": "move", "path": rel, "to": dest_rel})
            elif op["op"] == "read":
                with open(full, encoding="utf-8") as f:
                    res.append("чтение " + rel + ":\n" + f.read()[:2000])
            elif op["op"] == "list":
                base = full if os.path.isdir(full) else os.path.dirname(full)
                names = sorted(os.listdir(base))[:50]
                res.append("список " + (rel or ".") + ": " + ", ".join(names))
        except Exception as e:
            res.append("ошибка: " + str(e))
    return res, records
