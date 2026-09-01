# AI1: юнит-тесты провайдеров (mock HTTP transport, без реальных ключей).
# Запуск: python tools/ai1_tests.py  → печатает PASS/FAIL и exit code.
# Покрывает: точные URL трёх провайдеров, изоляцию ключей, API_KEY_MISSING,
# GLM_API_KEY не участвует, MODEL_NOT_ALLOWED, error-маппинг (401/403/404/429/
# timeout), отсутствие секретов в ошибках, mock_llm без внешних запросов,
# Whisper не через chat endpoint, /api/ai/check изоляция провайдеров.
import io
import json
import os
import sys
import urllib.error

# Windows-консоль (cp1251): безопасный вывод эмодзи/кириллицы
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

# тестовое окружение: без реальных ключей
os.environ.setdefault("MONICA_DATA_DIR", os.path.join(ROOT, "data"))
for k in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY", "GLM_API_KEY"):
    os.environ.pop(k, None)

import model_registry  # noqa: E402
import providers  # noqa: E402

RESULTS = []


def check(name, cond):
    RESULTS.append((name, bool(cond)))
    print(("  \u2705 " if cond else "  \u274c ") + name)


# ── 1. точные URL (без /v1/v1 и двойного /chat/completions) ──
check("URL openrouter = https://openrouter.ai/api/v1/chat/completions",
      model_registry.build_url("glm-fast") == "https://openrouter.ai/api/v1/chat/completions")
check("URL openai = https://api.openai.com/v1/chat/completions",
      model_registry.build_url("luna") == "https://api.openai.com/v1/chat/completions")
check("URL groq = https://api.groq.com/openai/v1/audio/transcriptions",
      model_registry.build_url("groq-whisper") == "https://api.groq.com/openai/v1/audio/transcriptions")
check("нет /v1/v1 ни в одном URL",
      all("/v1/v1" not in model_registry.build_url(k) for k in model_registry.MODELS))
check("нет двойного /chat/completions",
      all(model_registry.build_url(k).count("/chat/completions") <= 1
          for k in model_registry.MODELS))

# ── 2. изоляция ключей по провайдерам ──
os.environ["OPENROUTER_API_KEY"] = "or-test-key-123456"
os.environ["OPENAI_API_KEY"] = "sk-test-key-123456"
os.environ["GROQ_API_KEY"] = "gsk-test-key-123456"
check("openrouter ← только OPENROUTER_API_KEY",
      model_registry.provider_env_key("openrouter") == "or-test-key-123456")
check("openai ← только OPENAI_API_KEY",
      model_registry.provider_env_key("openai") == "sk-test-key-123456")
check("groq ← только GROQ_API_KEY",
      model_registry.provider_env_key("groq") == "gsk-test-key-123456")
os.environ.pop("GLM_API_KEY", None)
check("GLM_API_KEY не участвует в routing (нет такого провайдера)",
      "glm" not in model_registry.PROVIDERS)

# ── 3. отсутствующий ключ → API_KEY_MISSING ──
os.environ.pop("OPENROUTER_API_KEY", None)
try:
    providers.chat("glm-fast", None, [{"role": "user", "content": "x"}])
    check("нет ключа → ProviderError", False)
except providers.ProviderError as e:
    check("нет ключа → API_KEY_MISSING", e.code == "API_KEY_MISSING")
os.environ["OPENROUTER_API_KEY"] = "or-test-key-123456"

# ── 4. MODEL_NOT_ALLOWED: произвольный model id от клиента ──
try:
    providers.chat("openrouter/auto", "k", [{"role": "user", "content": "x"}])
    check("legacy model id → ProviderError", False)
except providers.ProviderError as e:
    check("legacy model id → MODEL_NOT_ALLOWED", e.code == "MODEL_NOT_ALLOWED")
try:
    providers.chat("groq-whisper", "k", [{"role": "user", "content": "x"}])
    check("whisper не через chat endpoint", False)
except providers.ProviderError as e:
    check("whisper не через chat endpoint (MODEL_NOT_ALLOWED)",
          e.code == "MODEL_NOT_ALLOWED")

# ── 5. mock_llm=true: внешних запросов нет ──
calls = []


def _spy(url, headers, payload, timeout):
    calls.append(url)
    raise AssertionError("внешний запрос при mock_llm")


_orig_post = providers._post_json
providers._post_json = _spy
providers.config.CFG["mock_llm"] = True
out = providers.chat("glm-fast", None, [{"role": "user", "content": "привет"}])
check("mock_llm=true: внешних запросов нет", not calls and "mock" in out)
providers.config.CFG["mock_llm"] = False
providers._post_json = _orig_post

# ── 6. error-маппинг (mock transport) ──
class _FakeHTTPError(urllib.error.HTTPError):
    def __init__(self, code, body=""):
        super().__init__("http://mock", code, "err", hdrs=None,
                         fp=io.BytesIO(body.encode()))


import urllib.request  # noqa: E402

_URLOPEN = urllib.request.urlopen


def _with_status(code, body=""):
    """Патчит urlopen: реальный _post_json обрабатывает HTTPError сам."""
    def fake_urlopen(req, timeout=None):
        raise _FakeHTTPError(code, body)
    return fake_urlopen


cases = [
    (401, "", "API_KEY_UNAUTHORIZED"),
    (403, "", "MODEL_ACCESS_DENIED"),
    (404, '{"error":{"message":"No endpoints found for model"}}', "MODEL_NOT_FOUND"),
    (404, "", "PROVIDER_ENDPOINT_NOT_FOUND"),
    (429, "", "PROVIDER_RATE_LIMITED"),
    (402, '{"error":{"message":"insufficient_quota"}}', "PROVIDER_BILLING_REQUIRED"),
]
for code, body, expected in cases:
    urllib.request.urlopen = _with_status(code, body)
    try:
        providers.chat("glm-fast", "k", [{"role": "user", "content": "x"}])
        check("HTTP %d → %s" % (code, expected), False)
    except providers.ProviderError as e:
        check("HTTP %d → %s" % (code, expected), e.code == expected)
urllib.request.urlopen = _URLOPEN

import socket  # noqa: E402


def _timeout_urlopen(req, timeout=None):
    raise socket.timeout()


urllib.request.urlopen = _timeout_urlopen
try:
    providers.chat("glm-fast", "k", [{"role": "user", "content": "x"}])
    check("timeout → PROVIDER_TIMEOUT", False)
except providers.ProviderError as e:
    check("timeout → PROVIDER_TIMEOUT", e.code == "PROVIDER_TIMEOUT")
urllib.request.urlopen = _URLOPEN

# ── 6. ошибка не содержит ключ/Authorization/prompt ──
SECRET = "sk-super-secret-value-9876543210"
urllib.request.urlopen = _with_status(401, '{"error":{"message":"bad key"}}')
try:
    providers.chat("luna", SECRET, [{"role": "user", "content": "секретный prompt"}])
except providers.ProviderError as e:
    blob = e.message + str(e.args)
    check("ошибка не содержит ключ", SECRET not in blob)
    check("ошибка не содержит Authorization", "Bearer" not in blob)
    check("ошибка не содержит prompt", "секретный prompt" not in blob)
    check("ошибка не содержит сырой HTTP-текст", "HTTP Error" not in blob)
urllib.request.urlopen = _URLOPEN

# ── 7. safe_error: {code, message} без секретов ──
se = model_registry.safe_error("API_KEY_MISSING")
check("safe_error = {code, message}",
      set(se.keys()) == {"code", "message"} and
      se["message"] == model_registry.ERROR_MESSAGES["API_KEY_MISSING"])

# ── 8. check_provider: изоляция провайдеров (неудача одного не ломает другие) ──
def _fail_urlopen(req, timeout=None):
    raise _FakeHTTPError(401, "")


class _FakeResp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ok_urlopen(req, timeout=None):
    return _FakeResp(json.dumps(
        {"choices": [{"message": {"content": "ok"}}]}).encode())


urllib.request.urlopen = _fail_urlopen
res_or = providers.check_provider("openrouter", "k1")
urllib.request.urlopen = _ok_urlopen
res_oa = providers.check_provider("openai", "k2")
urllib.request.urlopen = _URLOPEN
check("ai/check: openrouter упал (invalid), openai ok — изолированно",
      res_or["status"] == "invalid" and res_oa["status"] == "ok")
check("ai/check: без ключа → missing, без запроса",
      providers.check_provider("groq", "")["status"] == "missing")

# ── 9. resolve_key: пользовательский ключ приоритетнее env ──
check("resolve_key: пользовательский ключ главнее env",
      providers.resolve_key("user-key", "openrouter") == "user-key")
check("resolve_key: без пользовательского → env своего провайдера",
      providers.resolve_key("", "openai") == "sk-test-key-123456")

# ── 10. registry: ровно 3 модели, whisper kind=transcription ──
check("registry: ровно 3 модели", len(model_registry.MODELS) == 3)
check("groq-whisper kind=transcription (не chat)",
      model_registry.get("groq-whisper")["kind"] == "transcription")
check("CHAT_KEYS = glm-fast, luna",
      model_registry.CHAT_KEYS == ("glm-fast", "luna"))
check("default chat = glm-fast", model_registry.DEFAULT_CHAT == "glm-fast")

# ── 11. ai_log: whitelist полей, секреты не пишутся ──
import ai_log  # noqa: E402
os.environ["MONICA_AI_DEBUG"] = "true"
os.environ["MONICA_DATA_DIR"] = os.path.join(ROOT, "data")
ai_log.log_event(provider="openrouter", model="glm-fast", endpoint="https://x",
                 http_status=200, latency_ms=5, api_key=SECRET,
                 Authorization="Bearer " + SECRET)
p = os.path.join(ROOT, "data", "audit", "ai_debug.jsonl")
if os.path.exists(p):
    with open(p, encoding="utf-8") as f:
        last = f.read().strip().splitlines()[-1]
    check("ai_log: ключ не попал в лог", SECRET not in last)
    check("ai_log: Authorization не попал в лог", "Bearer" not in last)
else:
    check("ai_log: файл создан", False)
os.environ.pop("MONICA_AI_DEBUG", None)

# ── итог ──
fails = [n for n, ok in RESULTS if not ok]
print("\nAI1 unit: %d/%d passed" % (len(RESULTS) - len(fails), len(RESULTS)))
sys.exit(1 if fails else 0)
