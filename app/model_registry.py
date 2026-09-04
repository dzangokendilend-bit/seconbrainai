import os
from typing import Dict, Any, List

DEFAULT_PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini"],
        "default_model": "gpt-4o-mini"
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-coder"],
        "default_model": "deepseek-chat"
    },
    "groq": {
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "models": ["llama-3.3-70b-versatile", "mixtral-8x7b-32768"],
        "default_model": "llama-3.3-70b-versatile"
    },
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "models": ["openai/gpt-4o-mini", "anthropic/claude-3.5-haiku", "meta-llama/llama-3.3-70b-instruct"],
        "default_model": "openai/gpt-4o-mini"
    },
    "ollama": {
        "name": "Ollama (Local)",
        "base_url": "http://localhost:11434/v1",
        "models": ["llama3", "mistral", "qwen2.5"],
        "default_model": "llama3"
    }
}

def get_available_models(user_keys: Dict[str, str]) -> List[Dict[str, Any]]:
    """Возвращает список моделей, для которых настроены ключи или доступен локальный сервер."""
    available = []
    for prov_id, prov_data in DEFAULT_PROVIDERS.items():
        has_key = bool(user_keys.get(prov_id) or os.getenv(f"{prov_id.upper()}_API_KEY"))
        if prov_id == "ollama" or has_key:
            for model_id in prov_data["models"]:
                available.append({
                    "id": f"{prov_id}:{model_id}",
                    "name": f"{prov_data['name']} - {model_id}",
                    "provider": prov_id,
                    "model": model_id
                })
    return available
