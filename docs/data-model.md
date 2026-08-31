# Моника 1.0 — модель данных нового этапа

> Хранение — файлы JSON/MD (без БД-серверов). Все записи JSON — атомарная
> запись через tmp + os.replace (паттерн auth.py). Существующие сущности
> описаны как есть; новые помечены ★.

## 1. Существующие сущности

### users/index.json
```
{ "<username-lower>": "u_<hex16>" }        // username → uid
```

### data/users/<uid>/profile.json
```
user_id, username, password_hash (pbkdf2), salt, hint, avatar, created,
onboarding: { prefs: { model, chat_kind, light{provider,api_model},
             smart{provider,api_model}, ... } },
modules: { wiki: bool, telegram: bool, analytics: bool },
keys_status: { <service>: { ok, message, checked_at } }
★ добавится: budget: { daily_limit, tz }, analytics_unlocked_until,
  telegram_rights: {...}, telemetry: { basic: bool, content: bool }
```

### data/sessions/sessions.json
```
{ "<token>": { uid, created, expires } }    // TTL из config.SESSION_TTL_HOURS
★ добавится: analytics_unlock_until (re-auth, 15 мин)
```

### data/users/<uid>/vault/**.md
Заметки: frontmatter (title/created/tags) + тело; `[[wikilinks]]` — ссылки
по имени. Единственная записываемая зона пользователя.

### data/users/<uid>/history.jsonl
История чата/терминала + undo-диффы (лимит 500, history.py).

### data/users/<uid>/attachments/, tg.json, wiki_queue.json, avatar.*
Медиа-вложения (≤5×10МБ), конфиг TG-бота, очередь вики-генерации, аватар.

## 2. Новые сущности ★

### data/users/<uid>/budget.json (фаза A)
```
{ "date": "2026-08-31", "tz": "Europe/Kiev",
  "daily_limit": 200000,                  // токенов/день, 0 = без лимита
  "used": { "glm": 1200, "smart": 3400, "luna": 800 },
  "reserved": 0 }                          // атомарное резервирование
```
Сброс: при первом запросе нового дня (по tz пользователя). Атомарность:
lock-файл `budget.lock` (os.O_EXCL) + перезапись JSON.

### data/users/<uid>/audit.jsonl (фаза A)
```
{ "ts": "...", "event": "login|password_change|vault_write|export|key_change|
   import|project_invite|...", "meta": {...маскировано...}, "ip": "..." }
```
Append-only; ротация по размеру (например 5 МБ → .1).

### data/users/<uid>/jobs/<job_id>.json + jobs/history.jsonl (фазы B–C)
```
job: { id, kind: "import|digest|backfill", status: queued|running|done|error,
       created, started, finished, progress: {done, total}, report: {...} }
```
Идемпотентность digest: файл `digest-YYYY-MM-DD.json` — существует → пропуск.

### data/users/<uid>/import-report.json (фаза B)
```
{ "source": "...", "strategy": "skip|overwrite|rename",
  "added": N, "skipped_dupes": N, "overwritten": N, "renamed": N,
  "errors": [...], "checksums": { "<sha256>": "<relpath>" } }
```

### data/users/<uid>/stickers.json (фаза D, порт Сибериады)
```
[ { "type": "sticker|animation", "file_id": "...", "desc": "...",
    "moods": ["грусть", ...], "weight": 1.0, "cooldown_until": 0, "added": "..." } ]
```

### data/users/<uid>/tg_link.json (фаза D)
```
{ "code": "123456", "expires": epoch, "chat_id": null }   // одноразовый код
```

### data/projects/<pid>/ (фаза F)
```
project.json: { id, title, owner_uid, created, members: { "<uid>": "role" } }
invite.json:  { code, expires, role }                       // одноразовое
chat.jsonl:   { ts, uid, text }
notes/<name>.md + history.jsonl: снапшоты версий заметок
presence.json: { "<uid>": last_heartbeat }
```
Роли: owner > admin > editor > member > viewer (матрица прав — в
security-threat-model.md).

### data/users/<uid>/trash/ (фаза C)
```
<uid>/trash/<timestamp>-<relpath>   // soft delete, TTL-очистка в jobs
```

### Телеметрия (фаза H)
```
data/telemetry/events-YYYY-MM.json: { "chat_message": N, "import_run": N, ... }
// агрегаты без контента; контентные данные — только opt-in, без привязки к uid
```

## 2.1 Vault-структуры, создаваемые системой
```
vault/Monica/Digests/YYYY-MM-DD.md     # ночной digest (provenance в frontmatter)
vault/Monica/Ideas/*.md                # Product Insights
vault/inbox/                           # импорт/сессии (уже используется 6-S3)
```

## 3. Связи

```
index.json ──username──> uid
uid ──1:1──> profile.json, vault/, history.jsonl, audit.jsonl, jobs/,
             attachments/, tg.json, stickers.json, trash/
uid ──N:M──> projects/<pid> (members с ролями)
session ──> uid (cookie monica_session)
job ──> uid, kind, идемпотентный ключ (дата/чекsum)
```

## 4. Жизненный цикл и удаление

| Данные | Создание | Изменение | Удаление |
|---|---|---|---|
| Аккаунт | онбординг/`/api/login`-регистрация | настройки | `tools/cleanup_users.py --delete` |
| Заметка | терминал/импорт/бот | терминал (с бэкапом+undo) | soft delete → trash (TTL) → физически |
| Сессия | login | — | logout / TTL / смена пароля |
| Вложение | чат | — | вместе с аккаунтом (TTL — обсудить) |
| Job | маршрут/планировщик | статус | архив >30 дней |
| Проект | владелец | роли/заметки | owner (soft → trash) |
| Audit | события | никогда (append-only) | ротация по размеру |
| Телеметрия | события | агрегаты | файл за месяц ротируется |
