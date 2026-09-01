# Deploy Моники (P0 — подготовка)

## Локальный запуск (Windows)

```bat
rem 1. один раз: скопировать .env.example в .env и заполнить секреты
copy .env.example .env

rem 2. запуск
start_monica.bat
rem или: python app\server.py
```

Сервер слушает `127.0.0.1:8900` (переопределяется `MONICA_HOST`/`PORT`).
При старте печатается безопасный startup report (`[OK]/[WARN]`, без секретов).

## Docker Compose

```bat
docker compose up -d --build
curl http://127.0.0.1:8900/health   rem {"status": "ok"}
```

- Секреты берутся из `.env` (env_file), данные живут в volume `monica_data`
  (`MONICA_DATA_DIR=/data` внутри контейнера).
- В контейнере приложение слушает `0.0.0.0` (env `MONICA_HOST`), наружу —
  только опубликованный порт.
- Образ: `python:3.12-slim`, non-root пользователь `monica`, только stdlib.
- `.dockerignore` исключает `.env`, `config.json`, `data/`, `backups/`,
  `node_modules`, `__pycache__`, `tmp/`, `.git`, `docs/` — секреты и данные
  не попадают в образ.

## Что настроить для публичного deploy (VPS)

1. **Секреты**: заполнить `.env` на сервере
   (`MONICA_MACHINE_SECRET`, `TELEGRAM_BOT_TOKEN`, …). Никогда не в git.
2. **HTTPS**: только через reverse-proxy (Caddy/nginx) с валидным
   сертификатом. Приложение само по себе HTTP — TLS терминирует прокси.
3. **Telegram-транспорт**: ровно один.
   - *Webhook (production)*: `PUBLIC_APP_URL=https://домен`,
     `TELEGRAM_WEBHOOK_SECRET=<случайная строка>`; зарегистрировать webhook:
     `https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://домен/api/telegram/webhook/<СЕКРЕТ>`.
   - *Polling*: только для разработки (`TELEGRAM_DEV_POLLING=1`).
   - Polling и webhook одновременно — запрещено (`tools/doctor.py` ловит).
4. **Данные**: `MONICA_DATA_DIR` на постоянный путь (или Docker volume).
5. **Проверка**: `python tools/doctor.py` — 0 ERROR перед открытием наружу.

## Фоновые задачи после deploy

- **Telegram polling** — daemon-поток, только при явном dev-флаге.
- **Telegram webhook** — обрабатывается в запросах, отдельного потока нет.
- **Digest-планировщик** — один глобальный daemon-поток (проверка раз в 60с,
  запуск по prefs.digest_enabled/digest_time; токены LLM не тратятся, пока
  prefs.digest_llm_enabled=false).
- **Trash sweep** — TTL-очистка корзин раз в час + при старте.

## Health endpoint

`GET /health` → `{"status": "ok"}` — без ключей, путей, данных пользователей
и конфигурации. Используется Docker healthcheck и мониторингом.
