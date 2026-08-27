# LLM-провайдеры Моники: OpenAI-совместимый протокол, ключи пользователей.
# Сервисы: glm (терминал/быстрые), smart (OpenRouter, глубокие модели), luna (чат/бот).
# Базовые URL и id моделей — в config.json (секция providers).
# mock_llm=true в config.json — тестовый режим без реальных ключей.
import json
import urllib.request

import config


def chat(service, api_key, model, messages, timeout=120):
    if config.CFG.get("mock_llm"):
        return mock_chat(messages)
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
    return data["choices"][0]["message"]["content"]


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
    """Фаза 5-D: проверка живости ключа — минимальный запрос max_tokens=1.
    Возвращает (ok, сообщение)."""
    if config.CFG.get("mock_llm"):
        return True, "mock-режим: ключ не проверялся"
    prov = (config.CFG.get("providers") or {}).get(service) or {}
    base = (prov.get("base_url") or "").rstrip("/")
    model_id = prov.get("model")
    if not base or not model_id:
        return False, "провайдер не настроен"
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
        return True, "ключ работает"
    except Exception as e:
        msg = str(e)
        try:
            body = e.read().decode("utf-8", "replace")[:300]
            err = json.loads(body).get("error")
            msg = err.get("message", body) if isinstance(err, dict) else body
        except Exception:
            pass
        return False, msg



def chat_stream(service, api_key, model, messages, timeout=120):
    """То же, что chat(), но выдаёт ответ кусочками (генератор).
    Mock стримит по словам с паузой, реальный провайдер — SSE-дельты."""
    import time as _t
    if config.CFG.get("mock_llm"):
        text = mock_chat(messages)
        try:
            text = json.loads(text).get("reply", text)
        except Exception:
            pass
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
                delta = json.loads(chunk)["choices"][0]["delta"].get("content")
            except Exception:
                continue
            if delta:
                yield delta
