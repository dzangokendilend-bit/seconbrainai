# Backup / Restore Моники (P0)

CLI-only (никакого HTTP-endpoint для скачивания архива). Инструмент:
`tools/backup_restore.py`. Старый `tools/backup.py` продолжает работать
для быстрых бэкапов, но manifest/checksum есть только в новом.

## Что входит в архив

| Область | Содержимое |
|---|---|
| `users/` | vault (заметки), profile.json, **keys.enc**, history.jsonl, Digests/, budget.json, audit.jsonl, jobs.json, trash/ (trash.json + файлы корзины) |
| `telegram/` | links.json, link_tokens.json, link_settings.json, stickers.json, integration_events.jsonl, seen_updates.json |
| `sessions/` | sessions.json |
| `audit/` | system.jsonl |

**Не входит:** `tmp/`, `backups/`, `*.lock`, `*.tmp`, `.env`, `config.json`
(секреты окружения — не данные; они не должны лежать в архивах).

## Важные оговорки (решения P0)

- **keys.enc включён** — иначе restore не вернёт доступ к API-ключам
  пользователей. Но keys.enc зашифрован `MONICA_MACHINE_SECRET`:
  **храни .env (или сам секрет) отдельно от архива**. Потерял секрет —
  потерял ключи пользователей (они просто перезадаются в настройках).
- **trash/ включён целиком** (metadata trash.json + файлы корзины) —
  корзина часть пользовательских данных; TTL 30 дней продолжит работать
  после restore.

## Команды

```bat
rem создать архив (по умолчанию в DATA_DIR\backups, хранить 14)
python tools\backup_restore.py backup

rem свой каталог и глубина ротации
python tools\backup_restore.py backup --out D:\monica-backups --keep 30

rem проверить целостность архива (manifest + sha256 каждого файла)
python tools\backup_restore.py verify DATA_DIR\backups\monica_backup_YYYYMMDD_HHMMSS.zip

rem dry-run: проверить manifest/checksum, НИЧЕГО не изменяя
python tools\backup_restore.py restore ARCHIVE.zip --to D:\restore-test --dry-run

rem восстановить ТОЛЬКО в новую пустую директорию (текущие данные не трогаются)
python tools\backup_restore.py restore ARCHIVE.zip --to D:\restore-test --yes
```

## После restore

1. Убедись, что `MONICA_MACHINE_SECRET` в `.env` совпадает с тем, что был
   при backup (иначе keys.enc не расшифруется).
2. Пропиши `MONICA_DATA_DIR=<директория restore>` в `.env` и перезапусти сервер.
3. Запусти `python tools\doctor.py` — все проверки должны быть без ERROR.
