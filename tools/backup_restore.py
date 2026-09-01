# -*- coding: utf-8 -*-
"""tools/backup_restore.py — backup/restore data/ Моники с manifest и
checksum (P0). CLI-only: никакого HTTP-endpoint для скачивания архива.

Backup: ZIP + manifest.json (формат, дата, области, sha256 каждого файла).
  Включаются области: users/ (vault, profile, keys.enc, history, digest,
  budget, audit, trash/ — включая trash.json и файлы корзины), telegram/
  (links, link_tokens, link_settings, stickers, integration_events,
  seen_updates), sessions/, audit/.
  НЕ включаются: tmp/, backups/, *.lock, *.tmp, .env, config.json
  (секреты окружения — не данные).
  ВАЖНО: keys.enc зашифрован MONICA_MACHINE_SECRET — храни .env
  (или сам секрет) отдельно от архива, иначе restore не вернёт доступ
  к ключам пользователей.

Restore: ТОЛЬКО в новую пустую директорию (данные не перетираются),
--dry-run проверяет manifest/checksum без изменений, запись требует
--yes (или интерактивного подтверждения).

Использование:
    python tools/backup_restore.py backup [--out DIR] [--keep N]
    python tools/backup_restore.py restore ARCHIVE.zip --to DIR [--dry-run] [--yes]
    python tools/backup_restore.py verify ARCHIVE.zip
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import config  # noqa: E402

FORMAT = "monica-backup"
VERSION = 1
# области данных внутри DATA_DIR (относительные префиксы, /-разделители)
AREAS = ["users", "telegram", "sessions", "audit"]
EXCLUDE_DIRS = {"tmp", "backups", "__pycache__"}
EXCLUDE_SUFFIX = (".lock", ".tmp")
MANIFEST = "manifest.json"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_files(data_dir):
    """Файлы выбранных областей (относительные пути, /-разделители)."""
    out = []
    for area in AREAS:
        base = os.path.join(data_dir, area)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames
                           if d not in EXCLUDE_DIRS and not d.endswith(".lock")]
            for fn in filenames:
                if fn.endswith(EXCLUDE_SUFFIX) or fn == ".write_probe":
                    continue
                fp = os.path.join(dirpath, fn)
                if os.path.isfile(fp):
                    out.append((fp, area + "/" +
                                os.path.relpath(fp, base).replace(os.sep, "/")))
    return out


def cmd_backup(args):
    data_dir = config.DATA_DIR
    out_dir = os.path.abspath(args.out or config.BACKUP_DIR)
    files = collect_files(data_dir)
    if not files:
        print("ERROR: данные не найдены в " + data_dir)
        return 2
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(out_dir, "monica_backup_" + stamp + ".zip")

    manifest = {"format": FORMAT, "version": VERSION,
                "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "areas": AREAS,
                "notes": ["keys.enc зашифрован MONICA_MACHINE_SECRET — "
                          "храни .env отдельно от архива",
                          "trash/ включён целиком (trash.json + файлы)"],
                "files": []}
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for fp, arc in files:
            z.write(fp, arc)
            manifest["files"].append(
                {"path": arc, "size": os.path.getsize(fp),
                 "sha256": sha256_file(fp)})
        z.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))

    # проверка целостности сразу после создания
    ok, err = verify_archive(out_path)
    if not ok:
        print("ERROR: архив не прошёл самопроверку: " + str(err))
        return 1
    print("OK: " + out_path)
    print("    файлов: %d, областей: %s" % (len(files), ", ".join(AREAS)))
    print("    manifest+checksum: проверены при создании")

    # ротация
    keep = args.keep
    backups = sorted(f for f in os.listdir(out_dir)
                     if f.startswith("monica_backup_") and f.endswith(".zip"))
    extra = len(backups) - keep
    for old in backups[:max(0, extra)]:
        os.remove(os.path.join(out_dir, old))
        print("    ротация: удалён " + old)
    return 0


def read_manifest(z):
    try:
        return json.loads(z.read(MANIFEST).decode("utf-8"))
    except KeyError:
        return None
    except Exception as e:
        raise ValueError("manifest повреждён: " + str(e))


def verify_archive(path):
    """(ok, error|manifest). Проверяет формат, список файлов и sha256."""
    try:
        with zipfile.ZipFile(path) as z:
            m = read_manifest(z)
            if not m or m.get("format") != FORMAT:
                return False, "это не архив Моники (manifest.json/format)"
            names = set(n for n in z.namelist() if n != MANIFEST)
            expected = set(f["path"] for f in m["files"])
            if names != expected:
                return False, "состав архива не совпадает с manifest"
            for f in m["files"]:
                h = hashlib.sha256(z.read(f["path"])).hexdigest()
                if h != f["sha256"]:
                    return False, "checksum не сошёлся: " + f["path"]
        return True, m
    except (OSError, ValueError, KeyError) as e:
        return False, str(e)


def cmd_verify(args):
    ok, res = verify_archive(args.archive)
    if not ok:
        print("ERROR: " + str(res))
        return 1
    print("OK: архив цел, файлов %d, создан %s" %
          (len(res["files"]), res.get("created", "?")))
    return 0


def cmd_restore(args):
    dst = os.path.abspath(args.to)
    ok, res = verify_archive(args.archive)
    if not ok:
        print("ERROR: " + str(res))
        return 1
    m = res
    if args.dry_run:
        print("DRY-RUN: manifest и checksum корректны, ничего не изменено.")
        print("    файлов: %d, областей: %s" %
              (len(m["files"]), ", ".join(m.get("areas") or AREAS)))
        print("    restore был бы в: " + dst)
        return 0
    # restore только в НОВУЮ пустую директорию — текущие данные не трогаем
    if os.path.exists(dst) and os.listdir(dst):
        print("ERROR: " + dst + " существует и не пуст — restore выполняется "
              "только в новую пустую директорию")
        return 2
    if not args.yes:
        answer = input("Восстановить %d файл(ов) в %s? [y/N] " %
                       (len(m["files"]), dst))
        if answer.strip().lower() not in ("y", "yes", "д", "да"):
            print("отменено")
            return 1
    os.makedirs(dst, exist_ok=True)
    with zipfile.ZipFile(args.archive) as z:
        for f in m["files"]:
            target = os.path.join(dst, f["path"].replace("/", os.sep))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(f["path"]) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    print("OK: восстановлено %d файл(ов) в %s" % (len(m["files"]), dst))
    print("Дальше: задай MONICA_DATA_DIR=" + dst + " в .env и перезапусти сервер.")
    print("Помни: keys.enc расшифровывается MONICA_MACHINE_SECRET из .env — "
          "он должен совпадать с тем, что был при backup.")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Backup/restore data/ Моники (manifest + sha256)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("backup", help="создать архив с manifest")
    b.add_argument("--out", default=None, help="каталог для архива "
                   "(по умолчанию DATA_DIR/backups)")
    b.add_argument("--keep", type=int, default=14,
                   help="сколько последних архивов хранить")
    b.set_defaults(fn=cmd_backup)

    r = sub.add_parser("restore", help="восстановить архив в новую директорию")
    r.add_argument("archive")
    r.add_argument("--to", required=True, help="НОВАЯ пустая директория")
    r.add_argument("--dry-run", action="store_true",
                   help="проверить manifest/checksum без изменений")
    r.add_argument("--yes", action="store_true", help="без интерактива")
    r.set_defaults(fn=cmd_restore)

    v = sub.add_parser("verify", help="проверить целостность архива")
    v.add_argument("archive")
    v.set_defaults(fn=cmd_verify)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
