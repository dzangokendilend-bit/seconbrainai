# Фаза 7: импорт личного vault Ивана (или любого набора .md) в аккаунт Моники.
# Использование:
#   python tools/import_vault.py <username> <путь-к-папке> [--enqueue] [--overwrite]
# Копирует .md/.txt/.markdown, сохраняя структуру папок. Существующие файлы
# пропускаются (если не указан --overwrite). --enqueue — поставить заметки
# в очередь вики-генерации.
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
import auth  # noqa: E402
import modules as mon_mods  # noqa: E402

TEXT_EXT = (".md", ".txt", ".markdown")


def main():
    if len(sys.argv) < 3:
        print("Использование: python tools/import_vault.py <username> <папка-источник> [--enqueue] [--overwrite]")
        sys.exit(1)
    username = sys.argv[1]
    src = sys.argv[2]
    enqueue = "--enqueue" in sys.argv
    overwrite = "--overwrite" in sys.argv

    uid = auth.find_uid(username)
    if not uid:
        print("Пользователь не найден: " + username)
        sys.exit(1)
    if not os.path.isdir(src):
        print("Папка-источник не найдена: " + src)
        sys.exit(1)

    vault = os.path.join(auth.user_dir(uid), "vault")
    imported, skipped = 0, 0
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in TEXT_EXT:
                continue
            sp = os.path.join(root, f)
            rel = os.path.relpath(sp, src).replace(os.sep, "/")
            dp = os.path.join(vault, *rel.split("/"))
            if os.path.exists(dp) and not overwrite:
                skipped += 1
                continue
            os.makedirs(os.path.dirname(dp), exist_ok=True)
            with open(sp, encoding="utf-8", errors="replace") as fin:
                content = fin.read()
            with open(dp, "w", encoding="utf-8", newline="\n") as fout:
                fout.write(content)
            if enqueue:
                mon_mods.enqueue(auth.user_dir(uid), rel)
            imported += 1
            print("  + " + rel)
    print("Импорт завершён: добавлено " + str(imported) +
          ", пропущено (уже были) " + str(skipped))
    print("Vault: " + vault)


if __name__ == "__main__":
    main()
