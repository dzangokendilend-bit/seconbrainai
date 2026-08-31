# Моника 1.0 — финальное видение и дорожная карта

> Файл-«память» проекта: любой агент в новой сессии должен прочитать этот файл +
> `AGENT_PLAN_MONICA.md` и свериться с `git log --oneline` перед работой.
> Обновляется после каждой завершённой подфазы.

## 1. Видение продукта

**Моника** — веб-сервис «личного ИИ-пространства»: закрытая бета для друзей,
в будущем публичный продукт. Пользователь заходит на сайт, проходит короткий
онбординг (7 шагов) и получает:

- **Чат** с Моникой на выбранной модели (быстрый переключатель моделей прямо в чате),
  стриминг ответов, markdown, typewriter-заголовок, баннер закрытой беты.
- **Терминал 2.0** — трёхпанельный мини-инструмент над личным vault:
  слева дерево файлов, в центре чат ⇄ md-редактор, справа лог изменений с откатом (undo).
  Жёсткая песочница: только vault пользователя, белый список операций, подтверждение ИИ-действий.
- **Личная Википедия** — автогенерируемые статьи по заметкам в стиле Иванопедии
  (серифные заголовки, инфобоксы), анимация открытия вкладки.
- **Модули**: Википедия (поиск/выжимки), Telegram-бот (Luna, per-user токен),
  Полная аналитика (выключена по умолчанию, re-auth паролем аккаунта → токен 15 мин,
  этические ограничения).
- **Настройки** в трёх секциях: Профиль (юзернейм/аватар/пароль),
  Модели и ключи (шифрованные, с проверкой живости), Модули.

### Принципы (не нарушать)
- Стек: Python stdlib + vanilla JS, никаких новых фреймворков/библиотек анимаций.
- Дизайн: только эстетика Сибериады/Иванопедии (`style.css`, стекло, aurora, серифы).
- Безопасность: ключи шифрованы машинным секретом, изоляция пользователей на сервере,
  терминал не выходит за vault, единственное удаление в системе — undo созданного терминалом файла.
- Дисциплина агента: тестовые файлы только в `tmp/`, план перед крупными правками,
  smoke-тест после каждого коммита, один логический коммит на подфазу.

## 2. Где мы сейчас

Фаза C «Ночной digest + soft delete + prompt injection»: app/jobs.py (daily_knowledge_digest — планировщик ОДНИМ глобальным daemon-потоком ~60с, prefs.digest_enabled/digest_time (по умолчанию 03:00), kill switch, идемпотентность uid+date — done/running не повторяется, факты за 24ч из history.jsonl + activity.jsonl с дедупом по (kind, path, ts), заметка Digests/<дата>.md в отдельной inbox-области vault (исходные заметки не трогаются), frontmatter date/type: digest/processed/tokens, каждая строка факта — с provenance, smart-модель через budget.reserve/commit, в mock — структурная заглушка без LLM, jobs.json — последние 30 запусков, backfill-маршрут), app/trash.py (soft delete: trash/<timestamp>_<relpath> + trash.json, restore с суффиксом « (восстановлено)», TTL 30 дней — при старте сервера и раз в час), маршруты /api/jobs, /api/jobs/digest/run|backfill, /api/prefs/digest, /api/vault/trash (+/restore, GET-список), prompt injection «данные ≠ инструкции»: wrap_data()-блоки ДАННЫЕ в терминале/вики/digest + hardening-строка в CHAT_SYSTEM/SYSTEM/шаблонах вики, UI: карточка «Ночной digest» в Настройки→Модули (переключатель, время, «Запустить сейчас», backfill, история запусков), «Корзина» в дереве Терминала, smoke 152/152 ← HEAD

Реворк «Википедия = оболочка над vault»: app/web/app.js — ОДНО общее дерево vault renderTree(box, paths, opts) для Терминала и вики (папки любой глубины, счётчики .md, collapse-state в localStorage, поиск-фильтр с родителями, выделение по полному пути, filterMd, пустые папки скрыты); openArticle читает РЕАЛЬНЫЙ файл через новый /api/wiki/read (тонкая обёртка над term.safe_path: только .md, {path, content, mtime}, traversal → 400, доступ по сессии) — мок из modules.py убран из production-flow; frontmatter (--- /***) отделяется от тела, title/теги/неизвестные поля в инфобокс .wk-ib, повреждённый YAML → предупреждение, raw-блок сохраняется; md() расширен (таблицы, чек-листы, изображения, [[wikilinks]] с алиасами); wikilinks кликабельны внутри вики: резолв по полному пути/уникальному basename, неоднозначность → выбор вариантов, не найдено → «Статья не найдена» + создать; race-guard (request id) при быстром переключении статей; /api/vault/tree отдаёт vault целиком (лимит 200 остался только для промпта терминала), smoke 113/113 ← HEAD
Фаза B «Импорт vault 2.0, Heatmap активности и Re-auth gate»: app/importer.py (ZIP-мастер: preview, стратегии конфликтов overwrite/skip/copy «имя (1).md», SHA-256-дедуп через import_manifest.json — повторный импорт даёт 0 изменений, .obsidian игнорируется, контент байт-в-байт, защиты path traversal + ZIP-bomb: ≤200МБ/≤5000 файлов/≤20МБ, фоновая задача с прогрессом, маршруты /api/import/preview|run|status|report), app/analytics.py (heatmap за 365 дней: history.jsonl + mtime vault + activity.jsonl; чаты/импорты пишутся в activity.jsonl), re-auth gate (4221/ANALYTICS_PASSWORD/hmac_guard удалены полностью; POST /api/analytics/reauth → secrets.token_urlsafe, TTL 15 мин, X-Analytics-Token на всех /api/analytics/*), UI: мастер импорта ZIP в tabAna, heatmap-сетка 53×7 с tooltips и переключателем метрик, форма «пароль аккаунта», smoke 93/93
Фаза A «Фундамент безопасности и бюджетов»: app/budget.py (дневной лимит 200k, атомарный reserve через lock-файл, разбивка light/smart, сброс в полночь), app/audit.py (append-only audit.jsonl с маскированием), rate limits (login 10/мин на IP, chat/terminal 30/мин на uid), providers.ping() → ok/quota/permissions/unavailable/invalid/network, UI «Лимиты и использование» в настройках, smoke 80/80
Phase 8-prep: деплой-инструменты — tools/backup.py (zip data/ + ротация), HTTPS-опция в server.py (ssl в config.json), автозапуск (start_monica.bat + install_autostart.bat)
f768811 fix round 6: переключатель моделей в чате = роли «⚡ Лёгкая / 🧠 Сложная» (/api/prefs/kind, resolve_model учитывает chat_kind); вкладки настроек скроллятся с контентом
5aa4a75 Phase 7 prep: tools/import_vault.py + tools/cleanup_users.py; 6-F закрыта
d0f067d Phase 6-M: Медиа — app/media.py (Groq Whisper, ffmpeg-кадры, attachments), файлы в чате (до 5 ≤10МБ), слоты композера, ключ Groq в реестре
717fbb6 fix round 5: настройки видимы на новых/старых аккаунтах (.cs-menu absolute), серая полоса вкладок
a1b26e0 Phase 6-N: Настройки 2.0
32aa193 Phase 6-N2: glassmorphism-редизайн настроек
96187ea fix round 4: аватар-оверлей, вкладки, редактор на всю высоту
a160473 Phase 6-O4: 19 багфиксов/фич от автора
b55d0b0 fix round 3: чат-кнопка = новая сессия, бета-кнопка, hatnote вики
678e012 fix round 2: шаг 5, бета-бейдж, сессии в списке, вики-сайдбар, счётчик реплик
c10ec3e Phase 6-O3: «Живое ядро» — сквозная сцена визарда
10fca8e Phase 6-O2 часть 2: ритуал «поле → ядро», ачивки-тосты, финальный запуск; fix bind() слайдера
445da53 Phase 6-O: onboarding 2.0 — слайдер-презентация (5 сцен, орбиты, демо-чат)
1cd8699 fix(6-W): sidebar tools / wk-shell flex
1cf529a Phase 6-W: вики = Иванопедия 1:1 (шаблон статьи, backlinks, /api/wiki/backlinks)
49322f4 Phase 6-T2: drag&drop в дерево vault, create-меню с мини-модалкой
729e739 Phase 6-T: Терминал 2.1 (md-превью, Ctrl+F, рецепты, undo-дифф)
52f08cb Phase 6-S2: модалка проектов, страница проекта, пин-индикатор
1c47f4d Phase 6-S: проекты сессий (+общая инструкция в system-промпт)
e4d33e9 fix: клики по бета-баннеру (pointer-events)
… (ранее: 5-A..5-I, 4-design, 1–3)
```

Готово: каркас пользователей, онбординг 2.0 («Ритуал запуска» + «Живое ядро»), чат
со стримингом и медиа-вложениями, Терминал 2.1, вики 1:1, проекты сессий,
настройки ×3 (glassmorphism), роли моделей в чате, Фаза A (бюджеты, аудит,
rate limits, состояния ключей), Фаза B (импорт vault 2.0, heatmap, re-auth gate),
security-аудит: md()/inl() escape-first с экранированием кавычек (attribute-injection
XSS в img/a/wikilink-алиасах закрыт), safe_path канонический (realpath+normcase,
null bytes, backslash, all-dot компоненты, абсолютные пути), security hardening:
strict absolute/UNC/drive path rejection в safe_path (lstrip-конверсия убрана),
commonpath-граница vault (vault ≠ vault-backup), canonical-проверка родителя при
записи (symlink наружу отклоняется), единый safe_path во всех файловых endpoints
(включая importer), строгий data:image allowlist в inl() (svg+xml запрещён),
Фаза C (ночной digest, soft delete trash/ с TTL 30 дней, prompt injection
«данные ≠ инструкции»), ui_smoke 152/152.
`mock_llm: true` — модели пока заглушки (переключает автор при наличии ключей).

## 3. Дорожная карта

### Фаза 6 (план работ — порядок согласован с автором)

| # | Подфаза | Состав | Основные файлы | Статус |
|---|---------|--------|----------------|--------|
| 6-S/S2 | проекты сессий | проекты, страница проекта, общая инструкция | app.js, server.py | ✅ |
| 6-T/T2 | Терминал 2.1 | md-превью, Ctrl+F, рецепты, undo-дифф, drag&drop | terminal.py, app.js | ✅ |
| 6-W | вики 1:1 | полный шаблон Иванопедии, backlinks | modules.py, app.js | ✅ |
| 6-O..O4 | онбординг 2.0 + «Ритуал запуска» | слайдер, живое ядро, ачивки, финал с конфетти, пара моделей | app.js, monica.css, server.py | ✅ |
| **6-N** | **Настройки 2.0 — наполнение** (приоритет автора) | 1) дата создания аккаунта в Профиле; 2) «Экспорт данных» — zip (vault + профиль + история) через /api/profile/export; 3) индикатор силы пароля при смене; 4) цветовые статусы ключей (проверен/ошибка/не проверялся); 5) показ и правка пары light/smart моделей из онбординга; 6) fix: .cs-menu (absolute из style.css) в настройках → static | server.py (+export, +custom-models, +keys_status), app.js (setTab*), monica.css | ✅ |
| **6-M** | **Медиа: фото/видео/файлы/голос** | app/media.py: Groq Whisper (голос), ffmpeg-кадры (видео→vision), save_attachment (до 5 файлов ≤10МБ в attachments/); /api/chat(+stream) принимают files[]; композер: активация слотов, превью вложений; ключ groq в KEY_SERVICES | app/media.py (новый), server.py, providers.py, app.js, onboarding.py | ✅ |
| 6-F | хвосты 5-I | кликабельность @sozrelyy (e4d33e9 + smoke-проверка), отступы — закрыто попутными фиксами | app.js, monica.css | ✅ |
| **A** | **Фундамент безопасности и бюджетов** (новый этап) | budget.py (дневной лимит, lock-резерв, сброс в полночь), audit.py (audit.jsonl, маскирование), rate limits, ping()-состояния, UI «Лимиты и использование» | app/budget.py (новый), app/audit.py (новый), providers.py, server.py, app.js, monica.css | ✅ |
| 7 | боевой режим | инструменты готовы: tools/import_vault.py (импорт .md с --enqueue/--overwrite), tools/cleanup_users.py (чистка тестеров, dry-run + --delete). Живые модели: переключение mock_llm=false — делает автор при наличии ключей (smoke рассчитан на mock) | config.json, tools/ | ◐ |
| 8 | деплой | инструменты готовы (8-prep): tools/backup.py (zip data/ + ротация --keep), HTTPS-опция в server.py (config.json → "ssl": {"cert","key"}), start_monica.bat + install_autostart.bat (schtasks). Осталось за автором: хостинг/проброс порта, сертификат | tools/, server.py, config.example.json | ◐ |
| 9 | полировка по фидбеку беты | темы, i18n, экспорт заметок, аналитика-визуализации | — | ☐ |

### Фаза 5 — «улучшения и Терминал 2.0» (завершена)

| # | Подфаза | Состав | Основные файлы |
|---|---------|--------|----------------|
| A | ✅ | hatnote-баннер, минус приветствие, typewriter 2.0 | monica.css, app.js |
| B | ✅ | реестр моделей, смерть ox alpha, переключатели | onboarding.py, server.py, providers.py, app.js |
| C | ✅ | hero-приветствие + анимация шагов онбординга (slide+fade, глифы, prefers-reduced-motion) | app.js (renderW), monica.css |
| D | ✅ | Настройки ×3: Профиль (смена юзернейма/аватара/пароля), Модели и ключи (+проверка живости `max_tokens=1`), Модули; формы вместо prompt() | auth.py (+change_username/change_password/drop_all_sessions), server.py (+4 маршрута), providers.py (+ping), app.js (tabSet → setTab*) |
| E | ✅ | Терминал 2.0: дерево vault / чат⇄md-редактор / лог изменений + undo; op `edit_note`; бэкап перед записью (молчаливая перезапись устранена); history.jsonl, лимит 500 | terminal.py, app/history.py (новый), server.py (+tree/read/write/history/undo), app.js (tabTerm → 3 панели) |
| F | ✅ | Личная вики: очередь wiki_queue.json, генератор статей через smart-модель по шаблону Иванопедии, страницы статей, анимация `.wk-open` | modules.py, server.py (+/api/wiki/articles,regen), app.js (tabWiki), monica.css |

| G | ✅ | Полировка-1: term-wide каркас, воздух у VAULT, focus-расширение чат-поля, VS Code-редактор (шапка-таб, точка несохранённых, gutter, caret/selection), .tab-in переходы, вики 3 зоны (sidebar/статья/инфобокс) | app.js, monica.css, ui_smoke.js |

**Фаза 5 завершена полностью (A–G).** Фаза 6 в работе: 6-S/6-S2 (проекты) ✅,
6-T/6-T2 (Терминал 2.1) ✅, 6-W (вики 1:1) ✅, 6-O/O2/O3 (онбординг 2.0 +
«Ритуал запуска»: слайдер, ачивки, живое ядро — концепт в
plans/6-O3-living-core-concept.md) ✅. Остались: 6-M (медиа), 6-F (хвосты 5-I),
живые модели (mock_llm=false), перенос vault, деплой.

После каждой подфазы: расширить `tools/ui_smoke.js`, прогнать, коммит, протокол.

### Фаза 6 — «боевой режим»
1. **Живые модели**: `mock_llm: false`, проверить реальные ключи GLM/OpenRouter/Luna
   на всех маршрутах (чат, стриминг, терминал, вики-генератор).
2. **Перенос личного vault Ивана** первым боевым пользователем (скрипт импорта .md в `data/users/<id>/vault`).
3. **Приглашение друзей-тестеров**: чистка тестовых аккаунтов, свежие сессии.

### Фаза 7 — деплой
1. Хостинг/VPS или домашний сервер с пробросом порта; HTTPS (reverse proxy + сертификат).
2. Вынос секретов: `config.json` не в git (уже так), бэкапы `data/`.
3. Автозапуск сервера (служба/планировщик), мониторинг падений.

### Фаза 8 — полировка после фидбека беты
- Загрузка изображений/файлов в композер (слоты-заглушки уже стоят).
- Темы оформления (светлая опция), i18n интерфейса (ru/ua/en уже собираются в онбординге).
- История чатов-сессий, экспорт заметок, расширенная аналитика-визуализации.

## 4. Известные риски / долги
- `terminal.execute()` перезаписывает файлы без бэкапа — чинится в подфазе E до внедрения undo.
- Состояние вкладки терминала теряется при переключении вкладок (#m-body перерисовывается) — кэш в JS-переменной в E.
- Смена юзернейма должна инвалидировать сессию; смена пароля — все сессии (D).
- Старый экземпляр сервера может висеть на порту 8900 — всегда убивать перед прогоном smoke.
