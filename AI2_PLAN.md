# AI2 — диагностика и исправление реальных пользовательских проблем

> Этап AI2. Порядок: диагностика → план → исправления → тесты → отчёт.
> Правила: только stdlib; smoke 194 не ломать; ключи не выводить; .env не менять;
> security-гварды не ослаблять; при ERR_CONNECTION_REFUSED smoke не считать успешным.

## 1. Исходная диагностика (факты из кода и данных)

### Проблема 1: Luna check ✅, чат → PROVIDER_ENDPOINT_NOT_FOUND
- Frontend route: `POST /api/chat/stream` (app.js chatTurn) и `POST /api/chat`
- Backend route: `server.py:977 /api/chat/stream` → `providers.chat_stream` →
  `model_registry.build_url("luna")` = `https://api.openai.com/v1/chat/completions`
- Проверка: `POST /api/ai/check` → `providers.check_provider("openai")` →
  `providers._check_chat` → ТОТ ЖЕ url (`build_url`), НО payload отличается:
  - check: `{model, messages, max_completion_tokens: 16}` (без temperature)
  - chat: `{model, messages, temperature: 0.6}` (без max_completion_tokens)
- Гипотеза (проверяется live): gpt-5.6-luna отклоняет `temperature` → HTTP 400 →
  `http_error_to_code(400, body)` маппит любой 4xx (не 401/403/404/429) в
  `PROVIDER_ENDPOINT_NOT_FOUND` — ложный код. Endpoint один и тот же, registry
  один; расхождение — в payload и в маппинге ошибок.
- Профиль пользователя wenyangat: `chat_kind=light` → чат реально идёт через luna.

### Проблема 2: UI «ключ не настроен» при рабочем ключе
- Источник данных UI: `setTabKeys` (app.js:2942) → `p.keys_masked` (только ключи,
  сохранённые в keys.enc) + `p.keys_status` (только после ручной проверки).
- Факт: пользователь работает на env-fallback ключах из .env (keys.enc пуст) →
  `keys_masked` пуст → `regStatus()` = «ключ не настроен», хотя
  `/api/ai/check` → ok (resolve_key использует env-fallback).
- Исправление (P3): бэкенд возвращает единый `keys_overview`:
  `key_configured` (bool), `key_source` (env|encrypted_store|none),
  `connection_status` (unknown|working|error), `checked_at`, safe `error_code`.
  UI различает 4 состояния: «Ключ настроен» / «Подключение ещё не проверялось» /
  «Подключение работает» / «Провайдер отклонил ключ».

### Проблема 3: user message не виден в терминальном чате
- `termTurn` (app.js:1903): сразу `addTyping("term")`, `addTMsg("user", text)`
  НЕ вызывается вообще → сообщение пользователя не появляется ни до, ни после
  запроса. (В основном чате `chatTurn` добавляет — P4 распространяет фикс и туда.)

### Проблема 4: статус застывает на «Думаю…»
- `addTyping()` возвращает `{el, stop}`; `stop` только останавливает ротацию фраз
  (`clearInterval`), но НЕ удаляет элемент typing из лога → «Думаю…» остаётся
  навсегда при любой ошибке (`/api/terminal` 502, стрим оборван, JSON-ошибка).
- Исправление (P5): typing-элемент удаляется при answer/run_finished/run_failed;
  статусы динамические; привязка к run_id.

### Проблема 5: файл «Календарь октябрь 2026» не в vault
- Каталоги: MONICA_DATA_DIR=D:\monica-data (активен) И старый <проект>/data.
- Поиск «Календарь» в обоих каталогах: файл НЕ найден нигде → файл НЕ был создан
  (сервер не подтверждал создание; терминал возвращает ops только после
  подтверждения пользователем; при ошибке LLM ops=[]).
- Исправление (P7): после записи — exists-проверка + read-back; результат
  `verified=true|false`; `file_created`-событие; success только при реально
  существующем файле; canonical vault root = auth.user_dir(uid)/vault.

### Проблема 6: счётчик light растёт при ошибке Luna
- `budget.reserve(uid, est, kind="light")` ДО запроса; при ProviderError —
  `release`. Факт: budget.json wenyangat: `used.light=2619` при падающем Luna
  чате — рост происходил в стрим-пути/при частичном успехе либо исторически в
  mock-режиме. Требуется тест до/после для success и failure (P8).

## 2. Реализация (после live-диагностики)

- P1: реальный GLM chat через `POST /api/chat` (тот же route, что UI-стрим)
- P2: реальный Luna chat тем же путём; fix payload chat vs check; fix
  http_error_to_code (400 с unsupported parameter ≠ PROVIDER_ENDPOINT_NOT_FOUND);
  regression-тест «check endpoint == chat endpoint»
- P3: keys_overview в /api/me + UI-состояния
- P4: user message до запроса + run_id (терминал и чат)
- P5: динамические статусы run_started/status/file_read/file_created/answer/
  run_finished/run_failed; typing удаляется
- P6: история действий по клику (раскрывающаяся панель, run_id scope)
- P7: read-back verification создания файлов, verified=true, file_created,
  дерево обновляется
- P8: счётчики только после успеха; release при ошибке; тест до/после
- P9: node --check, py_compile, юниты (tools/ai2_tests.py), health, реальные
  GLM+Luna, 3 smoke-прогона (194+новые)

## 3. Acceptance ledger (gate на каждое требование)

| Gate | Требование | Критерий | Статус |
|---|---|---|---|
| G1 | P1 GLM chat | реальный ответ от OpenRouter через POST /api/chat (UI-route), provider/model/endpoint/status записаны без секрета | MET — live: 200, model=glm-fast, run_id ok |
| G2a | P2 Luna chat check==chat | оба пути используют один registry/adapter/endpoint (build_url), regression-тест падает при расхождении | MET — ai2_tests: check endpoint == chat endpoint |
| G2b | P2 Luna chat live | реальный ответ Luna через POST /api/chat (chat_kind=light) | MET — live: 200 /api/chat + 200 /api/chat/stream (X-Run-Id) |
| G3 | P3 key states | /api/me отдаёт key_configured/key_source/connection_status/checked_at; UI показывает 4 состояния; env-ключ не «не настроен» | MET — live: conn=working/checked_at после check; groq=error честно |
| G4 | P4 user message | user message виден в терминале ДО ответа и после перезагрузки (история), привязан к run_id | MET — addTMsg("user") до запроса; termlog в localStorage; run_id эхо-проверен live |
| G5 | P5 dynamic statuses | run_started/status/file_read/file_created/answer/run_finished/run_failed; нет залипшего «Думаю…» после завершения/ошибки | MET — dropTyping удаляет typing; фразы «Изучаю сеть…»/«Читаю хранилище…»/«Формирую ответ…» |
| G6 | P6 action history | клик по системному сообщению → панель с хронологией текущего run_id (timestamp/op/описание/результат), без секретов | MET — .runlog pop-up; smoke-проверки 2 шт |
| G7 | P7 file creation | создание через /api/terminal/execute: exists + read-back, verified, relative path+size, file_created, дерево обновлено, файл живёт после перезапуска; при отсутствии файла — failed | MET — live: «заметки/Календарь октябрь 2026.md» verified=true size=139; читается и в дереве после рестарта; ghost-файл → verified=false |
| G8 | P8 counters | used.light не растёт при ошибке (тест до/после), растёт только при успехе, provider/model совпадают | MET — ai2_tests: failure used+0/reserved=0; success used+777 |
| G9 | P9 testing | py_compile ok; node --check ok; ai2_tests зелёные; health 200; 3 smoke-прогона подряд 194+ без деградации | MET — COMPILE_OK; ai2 19/19, ai1 35/35; health ok; smoke 200/200 ×3 |

Итог: 10/10 gate MET. UNMET/BLOCKED нет.

Правило остановки: любой gate Pending/UNMET/BLOCKED в финале → НЕ объявлять
готовым; неоднозначность model ID/endpoint (Luna требует /v1/responses) —
зафиксировать в диагностике и остановиться для решения автора.
