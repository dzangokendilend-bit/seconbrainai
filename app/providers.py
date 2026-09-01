# AI1: LLM-провайдеры Моники через MODEL_REGISTRY (app/model_registry.py).
# Ровно 3 модели: glm-fast (OpenRouter), luna (OpenAI), groq-whisper (Groq).
# URL строится из base_url + endpoint РОВНО ОДИН раз (registry.build_url).
# Ключи: ключ пользователя (keys.enc) → fallback env/.env. GLM_API_KEY —
# legacy, НЕ используется. mock_llm=true — тестовый режим без внешних запросов.
# Ошибки → безопасные коды (ProviderError.code), сырой HTTP-текст не показывается.
import json
import socket
import time
import urllib.error
import urllib.request

import ai_log
import config
import model_registry


class ProviderError(Exception):
    """Ошибка провайдера с БЕЗОПАСНЫМ кодом (model_registry.ERROR_MESSAGES).
    .code — код, .message — человеческое сообщение без секретов."""

    def __init__(self, code, message=None):
        super().__init__(message or model_registry.ERROR_MESSAGES.get(code, code))
        self.code = code
        self.message = message or model_registry.ERROR_MESSAGES.get(code, code)


def resolve_key(user_key, provider):
    """Ключ пользователя приоритетнее; иначе серверный fallback из env.
    Возвращает строку ключа или None. GLM_API_KEY не участвует."""
    k = (user_key or "").strip()
    if k:
        return k
    fb = model_registry.provider_env_key(provider)
    return fb or None


def key_source(user_key, provider):
    """AI2 (P3): откуда возьмётся ключ провайдера — без значения ключа.
    "encrypted_store" — ключ пользователя (keys.enc), "env" — серверный
    fallback из env/.env, "none" — ключа нет."""
    if (user_key or "").strip():
        return "encrypted_store"
    if model_registry.provider_env_key(provider):
        return "env"
    return "none"


def _estimate_tokens(messages, extra=""):
    """Mock-режим: оценка ~len(текст)/4 (Фаза A: учёт бюджета)."""
    n = len(extra)
    for m in messages:
        c = m.get("content") if isinstance(m, dict) else None
        if isinstance(c, str):
            n += len(c)
        elif isinstance(c, list):
            for part in c:
                if isinstance(part, dict) and part.get("type") == "text":
                    n += len(part.get("text", ""))
    return max(1, n // 4)


def mock_chat(messages):
    last = ""
    for m in reversed(messages):
        if m["role"] == "user":
            last = m["content"]
            break
    low = last.lower()
    ops = []
    if "создай" in low or "создать" in low or "заметк" in low:
        ops = [{"op": "create_note", "path": "заметки/из терминала.md",
                "content": "# Из терминала\n\nЗаметка создана терминалом Моники (mock-режим).\n"}]
        reply = ("Понял план: создать заметку «заметки/из терминала.md». "
                 "Проверь операции и подтверди выполнение.")
    elif "привет" in low or "hello" in low:
        reply = "[mock] Привет! Я Моника. Спроси что-нибудь или попроси создать заметку."
    else:
        reply = "[mock] Принял: «" + last[:200] + "». mock_llm=true в config.json — реальный режим включится с твоими ключами."
    return json.dumps({"reply": reply, "ops": ops}, ensure_ascii=False)


# ── transport (monkeypatchable в тестах; реальный вызов — urllib) ──

def _headers_for(provider, api_key):
    """Заголовки провайдера. Bearer — только ключ СВОЕГО провайдера."""
    h = {"Content-Type": "application/json",
         "Authorization": "Bearer " + api_key}
    if provider == "openrouter":
        h["HTTP-Referer"] = "http://localhost"
        h["X-Title"] = "Monica"
    return h


def _post_json(url, headers, payload, timeout):
    """POST JSON → parsed dict. HTTPError → ProviderError (безопасный код)."""
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers=headers)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
            ai_log.log_event(endpoint=url, http_status=r.status,
                             latency_ms=int((time.time() - t0) * 1000),
                             request_id=str(data.get("id") or "")[:64],
                             usage=data.get("usage") if isinstance(
                                 data.get("usage"), dict) else None)
            return data
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:400]
        except Exception:
            pass
        code = model_registry.http_error_to_code(e.code, body)
        ai_log.log_event(endpoint=url, http_status=e.code,
                         latency_ms=int((time.time() - t0) * 1000),
                         error_code=code)
        raise ProviderError(code)
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as e:
        code = ("PROVIDER_TIMEOUT" if isinstance(e, (socket.timeout, TimeoutError))
                else "PROVIDER_NETWORK_ERROR")
        ai_log.log_event(endpoint=url, error_code=code,
                         latency_ms=int((time.time() - t0) * 1000))
        raise ProviderError(code)


def _open_stream(url, headers, payload, timeout):
    """POST JSON со stream=true → response-объект для построчного чтения SSE."""
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers=headers)
    t0 = time.time()
    try:
        return urllib.request.urlopen(req, timeout=timeout), t0
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:400]
        except Exception:
            pass
        code = model_registry.http_error_to_code(e.code, body)
        ai_log.log_event(endpoint=url, http_status=e.code, error_code=code,
                         latency_ms=int((time.time() - t0) * 1000))
        raise ProviderError(code)
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as e:
        code = ("PROVIDER_TIMEOUT" if isinstance(e, (socket.timeout, TimeoutError))
                else "PROVIDER_NETWORK_ERROR")
        ai_log.log_event(endpoint=url, error_code=code,
                         latency_ms=int((time.time() - t0) * 1000))
        raise ProviderError(code)


def _chat_payload(m, messages, stream=False):
    """AI2: параметры payload — по ограничениям модели из реестра.
    no_temperature=True (gpt-5.6-luna) → temperature не отправляется
    (live-проверено: OpenAI отклоняет temperature для этой модели)."""
    p = {"model": m["model_id"], "messages": messages}
    if not m.get("no_temperature"):
        p["temperature"] = 0.6
    if stream:
        p["stream"] = True
    return p


def chat(model_key, api_key, messages, timeout=120, with_usage=False):
    """AI1: chat через MODEL_REGISTRY. model_key — только "glm-fast"/"luna".
    with_usage=True → (content, usage_dict|None) — usage нужен бюджету."""
    if config.CFG.get("mock_llm"):
        content = mock_chat(messages)
        usage = {"total_tokens": _estimate_tokens(messages, content)}
        return (content, usage) if with_usage else content
    m = model_registry.chat_model(model_key)
    if not m:
        raise ProviderError("MODEL_NOT_ALLOWED")
    if not api_key:
        raise ProviderError("API_KEY_MISSING")
    url = model_registry.build_url(model_key)
    data = _post_json(url, _headers_for(m["provider"], api_key),
                      _chat_payload(m, messages), timeout)
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ProviderError("PROVIDER_NETWORK_ERROR")
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
    return (content, usage) if with_usage else content


def chat_stream(model_key, api_key, messages, timeout=120, usage_out=None):
    """То же, что chat(), но SSE-дельты. Тот же URL и ключ (registry).
    usage_out наполняется usage.total_tokens из финального SSE-чанка."""
    import time as _t
    if config.CFG.get("mock_llm"):
        text = mock_chat(messages)
        try:
            text = json.loads(text).get("reply", text)
        except Exception:
            pass
        if usage_out is not None:
            usage_out["total_tokens"] = _estimate_tokens(messages, text)
        for word in text.split(" "):
            yield word + " "
            _t.sleep(0.025)
        return
    m = model_registry.chat_model(model_key)
    if not m:
        raise ProviderError("MODEL_NOT_ALLOWED")
    if not api_key:
        raise ProviderError("API_KEY_MISSING")
    url = model_registry.build_url(model_key)
    r, t0 = _open_stream(url, _headers_for(m["provider"], api_key),
                         _chat_payload(m, messages, stream=True),
                         timeout)
    with r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if chunk == "[DONE]":
                break
            try:
                parsed = json.loads(chunk)
            except Exception:
                continue
            if isinstance(parsed.get("usage"), dict) and usage_out is not None:
                usage_out.update(parsed["usage"])
            try:
                delta = parsed["choices"][0]["delta"].get("content")
            except Exception:
                continue
            if delta:
                yield delta
    ai_log.log_event(endpoint=url, http_status=getattr(r, "status", None),
                     latency_ms=int((_t.time() - t0) * 1000))


# ── проверки провайдеров (/api/ai/check, /api/keys?check, key-check) ──

def _check_chat(provider, api_key, timeout=20):
    """Минимальный ping chat-провайдера: max_tokens=1 «ping». Не тратит
    заметки/историю. OpenAI-моделям нужен max_completion_tokens.
    AI2: ТОТ ЖЕ model_registry/build_url, что и chat — endpoint не расходится;
    параметры — только добавки к ping (max_tokens), не противоречащие модели."""
    model_key = "glm-fast" if provider == "openrouter" else "luna"
    m = model_registry.get(model_key)
    payload = {"model": m["model_id"],
               "messages": [{"role": "user", "content": "ping"}]}
    if provider == "openai":
        # live-проверено: новым моделям OpenAI max_tokens не поддерживается
        payload["max_completion_tokens"] = 16
    else:
        payload["max_tokens"] = 1
    url = model_registry.build_url(model_key)
    try:
        _post_json(url, _headers_for(provider, api_key), payload, timeout)
        return {"status": "ok", "detail": "ключ работает", "code": None}
    except ProviderError as e:
        return {"status": _status_from_code(e.code), "detail": e.message,
                "code": e.code}


def _check_groq(api_key, timeout=20):
    """Groq: GET /models — минимальная проверка без расхода токенов."""
    m = model_registry.get("groq-whisper")
    url = m["base_url"].rstrip("/") + "/models"
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + api_key})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            json.loads(r.read().decode("utf-8"))
        ai_log.log_event(provider="groq", endpoint=url, http_status=r.status,
                         latency_ms=int((time.time() - t0) * 1000))
        return {"status": "ok", "detail": "ключ работает"}
    except urllib.error.HTTPError as e:
        code = model_registry.http_error_to_code(e.code)
        ai_log.log_event(provider="groq", endpoint=url, http_status=e.code,
                         error_code=code, latency_ms=int((time.time() - t0) * 1000))
        return {"status": _status_from_code(code),
                "detail": model_registry.ERROR_MESSAGES.get(code, code)}
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError):
        ai_log.log_event(provider="groq", endpoint=url,
                         error_code="PROVIDER_NETWORK_ERROR",
                         latency_ms=int((time.time() - t0) * 1000))
        return {"status": "network", "detail": "сеть недоступна"}


def _status_from_code(code):
    return {
        "API_KEY_MISSING": "missing",
        "API_KEY_UNAUTHORIZED": "invalid",
        "MODEL_ACCESS_DENIED": "permissions",
        "PROVIDER_ENDPOINT_NOT_FOUND": "not_found",
        "MODEL_NOT_FOUND": "not_found",
        "PROVIDER_RATE_LIMITED": "quota",
        "PROVIDER_BILLING_REQUIRED": "quota",
        "PROVIDER_TIMEOUT": "unavailable",
        "PROVIDER_NETWORK_ERROR": "network",
    }.get(code, "unavailable")


def check_provider(provider, api_key, timeout=20):
    """Проверка ОДНОГО провайдера коротким минимальным запросом.
    Возвращает {status, detail, code} — человеческие статусы + безопасный
    код ошибки, без ключей/headers."""
    if config.CFG.get("mock_llm"):
        return {"status": "ok", "detail": "mock-режим: ключ не проверялся",
                "code": None}
    if provider not in model_registry.PROVIDERS:
        return {"status": "missing", "detail": "неизвестный провайдер",
                "code": None}
    if not api_key:
        return {"status": "missing",
                "detail": model_registry.ERROR_MESSAGES["API_KEY_MISSING"],
                "code": "API_KEY_MISSING"}
    if provider == "groq":
        return _check_groq(api_key, timeout)
    return _check_chat(provider, api_key, timeout)


def ping(model_key, api_key, timeout=20):
    """Совместимость: ping chat-модели (glm-fast/luna) → {status, detail}."""
    m = model_registry.chat_model(model_key)
    if not m:
        return {"status": "not_found", "detail": "неизвестная модель"}
    return check_provider(m["provider"], api_key, timeout)
