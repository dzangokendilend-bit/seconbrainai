# Фаза 7: чистка тестовых аккаунтов перед приглашением реальных тестеров.
# Использование:
#   python tools/cleanup_users.py                 — показать тестовые аккаунты (dry-run)
#   python tools/cleanup_users.py --delete        — удалить их (с подтверждением)
# Тестовыми считаются аккаунты с префиксами: shotfix, diag, ritual, test (test3 и т.п.).
# Основной аккаунт (ivan и т.п.) не трогается — префиксы не совпадают.
# Удаление: запись из index.json + папка data/users/<uid> целиком.
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
import auth  # noqa: E402
import config  # noqa: E402

TEST_PREFIXES = ("shotfix", "diag", "ritual", "test", "tester")


def is_test(username):
    low = (username or "").lower()
    return any(low.startswith(p) for p in TEST_PREFIXES)


def main():
    idx = auth._load_index()
    test_users = [(u, uid) for u, uid in idx.items() if is_test(u)]
    if not test_users:
        print("Тестовых аккаунтов нет.")
        return
    print("Тестовые аккаунты (" + str(len(test_users)) + "):")
    for u, uid in test_users:
        print("  - " + u + "  (" + uid + ")")
    if "--delete" not in sys.argv:
        print("\nDry-run. Для удаления: python tools/cleanup_users.py --delete")
        return
    answer = input("Удалить эти аккаунты и их данные? (yes/no): ")
    if answer.strip().lower() not in ("yes", "y", "да"):
        print("Отменено.")
        return
    for u, uid in test_users:
        udir = os.path.join(config.USERS_DIR, uid)
        if os.path.isdir(udir):
            shutil.rmtree(udir, ignore_errors=True)
        idx.pop(u, None)
        print("  × удалён: " + u)
    auth._save_index(idx)
    print("Готово. Осталось аккаунтов: " + str(len(idx)))


if __name__ == "__main__":
    main()
