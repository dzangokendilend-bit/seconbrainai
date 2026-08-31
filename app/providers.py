# LLM-провайдеры Моники: OpenAI-совместимый протокол, ключи пользователей.
# Сервисы: glm (терминал/быстрые), smart (OpenRouter, глубокие модели), luna (чат/бот).
# Базовые URL и id моделей — в config.json (секция providers).
# mock_llm=true в config.json — тестовый режим без реальных ключей.
import json
import urllib.request

import config


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


def chat(service, api_key, model, messages, timeout=120, with_usage=False):
    """Фаза A: with_usage=True → (content, usage_dict|None) — usage нужен
    бюджету (budget.commit). Без with_usage поведение прежнее."""
    if config.CFG.get("mock_llm"):
        content = mock_chat(messages)
        usage = {"total_tokens": _estimate_tokens(messages, content)}
        return (content, usage) if with_usage else content
    prov = (config.CFG.get("providers") or {}).get(service) or {}
    base = (prov.get("base_url") or "").rstrip("/")
    # Фаза 5-B: модель пользователя главнее дефолта из конфига
    model_id = model or prov.get("model")
    if not base or not api_key:
        raise RuntimeError("провайдер " + service + " не настроен: нет base_url или ключа")
    payload = json.dumps({"model": model_id, "messages": messages,
                          "temperature": 0.6}).encode("utf-8")
    req = urllib.request.Request(base + "/chat/completions", data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key})
    if service == "smart":
        req.add_header("HTTP-Referer", "http://localhost")
        req.add_header("X-Title", "Monica")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
    return (content, usage) if with_usage else content


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


def ping(service, api_key, timeout=20):
    """Фаза A: расширенные состояния ключа — минимальный запрос max_tokens=1.
    Возвращает {status: ok|quota|permissions|unavailable|invalid|network, detail}.
    Разбор HTTP: 401→invalid, 403→permissions, 429→quota, 5xx/timeout→unavailable."""
    if config.CFG.get("mock_llm"):
        return {"status": "ok", "detail": "mock-режим: ключ не проверялся"}
    prov = (config.CFG.get("providers") or {}).get(service) or {}
    base = (prov.get("base_url") or "").rstrip("/")
    model_id = prov.get("model")
    if not base or not model_id:
        return {"status": "unavailable", "detail": "провайдер не настроен"}
    payload = json.dumps({"model": model_id, "messages": [{"role": "user", "content": "ping"}],
                          "max_tokens": 1}).encode("utf-8")
    req = urllib.request.Request(base + "/chat/completions", data=payload, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + api_key})
    if service == "smart":
        req.add_header("HTTP-Referer", "http://localhost")
        req.add_header("X-Title", "Monica")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            json.loads(r.read().decode("utf-8"))
        return {"status": "ok", "detail": "ключ работает"}
    except Exception as e:
        msg = str(e)
        try:
            body = e.read().decode("utf-8", "replace")[:300]
            err = json.loads(body).get("error")
            msg = err.get("message", body) if isinstance(err, dict) else body
        except Exception:
            pass
        msg = str(msg)[:200]
        code = getattr(e, "code", None)
        if code == 401:
            return {"status": "invalid", "detail": msg or "ключ неверен"}
        if code == 403:
            return {"status": "permissions", "detail": msg or "доступ запрещён"}
        if code == 429:
            return {"status": "quota", "detail": msg or "квота провайдера исчерпана"}
        if code is not None and 500 <= code < 600:
            return {"status": "unavailable", "detail": msg or "сервис недоступен"}
        if code is not None:
            return {"status": "invalid", "detail": msg}
        # без HTTP-кода — сеть/таймаут
        return {"status": "network", "detail": msg or "сеть недоступна"}



def chat_stream(service, api_key, model, messages, timeout=120, usage_out=None):
    """То же, что chat(), но выдаёт ответ кусочками (генератор).
    Mock стримит по словам с паузой, реальный провайдер — SSE-дельты.
    Фаза A: usage_out (dict) наполняется usage.total_tokens из финального
    SSE-чанка (или оценкой в mock) — для budget.commit."""
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
    prov = (config.CFG.get("providers") or {}).get(service) or {}
    base = (prov.get("base_url") or "").rstrip("/")
    # Фаза 5-B: модель пользователя главнее дефолта из конфига
    model_id = model or prov.get("model")
    if not base or not api_key:
        raise RuntimeError("провайдер " + service + " не настроен")
    payload = json.dumps({"model": model_id, "messages": messages,
                          "temperature": 0.6, "stream": True}).encode("utf-8")
    req = urllib.request.Request(base + "/chat/completions", data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key})
    if service == "smart":
        req.add_header("HTTP-Referer", "http://localhost")
        req.add_header("X-Title", "Monica")
    with urllib.request.urlopen(req, timeout=timeout) as r:
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
