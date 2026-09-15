# -*- coding: utf-8 -*-
"""Configuración del módulo: proveedor LLM, API key y parámetros del cliente.

Fuentes, de mayor a menor prioridad:
  1. ir.config_parameter  (clave 'ai_data_chat.<nombre>')  -> configurable en caliente
  2. variable de entorno del proceso Odoo
  3. fichero .env junto a este módulo (parser propio, sin dependencias)
  4. valor por defecto (o preset del proveedor)

El cliente LLM habla la API de OpenAI Chat Completions. Varios proveedores la
exponen, así que cambiar de uno a otro es solo cambiar `provider` (o
`base_url` + `model`) en el .env:

  provider = gemini      -> Google AI Studio (endpoint compatible con OpenAI)
  provider = openrouter  -> OpenRouter
  provider = openai      -> OpenAI
"""
import logging
import os
import threading

_logger = logging.getLogger(__name__)

_MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENV_PATH = os.path.join(_MODULE_DIR, ".env")

# Presets por proveedor: base_url y modelo por defecto.
PROVIDER_PRESETS = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-3.6-flash",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "anthropic/claude-3.5-haiku",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
}
_DEFAULT_PROVIDER = "gemini"

# nombre lógico -> (claves .env/entorno aceptadas, clave ir.config_parameter, defecto)
# La primera clave de entorno que exista gana; se prueban en orden.
_KEYS = {
    "provider": (("AI_DATA_CHAT_PROVIDER",), "ai_data_chat.provider", _DEFAULT_PROVIDER),
    "api_key": (
        ("AI_DATA_CHAT_API_KEY", "OPENROUTER_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"),
        "ai_data_chat.api_key",
        "",
    ),
    "base_url": (("AI_DATA_CHAT_BASE_URL",), "ai_data_chat.base_url", ""),
    "model": (("AI_DATA_CHAT_MODEL",), "ai_data_chat.model", ""),
    "responder_mode": (("AI_DATA_CHAT_RESPONDER_MODE",), "ai_data_chat.responder_mode", "manual"),
    "max_tool_iterations": (("AI_DATA_CHAT_MAX_TOOL_ITERATIONS",), "ai_data_chat.max_tool_iterations", "4"),
    "http_timeout": (("AI_DATA_CHAT_HTTP_TIMEOUT",), "ai_data_chat.http_timeout", "60"),
    "http_referer": (("AI_DATA_CHAT_HTTP_REFERER",), "ai_data_chat.http_referer", "http://localhost"),
    "app_title": (("AI_DATA_CHAT_APP_TITLE",), "ai_data_chat.app_title", "Odoo AI Data Chat"),
}

_dotenv_cache = None
_dotenv_lock = threading.Lock()


def _load_dotenv():
    """Lee el .env una vez por proceso. Formato: líneas CLAVE=valor, admite
    comentarios con '#' y comillas opcionales alrededor del valor."""
    global _dotenv_cache
    if _dotenv_cache is not None:
        return _dotenv_cache
    with _dotenv_lock:
        if _dotenv_cache is not None:
            return _dotenv_cache
        data = {}
        try:
            with open(_ENV_PATH, "r", encoding="utf-8") as fh:
                for raw in fh:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key:
                        data[key] = value
        except FileNotFoundError:
            _logger.info("ai_data_chat: no hay .env en %s (se usarán entorno/parámetros)", _ENV_PATH)
        except OSError as err:
            _logger.warning("ai_data_chat: no se pudo leer .env: %s", err)
        _dotenv_cache = data
        return data


def reload_dotenv():
    """Fuerza releer el .env (útil tras editarlo sin reiniciar Odoo)."""
    global _dotenv_cache
    with _dotenv_lock:
        _dotenv_cache = None


def _raw(name, env=None):
    env_keys, param_key, default = _KEYS[name]
    if env is not None:
        value = env["ir.config_parameter"].sudo().get_param(param_key)
        if value:
            return value
    dotenv = _load_dotenv()
    for env_key in env_keys:
        if os.environ.get(env_key):
            return os.environ[env_key]
        if dotenv.get(env_key):
            return dotenv[env_key]
    return default


def get(name, env=None):
    """Valor de configuración como string."""
    if name not in _KEYS:
        raise KeyError("Clave de configuración desconocida: %r" % (name,))
    return _raw(name, env=env)


def get_int(name, env=None):
    try:
        return int(get(name, env=env))
    except (TypeError, ValueError):
        return int(_KEYS[name][2])


def _preset(provider):
    return PROVIDER_PRESETS.get(provider, PROVIDER_PRESETS["openrouter"])


def llm_config(env=None):
    """Bloque de configuración listo para el cliente LLM."""
    provider = (get("provider", env=env) or _DEFAULT_PROVIDER).strip().lower()
    preset = _preset(provider)
    return {
        "provider": provider,
        "api_key": get("api_key", env=env),
        "base_url": get("base_url", env=env) or preset["base_url"],
        "model": get("model", env=env) or preset["model"],
        "http_timeout": get_int("http_timeout", env=env),
        "max_tool_iterations": get_int("max_tool_iterations", env=env),
        "http_referer": get("http_referer", env=env),
        "app_title": get("app_title", env=env),
    }


def is_configured(env=None):
    """True si hay API key -> el modo 'llm' puede funcionar."""
    return bool(get("api_key", env=env))
