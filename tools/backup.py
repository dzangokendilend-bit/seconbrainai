# -*- coding: utf-8 -*-
"""tools/backup.py — простой бэкап data/ Моники (Фаза 8-prep).

P0: пути уважают MONICA_DATA_DIR; для backup с manifest.json и sha256
используй tools/backup_restore.py (рекомендуется).

Использование:
    python tools/backup.py                # бэкап + ротация (хранить 14)
    python tools/backup.py --keep 30      # хранить 30 архивов
    python tools/backup.py --dry-run      # показать, что попадёт в архив
"""
import argparse
import os
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
import config  # noqa: E402

DATA_DIR = config.DATA_DIR
BACKUP_DIR = config.BACKUP_DIR


def collect_files():
    """Все файлы data/ (кроме битых ссылок). Пути — относительно корня проекта."""
    out = []
    if not os.path.isdir(DATA_DIR):
        return out
    for dirpath, dirnames, filenames in os.walk(DATA_DIR):
        for fn in filenames:
            fp = os.path.join(dirpath, fn)
            try:
                if os.path.isfile(fp):
                    out.append(fp)
            except OSError:
                pass
    return out


def make_backup(keep):
    files = collect_files()
    if not files:
        print("data/ пуст или отсутствует — нечего бэкапить.")
        return 1
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(BACKUP_DIR, f"monica_backup_{stamp}.zip")
    total = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for fp in files:
            arc = os.path.relpath(fp, ROOT)
            z.write(fp, arc)
            total += os.path.getsize(fp)
    zsize = os.path.getsize(out_path)
    print(f"OK: {out_path}")
    print(f"    файлов: {len(files)}, исходно {total/1024:.1f} КБ, "
          f"в архиве {zsize/1024:.1f} КБ")

    # Ротация: удалить старейшие сверх keep
    backups = sorted(
        f for f in os.listdir(BACKUP_DIR)
        if f.startswith("monica_backup_") and f.endswith(".zip"))
    extra = len(backups) - keep
    if extra > 0:
        for old in backups[:extra]:
            os.remove(os.path.join(BACKUP_DIR, old))
            print(f"    ротация: удалён {old}")
    print(f"    хранилище: {len(backups) - max(extra, 0)} архив(ов) в backups/")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Бэкап data/ Моники")
    ap.add_argument("--keep", type=int, default=14,
                    help="сколько последних архивов хранить (по умолчанию 14)")
    ap.add_argument("--dry-run", action="store_true",
                    help="только показать, что попадёт в архив")
    args = ap.parse_args()

    files = collect_files()
    if args.dry_run:
        print(f"В архив попало бы {len(files)} файл(ов):")
        for fp in files[:40]:
            print("   ", os.path.relpath(fp, ROOT))
        if len(files) > 40:
            print(f"    … и ещё {len(files) - 40}")
        return 0
    return make_backup(args.keep)


if __name__ == "__main__":
    sys.exit(main())
