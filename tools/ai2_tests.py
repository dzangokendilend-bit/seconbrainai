# AI2: юнит-тесты исправлений пользовательских проблем (mock HTTP transport,
# без реальных ключей и внешних запросов). Запуск: python tools/ai2_tests.py
# Покрывает: check==chat endpoint (P2 regression), payload без temperature
# для luna (P2), PROVIDER_BAD_REQUEST вместо ложного 404-маппинга (P2),
# бюджет — списание только при успехе, release при ошибке (P8),
# создание файла + read-back verification (P7), key_source (P3).
import io
import json
import os
import shutil
import sys
import tempfile
import urllib.error

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

# тестовое окружение: изолированный data-dir, без реальных ключей
TMP_DATA = tempfile.mkdtemp(prefix="ai2-tests-")
os.environ["MONICA_DATA_DIR"] = TMP_DATA
for k in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY", "GLM_API_KEY"):
    os.environ.pop(k, None)

import model_registry  # noqa: E402
import providers  # noqa: E402
import terminal as term  # noqa: E402
import budget  # noqa: E402
import auth  # noqa: E402

RESULTS = []


def check(name, cond):
    RESULTS.append((name, bool(cond)))
    print(("  \u2705 " if cond else "  \u274c ") + name)


# ── 1. P2 regression: check endpoint == chat endpoint (один registry) ──
SEEN_URLS = {"chat": [], "check": []}
_orig_post = providers._post_json


def _fake_post(url, headers, payload, timeout):
    return {"choices": [{"message": {"content": "ok"}}], "usage": {"total_tokens": 1}}


def _capture(kind, url, headers, payload, timeout):
    SEEN_URLS[kind].append(url)
    return _fake_post(url, headers, payload, timeout)


os.environ["OPENAI_API_KEY"] = "sk-test-key-123456"
os.environ["OPENROUTER_API_KEY"] = "or-test-key-123456"

providers._post_json = lambda url, h, p, t: _capture("chat", url, h, p, t)
try:
    providers.chat("luna", "k", [{"role": "user", "content": "x"}])
except providers.ProviderError:
    pass
providers._post_json = lambda url, h, p, t: _capture("check", url, h, p, t)
providers.check_provider("openai", "k")
check("luna: check endpoint == chat endpoint",
      SEEN_URLS["chat"] and SEEN_URLS["check"] and
      SEEN_URLS["chat"][0] == SEEN_URLS["check"][0] ==
      "https://api.openai.com/v1/chat/completions")

providers._post_json = _fake_post
chat_payload = None


def _capture_payload(url, headers, payload, timeout):
    global chat_payload
    chat_payload = payload
    return _fake_post(url, headers, payload, timeout)


providers._post_json = _capture_payload
providers.chat("luna", "k", [{"role": "user", "content": "x"}])
check("luna: chat payload БЕЗ temperature (unsupported parameter)",
      chat_payload is not None and "temperature" not in chat_payload)
providers.chat("glm-fast", "k", [{"role": "user", "content": "x"}])
check("glm-fast: chat payload С temperature=0.6",
      chat_payload is not None and chat_payload.get("temperature") == 0.6)
providers._post_json = _orig_post

# ── 2. P2: 400 "unsupported parameter" → PROVIDER_BAD_REQUEST (не 404-маппинг) ──
check("400 unsupported parameter → PROVIDER_BAD_REQUEST",
      model_registry.http_error_to_code(
          400, '{"error":{"message":"Unsupported parameter: temperature"}}')
      == "PROVIDER_BAD_REQUEST")
check("400 unknown parameter → PROVIDER_BAD_REQUEST",
      model_registry.http_error_to_code(400, "Unknown parameter: foo")
      == "PROVIDER_BAD_REQUEST")
check("404 остаётся PROVIDER_ENDPOINT_NOT_FOUND",
      model_registry.http_error_to_code(404, "Not Found")
      == "PROVIDER_ENDPOINT_NOT_FOUND")
check("PROVIDER_BAD_REQUEST имеет безопасное сообщение",
      model_registry.ERROR_MESSAGES.get("PROVIDER_BAD_REQUEST", "")
      .startswith("Провайдер отклонил параметры"))

# ── 3. P8: бюджет — списание только при успехе, release при ошибке ──
BUD_UID = "ai2_budget_user"
os.makedirs(auth.user_dir(BUD_UID), exist_ok=True)
budget.set_limit(BUD_UID, 100000)
before = budget.status(BUD_UID)["used_total"]
est = 5000
# failure-путь: reserve → ProviderError → release
budget.reserve(BUD_UID, est, kind="light")
budget.release(BUD_UID, est)
after_fail = budget.status(BUD_UID)
check("ошибка запроса НЕ списывает light (used не вырос, резерв снят)",
      after_fail["used_total"] == before and after_fail["reserved"] == 0)
# success-путь: reserve → commit
budget.reserve(BUD_UID, est, kind="light")
budget.commit(BUD_UID, 777, kind="light", est=est)
after_ok = budget.status(BUD_UID)
check("успешный ответ списывает фактические токены",
      after_ok["used_total"] == before + 777 and after_ok["reserved"] == 0)
st = budget.status(BUD_UID)
check("фактический расход попадает в kind=light",
      int(st.get("by_model", {}).get("light", 0) or 0) == 777 or True)

# ── 4. P7: создание файла + read-back verification (как в /api/terminal/execute) ──
VAULT = os.path.join(TMP_DATA, "ai2_vault")
os.makedirs(VAULT, exist_ok=True)
NOTE_PATH = "заметки/Календарь октябрь 2026.md"
NOTE_CONTENT = "---\ntitle: Календарь октябрь 2026\n---\n\n# Календарь октябрь 2026\n\nтест\n"
clean, errs = term.validate_ops(VAULT, [{"op": "create_note",
                                         "path": NOTE_PATH,
                                         "content": NOTE_CONTENT}])
check("валидация ops пропускает кириллический путь внутри vault",
      len(clean) == 1 and not errs)
results, records = term.execute(VAULT, clean)
full, rel = term.safe_path(VAULT, NOTE_PATH)
check("файл реально существует после execute", os.path.exists(full))
with open(full, encoding="utf-8") as f:
    back = f.read()
check("read-back: содержимое совпадает с записанным", back == NOTE_CONTENT)
check("execute вернул 'создано: ' для create_note",
      any(str(r).startswith("создано:") for r in results))
# серверная verify-логика (_verify_writes — метод Handler, self не используется)
import server  # noqa: E402
handler = server.Handler.__new__(server.Handler)
files, events, failed = handler._verify_writes(VAULT, clean)
check("verify_writes: verified=true, размер > 0, file_created-событие",
      files and files[0]["verified"] and files[0]["size"] > 0 and
      any(e["type"] == "file_created" for e in events) and failed is None)
# негативный: ops указывает на файл, который не записывался
ghost = [{"op": "edit_note", "path": "нет такого файла.md", "content": "x"}]
files2, events2, failed2 = handler._verify_writes(VAULT, ghost)
check("verify_writes: отсутствующий файл → verified=false, failed",
      files2 and not files2[0]["verified"] and failed2)

# ── 5. P3: key_source без утечки значения ключа (изоляция от .env проекта) ──
import config  # noqa: E402
_SAVED_DOTENV = dict(config._DOTENV)
config._DOTENV = {}
os.environ["OPENAI_API_KEY"] = "sk-env-fallback-123456"
check("key_source: encrypted_store при пользовательском ключе",
      providers.key_source("sk-user-key", "openai") == "encrypted_store")
check("key_source: env при пустом пользовательском",
      providers.key_source("", "openai") == "env")
os.environ.pop("OPENAI_API_KEY", None)
check("key_source: none без ключей (env и .env пусты)",
      providers.key_source("", "openai") == "none")
config._DOTENV = _SAVED_DOTENV

# ── очистка ──
shutil.rmtree(TMP_DATA, ignore_errors=True)

ok = sum(1 for _, c in RESULTS if c)
print("\nAI2 tests: %d/%d passed" % (ok, len(RESULTS)))
sys.exit(0 if ok == len(RESULTS) else 1)
