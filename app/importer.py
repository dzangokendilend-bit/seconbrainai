# Фаза B: импорт Obsidian-vault (ZIP) в vault пользователя.
# Безопасность (threat model, риски 7 и 8):
#  - path traversal: каждый relpath нормализуется (запрет "..", абсолютных
#    путей, дисков) и перепроверяется через terminal.safe_path;
#  - ZIP-bomb: лимиты считаются ДО записи — суммарно ≤200МБ, ≤5000 файлов,
#    один файл ≤20МБ; чтение записи идёт с потолком (размер из заголовка
#    может врать).
# Контент заметок сохраняется байт-в-байт: frontmatter/теги/[[wikilinks]]
# не парсим и не меняем (разбор — задача Фазы C). .obsidian/ игнорируется.
# Дедуп: SHA-256 каждого файла → import_manifest.json {relpath: sha};
# повторный импорт того же файла пропускается даже при strategy=overwrite.
import base64
import hashlib
import io
import json
import os
import secrets
import threading
import time
import zipfile

import analytics
import audit
import auth
import modules as mon_mods
import terminal as term

MAX_TOTAL = 200 * 1024 * 1024   # суммарный распакованный размер
MAX_FILES = 5000                # количество файлов
MAX_FILE = 20 * 1024 * 1024     # один файл
NOTE_EXT = (".md", ".txt", ".markdown")
STRATEGIES = ("overwrite", "skip", "copy")

# Глобальный реестр фоновых задач импорта {job_id: {...}}
IMPORT_JOBS = {}
_LOCK = threading.Lock()


class ImportError(ValueError):
    """Понятная ошибка импорта (битый ZIP, лимиты, стратегия)."""


def decode_zip(data_b64):
    """base64 из тела запроса → байты архива."""
    try:
        raw = base64.b64decode(str(data_b64 or ""))
    except Exception:
        raise ImportError("некорректные данные архива (base64)")
    if not raw:
        raise ImportError("пустой архив")
    return raw


def _norm_rel(name):
    """Нормализация имени из ZIP. None — путь небезопасен (traversal/диск)."""
    rel = str(name or "").replace("\\", "/")
    rel = "/".join(p for p in rel.split("/") if p not in ("", "."))
    rel = rel.lstrip("/")
    if not rel:
        return None
    for p in rel.split("/"):
        if p == ".." or ":" in p:
            return None
    return rel


def _entries(zip_bytes):
    """Безопасное чтение архива в память: [(rel, bytes)], warnings.
    Битый ZIP / превышение лимитов → ImportError (до каких-либо записей)."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except Exception:
        raise ImportError("битый или не-ZIP архив")
    out, total, warnings = [], 0, []
    names = zf.namelist()
    if len(names) > MAX_FILES:
        raise ImportError("слишком много файлов в архиве (>" + str(MAX_FILES) +
                          ") — защита от ZIP-bomb")
    for info in zf.infolist():
        if info.is_dir():
            continue
        rel = _norm_rel(info.filename)
        if not rel:
            warnings.append("пропущен небезопасный путь: " + str(info.filename)[:80])
            continue
        if any(p == ".obsidian" for p in rel.split("/")):
            continue  # конфиг Obsidian не импортируем
        if info.flag_bits & 0x1:
            warnings.append("зашифрованный файл пропущен: " + rel[:80])
            continue
        if info.file_size > MAX_FILE:
            warnings.append("файл больше 20МБ пропущен: " + rel[:80])
            continue
        if total + info.file_size > MAX_TOTAL:
            raise ImportError("архив распаковывается больше 200МБ — лимит ZIP-bomb")
        try:
            with zf.open(info) as f:
                data = f.read(MAX_FILE + 1)  # потолок: заголовок мог соврать
        except Exception:
            warnings.append("не читается: " + rel[:80])
            continue
        if len(data) > MAX_FILE:
            warnings.append("файл больше 20МБ пропущен: " + rel[:80])
            continue
        total += len(data)
        out.append((rel, data))
    if not out:
        raise ImportError("в архиве нет файлов для импорта")
    return out, warnings


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def scan(uid, zip_bytes):
    """Preview без записи: сколько заметок/вложений, размер, конфликты
    (файлы, уже существующие в vault), предупреждения."""
    vault = os.path.join(auth.user_dir(uid), "vault")
    entries, warnings = _entries(zip_bytes)
    conflicts = []
    for rel, _ in entries:
        if os.path.exists(os.path.join(vault, *rel.split("/"))):
            conflicts.append(rel)
    notes = sum(1 for rel, _ in entries if rel.lower().endswith(NOTE_EXT))
    return {"notes": notes,
            "attachments": len(entries) - notes,
            "total": len(entries),
            "total_size": sum(len(d) for _, d in entries),
            "conflicts": conflicts[:200],
            "warnings": warnings[:50]}


def _copy_rel(vault, rel):
    """Свободное имя «имя (N).ext» для стратегии copy. Возвращает rel."""
    root, ext = os.path.splitext(rel)
    n = 1
    while True:
        cand = root + " (" + str(n) + ")" + ext
        if not os.path.exists(os.path.join(vault, *cand.split("/"))):
            return cand
        n += 1


def _write(dest, data):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:  # байт-в-байт, без перекодировки
        f.write(data)


def run(uid, zip_bytes, strategy="skip", job_id=None):
    """Валидирует архив и запускает импорт в фоне. Возвращает job_id."""
    if strategy not in STRATEGIES:
        raise ImportError("стратегия должна быть одной из: " + ", ".join(STRATEGIES))
    entries, warnings = _entries(zip_bytes)  # вся валидация — до потока
    job_id = job_id or ("imp_" + secrets.token_hex(6))
    with _LOCK:
        IMPORT_JOBS[job_id] = {"id": job_id, "status": "running", "progress": 0,
                               "processed": 0, "total": len(entries), "errors": [],
                               "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    threading.Thread(target=_worker,
                     args=(uid, entries, strategy, job_id, warnings),
                     daemon=True).start()
    return job_id


def _worker(uid, entries, strategy, job_id, warnings):
    udir = auth.user_dir(uid)
    vault = os.path.join(udir, "vault")
    man_path = os.path.join(udir, "import_manifest.json")
    manifest = _load_json(man_path)
    counters = {"added": 0, "skipped_dupes": 0, "skipped": 0,
                "overwritten": 0, "renamed": 0}
    report = {"source": "zip", "strategy": strategy, "errors": [],
              "warnings": warnings, "files": []}
    report.update(counters)
    try:
        for i, (rel, data) in enumerate(entries):
            sha = hashlib.sha256(data).hexdigest()
            dest = os.path.join(vault, *rel.split("/"))
            status = "added"
            try:
                if manifest.get(rel) == sha and os.path.exists(dest):
                    status = "dupe"  # checksum-дедуп — даже при overwrite
                elif os.path.exists(dest):
                    if strategy == "skip":
                        status = "skipped"
                    elif strategy == "overwrite":
                        _write(dest, data)
                        status = "overwritten"
                    else:  # copy → «имя (1).md»
                        rel2 = _copy_rel(vault, rel)
                        dest = os.path.join(vault, *rel2.split("/"))
                        _write(dest, data)
                        status = "renamed"
                else:
                    _write(dest, data)
                if status in ("added", "overwritten", "renamed"):
                    manifest[rel] = sha
                    final_rel = rel if status != "renamed" else \
                        os.path.relpath(dest, vault).replace(os.sep, "/")
                    if final_rel.lower().endswith(NOTE_EXT):
                        mon_mods.enqueue(udir, final_rel)
            except Exception as e:
                status = "error"
                report["errors"].append(rel[:120] + ": " + str(e)[:120])
            report["files"].append({"rel": rel[:200], "status": status})
            if status != "error":
                counters[{"dupe": "skipped_dupes", "skipped": "skipped",
                          "overwritten": "overwritten", "renamed": "renamed",
                          "added": "added"}[status]] += 1
            with _LOCK:
                job = IMPORT_JOBS.get(job_id)
                if job:
                    job["processed"] = i + 1
                    job["progress"] = int((i + 1) / len(entries) * 100)
        report.update(counters)
        report["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _save_json(man_path, manifest)
        _save_json(os.path.join(udir, "import-report.json"), report)
        analytics.track(uid, "import", n=counters["added"])
        audit.log(uid, "vault_import", count=counters["added"],
                  skipped=counters["skipped_dupes"] + counters["skipped"])
        with _LOCK:
            job = IMPORT_JOBS.get(job_id)
            if job:
                job["status"] = "done"
                job["progress"] = 100
                job["report"] = report
    except Exception as e:
        with _LOCK:
            job = IMPORT_JOBS.get(job_id)
            if job:
                job["status"] = "error"
                job["errors"].append(str(e)[:200])


def job_status(job_id):
    with _LOCK:
        job = IMPORT_JOBS.get(str(job_id or ""))
        return dict(job) if job else None


def job_report(uid, job_id):
    """Отчёт задачи: из памяти, а после перезапуска сервера — из файла."""
    job = job_status(job_id)
    if job and job.get("report"):
        return job["report"]
    rep = _load_json(os.path.join(auth.user_dir(uid), "import-report.json"))
    return rep or None
