# -*- coding: utf-8 -*-
"""tools/migrate_data.py — однократный перенос data/ Моники в новое место (P0).

Копирует текущий каталог mutable-данных (MONICA_DATA_DIR или <проект>/data)
в новую директорию. КОПИРОВАНИЕ: старые файлы никогда не удаляются и не
меняются. После миграции задай MONICA_DATA_DIR в .env и перезапусти сервер.

Использование:
    python tools/migrate_data.py --to D:\\monica-data            # копировать
    python tools/migrate_data.py --to D:\\monica-data --dry-run  # только план
"""
import argparse
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import config  # noqa: E402


def collect(src):
    """Все файлы исходного data-каталога (относительные пути, /-разделители)."""
    out = []
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d != ".write_probe"]
        for fn in filenames:
            if fn == ".write_probe":
                continue
            fp = os.path.join(dirpath, fn)
            rel = os.path.relpath(fp, src).replace(os.sep, "/")
            out.append((fp, rel))
    return out


def main():
    ap = argparse.ArgumentParser(
        description="Перенос data/ Моники в новую директорию (копирование)")
    ap.add_argument("--to", required=True,
                    help="новый каталог data (должен быть пуст или не существовать)")
    ap.add_argument("--dry-run", action="store_true",
                    help="показать план без изменений")
    args = ap.parse_args()

    src = config.DATA_DIR
    dst = os.path.abspath(args.to)
    print("Источник : " + src)
    print("Приёмник : " + dst)

    if os.path.abspath(dst) == os.path.abspath(src):
        print("ERROR: приёмник совпадает с источником")
        return 2
    if os.path.abspath(dst) in (os.path.abspath(ROOT),
                                os.path.abspath(os.path.join(ROOT, "app"))):
        print("ERROR: приёмник не может быть каталогом исходного кода")
        return 2
    if os.path.exists(dst) and os.listdir(dst):
        print("ERROR: приёмник существует и не пуст — укажи новую пустую "
              "директорию (миграция не перетирает данные)")
        return 2
    if not os.path.isdir(src):
        print("ERROR: источник не найден — нечего мигрировать")
        return 2

    files = collect(src)
    total = sum(os.path.getsize(fp) for fp, _ in files)
    print("Файлов к переносу: %d (%.1f КБ)" % (len(files), total / 1024))
    if args.dry_run:
        print("DRY-RUN: ничего не изменено. План (первые 40):")
        for _, rel in files[:40]:
            print("   " + rel)
        if len(files) > 40:
            print("   … и ещё %d" % (len(files) - 40))
        return 0

    t0 = time.time()
    for fp, rel in files:
        target = os.path.join(dst, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(fp, target)
    print("OK: скопировано %d файл(ов) за %.1fс" %
          (len(files), time.time() - t0))
    print("Дальше: добавь в .env строку  MONICA_DATA_DIR=" + dst)
    print("        и перезапусти сервер. Старая data/ не тронута "
          "(можно удалить вручную после проверки).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
