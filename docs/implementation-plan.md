# Моника 1.0 — план реализации нового этапа

> Порядок: сначала фундамент (бюджеты, аудит, re-auth), потом вертикальные
> срезы ценности. После каждого этапа — расширение `tools/ui_smoke.js`,
> прогон (≥76/76), один логический коммит, обновление ROADMAP.md.

## 0b. Этап AI1 — пересборка логики ИИ-провайдеров (выполнен)

Единственный источник правды — `app/model_registry.py` (MODEL_REGISTRY):
ровно 3 модели — `glm-fast` (OpenRouter, `z-ai/glm-5.3-flash`, primary:
чат/терминал/вики/digest), `luna` (OpenAI, `gpt-5.6-luna`, лёгкий чат),
`groq-whisper` (Groq, `whisper-large-v3-turbo`, только speech-to-text).
Ключи только из env/.env: OPENROUTER_API_KEY / OPENAI_API_KEY /
GROQ_API_KEY (GLM_API_KEY — legacy, из routing исключён). Клиент выбирает
только безопасный ключ `glm-fast`/`luna`; иное → 400 MODEL_NOT_ALLOWED.
Новые эндпоинты/файлы: `/api/ai/check` (проверка провайдеров по одному),
`app/ai_log.py` (MONICA_AI_DEBUG → data/audit/ai_debug.jsonl, без секретов),
`tools/ai1_tests.py` (35/35, mock HTTP transport).

Таблица причин (проверено по коду HEAD ce8a9e0 и live-запросами):

| Проблема | Реальная причина в старом коде | Исправление (AI1) |
|---|---|---|
| «⚠️ модель прервалась: HTTP Error 404: Not Found» | config.json задавал base_url УЖЕ с `/chat/completions` (open.bigmodel.cn/api/paas/v4/chat/completions, openrouter.ai/api/v1/chat/completions, api.openai.com/v1/chat/completions), а providers.chat/chat_stream/ping добавляли `/chat/completions` второй раз → `/chat/completions/chat/completions` | MODEL_REGISTRY.build_url(): base_url + endpoint РОВНО ОДИН раз; юнит-тесты на точные URL трёх провайдеров; секция providers в config.json больше не читается (`providers: {}`) |
| 401 Unauthorized | ключ не того провайдера: имена сервисов в коде (glm/smart/luna) не совпадали с именами env-ключей (GLM_API_KEY/OPENROUTER_API_KEY/OPENAI_API_KEY); ключ, сохранённый при регистрации под одним сервисом, молча заменялся env-ключом другого провайдера; GLM_API_KEY мог уходить не по адресу | строгая привязка ключ → провайдер (OPENROUTER→openrouter, OPENAI→openai, GROQ→groq); пользовательский ключ применяется только к своему провайдеру; GLM_API_KEY исключён из routing (только startup-warning) |
| сырой текст ошибки в чате | str(HTTPError) писался прямо в SSE-поток и в JSON-ответы | ProviderError + http_error_to_code() → безопасные коды (API_KEY_MISSING … PROVIDER_NETWORK_ERROR), {code, message} без секретов |
| недоступные/фиктивные model id | openrouter/auto, glm-5.3-fast на open.bigmodel.cn, id моделей не проверялись | live-верификация: `z-ai/glm-5.3-flash` (OpenRouter) и `gpt-5.6-luna` (OpenAI) — GET /models + ping → 200; open.bigmodel.cn и openrouter/auto убраны из routing |

## 0. Таблица «функция → что уже есть → чего не хватает → фаза»

| Функция | Моника (есть) | Сибериада (переиспользуемое) | Чего не хватает | Фаза |
|---|---|---|---|---|
| Импорт vault (.md) | `tools/import_vault.py` (папка, --enqueue/--overwrite) | — | ZIP, frontmatter, wikilinks, checksum-дедуп, preview, стратегии конфликтов, фоновая задача, UI-мастер | A |
| Экспорт vault | `/api/profile/export` (zip) | — | включить attachments + историю | A |
| Heatmap-аналитика | `/api/analytics/summary` (минимум) | `build_wiki.py`: `calendar_heatmap_svg`, `git_activity_by_day` | годовой период, метрики заметки/сообщения/сессии, часовой пояс, UI | B |
| Расширенная аналитика (гейт) | `/api/analytics/check` + пароль `4221` (config) | PIN-подход build_wiki.py | re-auth своим паролем, краткоживущий флаг сессии | B |
| Ночной digest | — | `account_watcher.py` (daily digest-заметки), `save_chat`→inbox | идемпотентная задача, provenance, история запусков, backfill | C |
| Telegram привязка | **D1 ✅**: `tgbot.py` (один бот на инстанс, одноразовый hashed-код привязки, allowlist-команды, webhook+dev polling) | панель прав бота, полноценный бот | панель прав | D |
| Проактивные сообщения | — | `_proactive_loop`, `/proactive on|off|hours|chance`, quiet hours | порт в per-user tgbot.py + opt-in в настройках | D |
| Стикеры | — | `stickers.json`, `pick_sticker`, `handle_incoming_sticker`, `describe_sticker` | каталог per-user, веса, cooldown, UI-библиотека | D |
| Кастомные TG-команды | — | `/settings`, `/proactive` (парсинг команд) | декларативные команды, allowlist, dry-run | E |
| Проверка ключей | `providers.ping()` → keys_status | `_groq_request` читает rate-limit заголовки, fallback-модель при TPD | состояния quota/permissions/unavailable, разбор 429/401/403 | A |
| Rate limits | — | — | in-memory per-IP+uid лимитеры на /api/* | A |
| Дневные лимиты токенов | — | знание лимитов Groq (TPD) в доке `08 System` | budget.py: резервирование, разбивка по моделям, UI настроек | A |
| Audit log | — | `ACTIVITY_LOG_PATH` (jsonl-журнал) | audit.py per-user, append-only, маскирование | A |
| Изоляция пользователей | uid-пути, сессии (auth.py) | — | тесты на cross-user доступ | A |
| Prompt injection защита | CHAT_SYSTEM (одна строка) | `_persona_addon`, экранирование в md_to_safe_html | маркер «данные ≠ инструкции», экранирование контекста заметок | B |
| Soft delete | undo только в терминале (history.py) | — | trash/ с TTL для заметок/сессий | C |
| Совместные проекты | проекты сессий в localStorage (6-S) | — | серверные проекты, роли, приглашения, общий чат, version history | F |
| Presence | — | — | heartbeat + список онлайн | F |
| Веб-поиск | — | `tool_web_search` (SerpAPI, answer_box/knowledge_graph) | SearchProvider, режимы композера, лимит запросов | G |
| Research-пайплайн | — | tool-loop `_groq_tool_loop`, trace-этапы | пайплайн с дедупом и inline citations | G |
| Режим документа | — | — | outline → черновик по секциям | G |
| Прозрачный процесс | — | trace/collected-плашки в chat_server | статус-строка + панель Process (этапы, время, источники) | G |
| Вложения | media.py: слоты, ≤5×10МБ, Whisper, vision | `save_attachment`, `transcribe_audio`, `extract_video_frames` | слот «заметка из vault», единая MIME-проверка | B |
| Лимиты токенов UI | — | — | экран «использовано/осталось» по моделям | A |
| Телеметрия | — | — | счётчики событий, opt-in контента, экран прозрачности, Insights→vault/Monica/Ideas | H |
| Браузерное расширение | — | — | MV3, сохранение страницы/выделения, allowlist, нормализация URL | I (опц.) |
| Тесты критических сценариев | ui_smoke.js 76 проверок | — | тесты: импорт, ключи, RBAC, изоляция, бюджет, идемпотентность digest, цитаты, prompt injection | по фазам |

## 1. Фазы

### Фаза A — «Фундамент безопасности и бюджетов» (первый вертикальный срез) ✅
Состав:
1. `app/budget.py` — дневной лимит токенов: настройки в profile.json,
   атомарное резервирование (lock + JSON), запись расхода по моделям,
   сброс по дате; маршруты `/api/budget` (GET/PUT), учёт в `/api/chat*`.
2. `app/audit.py` — audit.jsonl (login, password change, vault write, export,
   key change); маскирование.
3. Rate limits на чувствительные маршруты (login, chat, terminal).
4. `providers.ping()` → состояния ok/quota/permissions/unavailable.
5. UI: блок «Лимиты и использование» в настройках; цветовые статусы ключей.
Критерии готовности: при исчерпании лимита чат отвечает 429 с понятным
сообщением; audit.jsonl растёт при каждом чувствительном действии; smoke зелёный.
Зависимости: нет. Риски: атомарность при параллельных запросах → lock-файл.

### Фаза B — «Импорт vault + аналитика + вложения 2.0» ✅
Реализовано (утверждённый объём): app/importer.py (ZIP-мастер: preview,
стратегии overwrite/skip/copy, SHA-256-дедуп → import_manifest.json,
.obsidian игнор, traversal + ZIP-bomb защиты, фоновая задача IMPORT_JOBS
с прогрессом; jobs.py не понадобился — реестр задач в importer.py),
app/analytics.py (heatmap 365 дней, activity.jsonl, re-auth токены 15 мин),
маршруты /api/import/* и /api/analytics/reauth|heatmap, UI в tabAna
(reauth-форма, heatmap 53×7 с tooltips и метриками, мастер импорта ZIP),
4221 удалён полностью, smoke 93/93. Слот «заметка из vault» во вложениях —
не входил в утверждённый объём Фазы B, перенесён.
Состав (исходный план):
1. `app/importer.py` + `app/jobs.py`: мастер импорта (папка/ZIP), preview,
   checksum-дедуп, стратегии конфликтов, фоновая идемпотентная задача,
   статус-маршруты; расширение `tools/import_vault.py` → CLI-обёртка над importer.
2. `app/analytics.py`: heatmap за год (заметки/сообщения/сессии), часовой пояс;
   re-auth вместо 4221 (`/api/analytics/unlock` — свой пароль → флаг сессии 15 мин).
3. Вложения: слот «заметка из vault», drag&drop/paste уже есть — унификация
   MIME-проверки в media.py.
Критерии: импорт тестового Obsidian-vault без дублей (отчёт checksum), повторный
запуск — 0 изменений; heatmap рендерится за год; 4221 больше нигде не используется.
Зависимости: A (audit для импорта). Риски: большие vault (тысячи файлов) →
чанковая обработка в jobs, прогресс в UI.

### Фаза C — «Ночной digest + soft delete + prompt injection» ✅
Реализовано: app/jobs.py (daily_knowledge_digest: глобальный daemon-планировщик
~60с, prefs.digest_enabled/digest_time (03:00 по умолчанию), kill switch,
идемпотентность uid+date (done/running не повторяется), факты за 24ч из
history.jsonl + activity.jsonl с дедупом, заметка Digests/<дата>.md с
frontmatter date/type: digest/processed/tokens и provenance у каждой строки,
smart-модель через budget.reserve/commit, mock — структурная заглушка,
jobs.json — история 30 запусков), app/trash.py (soft delete:
trash/<timestamp>_<relpath> + trash.json, restore c « (восстановлено)»,
TTL 30 дней — при старте и раз в час), маршруты /api/jobs,
/api/jobs/digest/run|backfill, /api/prefs/digest, /api/vault/trash (+/restore,
GET-список), prompt injection: term.wrap_data() блоки ДАННЫЕ в терминале,
вики-генераторе и digest + hardening-строка в CHAT_SYSTEM/SYSTEM/шаблонах,
UI: карточка «Ночной digest» в Настройки→Модули и «Корзина» в Терминале,
smoke 152/152 (было 141).
Состав (исходный план):
1. `daily_knowledge_digest` в jobs.py: идемпотентность по дате, inbox-заметки
   с provenance, история запусков, backfill-маршрут.
2. Soft delete: `trash/` + TTL-очистка в jobs.
3. Экранирование контекста заметок (данные ≠ инструкции) + smoke-тест injection.
Критерии: два запуска digest за один день → одна заметка; удалённая заметка
восстанавливается из trash; injection-тест зелёный. — все выполнены.
Зависимости: B (jobs, импорт).

### Фаза D — «Telegram 2.0»
**D1 выполнен (безопасная привязка + минимальный TG-MVP):** один бот на инстанс
(токен администратора в config.json/env, при отсутствии — модуль выключен),
одноразовый URL-safe linking token (sha256-хеш в data/telegram/link_tokens.json,
TTL 600с, attempts ≤5, новый код инвалидирует старый, rate limit 5/час на uid+IP),
привязка через /start только в private chat с conflict detection, allowlist
команд (/start /help /status /open /unlink), webhook /api/telegram/webhook/<secret>
+ dev polling по явному флагу, дедуп update_id (последние 1000), TG audit events
с хешированными id, UI: Настройки→Интеграции→Telegram (полный state machine,
автоопрос 3с, confirm при отвязке).
**D2 выполнен (Telegram Control Center + Sticker Memory):** app/tgstickers.py —
server-side toggles per link (data/telegram/link_settings.json:
remember_stickers_enabled / sticker_reply_enabled /
integration_event_logging_enabled, по умолчанию ВЫКЛ, применяются немедленно
к входящим update без рестарта, audit telegram_settings_changed); память
стикеров (data/telegram/stickers.json, per link_key): private-only, только от
привязанного пользователя, не пересланные, дедуп по telegram_file_unique_id,
лимиты 300/привязка и 30 новых/час, cooldown ответа о выключенной функции,
без LLM; журнал интеграции (data/telegram/integration_events.json, последние
100, целиком управляется toggle event_logging, только техметаданные — без
текстов/токенов/file_id); test-send — единственная исходящая отправка в D2
(активная привязка + enabled стикер + rate limit 10/час, безопасная ошибка
без token/body); link_key в links.json — повторная привязка другого
TG-аккаунта не даёт автоматического доступа к старой библиотеке (данные
остаются у пользователя, но неактивны); endpoints /api/tg/settings,
/api/tg/stickers (+/{id}|toggle|test-send|DELETE, /{id}/preview — серверный
прокси getFile, file_id не в браузере), /api/tg/events?filter= — всё с
auth+scope+rate limit; UI: статус+активность, «Проверить подключение»,
toggles, блок «Скоро» (disabled-заглушки без endpoints), библиотека стикеров
(карточки, preview/fallback, редактор смысла с валидацией 60/300/вес 0–1,
вкл/выкл, удалить с confirm, «Отправить тестом» с confirm), история событий
с фильтрами. Формат каталога адаптирован из Сибериады (stickers.json), без
LLM-автоописаний и автоподбора. D3 (проактивные, кастомные команды) — не начат.
Состав (остаток): проактивные сообщения (порт `_proactive_loop` + quiet hours
+ opt-in), автоподбор одобренных стикеров в ответах (sticker_reply_enabled
уже есть как toggle), кастомные команды (Фаза E).
Критерии: привязка без ручного chat_id; бот молчит в quiet hours; стикер
подбирается по настроению; smoke зелёный (TG-логика тестируется юнит-функциями).
Зависимости: A (audit, budget для TG-запросов тоже).

### Фаза E — «Кастомные команды бота»
Декларативные команды (имя, промпт, действие), allowlist операций, dry-run.
Критерии: команда создаётся в настройках, dry-run показывает план без записи.
Зависимости: D.

### Фаза F — «Совместные проекты»
Серверные проекты, приглашения по коду, роли owner/admin/editor/member/viewer,
общий чат, version history заметок, presence (heartbeat).
Критерии: два аккаунта, приглашение, роль viewer не может писать, история
версий восстанавливается. Зависимости: A (audit, изоляция). Риски: наибольшая
новая поверхность API — делать MVP (без realtime).

### Фаза G — «Поиск, research, прозрачность»
SearchProvider (SerpAPI-порт + vault), 3 режима композера, research-пайплайн
с inline citations, режим документа, статус-строка + панель Process (trace).
Критерии: ответ «в сети» содержит цитаты с URL; панель Process показывает
этапы и время; mock-режим работает. Зависимости: B (vault-индекс), A (бюджет).
Риски: лимиты SerpAPI (250/мес) → кэш и дневной лимит поисков.

### Фаза H — «Телеметрия»
Счётчики событий (агрегированные), opt-in контента, экран прозрачности,
еженедельная сводка → `vault/Monica/Ideas/`.
Критерии: телеметрия выключается одной кнопкой, экран честно описывает сбор.
Зависимости: A.

### Фаза I (опционально) — «Браузерное расширение»
MV3, сохранение страницы/выделения, allowlist доменов, нормализация URL.
Зависимости: A (токен доступа), C (soft delete).

## 2. Сквозные правила
- Каждый этап: план → реализация → расширение ui_smoke.js → прогон 76/76 →
  коммит → запись в ROADMAP.md.
- Тесты добавляются в той же подфазе, что и функция (таблица §0, колонка «Тесты»).
- Никаких новых зависимостей; ffmpeg остаётся внешней опцией.

## 3. Топ-риски
1. Атомарность бюджета при параллельных стримах — lock-файл, тест на гонку.
2. Импорт гигантских vault (GPT Archive Raw Export у Ивана — тысячи файлов) —
   чанки, прогресс, отмена задачи.
3. Расширение server.py (уже 810 строк) — новые модули выносить из server.py,
   маршруты тонкие.
4. SerpAPI 250 запросов/мес — дневной лимит + кэш.
5. Совместные проекты = новая модель доверия — не запускать до фаз A–C.


## 4. P0 — Production Readiness (выполнено, smoke 189/189)

- **Слой секретов**: app/config.py — .env-парсер (stdlib), приоритет
  env > .env > config.json; секреты (machine_secret, telegram_*, LLM-ключи) —
  только из env/.env, config.json — устаревший fallback со startup-warning;
  .env.example; безопасный startup report при старте сервера.
- **MONICA_DATA_DIR**: все mutable-данные (users/, telegram/, sessions/,
  audit/, backups/, tmp/) внутри DATA_DIR; валидация на старте;
  tools/migrate_data.py (--to, --dry-run) — копирование без удаления.
- **Backup/restore**: tools/backup_restore.py — ZIP + manifest.json (sha256
  каждого файла, самопроверка), restore только в новую пустую директорию
  (--dry-run/--yes); keys.enc включён (MONICA_MACHINE_SECRET хранить
  отдельно); docs/backup-restore.md.
- **Docker**: Dockerfile (python:3.12-slim, non-root), .dockerignore,
  compose.yaml (env_file, volume, healthcheck), /health = {"status": "ok"};
  docs/deploy.md.
- **monica doctor**: tools/doctor.py — 13 проверок [OK]/[WARN]/[ERROR],
  без секретов; polling XOR webhook (конфликт = ERROR).
- **digest_llm_enabled** (prefs, default false): digest не тратит токены LLM
  без явного toggle в UI; серверные fallback LLM-ключи из env — не клиенту.
- **Тесты**: tools/p0_tests.py (18: env override, mock/real, digest-гейт,
  MONICA_DATA_DIR, migrate dry-run, backup manifest/checksum, restore,
  doctor, health/API без секретов) + 4 проверки в ui_smoke.js (189/189).
