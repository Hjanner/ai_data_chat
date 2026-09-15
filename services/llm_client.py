# -*- coding: utf-8 -*-
"""Cliente LLM (API OpenAI Chat Completions) + bucle de tool-calling contra la
capa de datos. Funciona con cualquier proveedor que exponga esa API: Gemini
(Google AI Studio), OpenRouter, OpenAI… El proveedor se elige en config.

Flujo de `answer()`:
  1. system prompt + historial + pregunta  ->  POST /chat/completions con `tools`
  2. si el modelo pide tool_calls -> se ejecutan con tool_dispatcher.run_tool
     y se devuelven como mensajes role='tool'
  3. se repite hasta `max_tool_iterations` o hasta que el modelo responde texto
  4. se devuelve el texto final + traza (tool calls, tokens, modelo)

La red se aísla en `_Transport` para poder inyectar un doble en los tests
(este módulo no depende de `requests`: usa urllib).
"""
import json
import logging
import urllib.error
import urllib.request

from . import config
from . import llm_prompt
from .tool_dispatcher import run_tool

_logger = logging.getLogger(__name__)

# Cuántas filas de cada resultado de herramienta se devuelven al modelo
# (el resto se resume) para no disparar el coste de tokens.
_ROWS_TO_MODEL = 20


class LLMError(Exception):
    pass


# Alias retro-compatible mientras quede código/documentación con el nombre viejo.
OpenRouterError = LLMError


class _Transport:
    """Envoltura HTTP mínima. Sustituible en tests."""

    def post_json(self, url, payload, headers, timeout):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", "replace")
            raise LLMError("HTTP %s del proveedor LLM: %s" % (err.code, body[:500]))
        except urllib.error.URLError as err:
            raise LLMError("No se pudo contactar con el proveedor LLM: %s" % err.reason)
        except json.JSONDecodeError as err:
            raise LLMError("Respuesta no-JSON del proveedor LLM: %s" % err)


class LLMClient:
    def __init__(self, env, transport=None):
        self.env = env
        self.cfg = config.llm_config(env)
        self.transport = transport or _Transport()

    # --- API pública --------------------------------------------------
    def answer(self, user_text, history=None):
        """Devuelve dict: content, tool_trace(list), model_used, tokens_input,
        tokens_output, status."""
        if not self.cfg["api_key"]:
            raise LLMError(
                "Falta la API key (pon AI_DATA_CHAT_API_KEY en el .env del módulo "
                "o el parámetro de sistema 'ai_data_chat.api_key')."
            )

        messages = [{"role": "system", "content": llm_prompt.build_system_prompt(self.env)}]
        for item in history or []:
            role = item.get("role")
            if role in ("user", "assistant") and item.get("content"):
                messages.append({"role": role, "content": item["content"]})
        messages.append({"role": "user", "content": user_text})

        tools = llm_prompt.tool_schemas(self.env)
        tool_trace = []
        tokens_in = tokens_out = 0
        model_used = self.cfg["model"]

        for _iteration in range(self.cfg["max_tool_iterations"] + 1):
            data = self._chat(messages, tools)
            usage = data.get("usage") or {}
            tokens_in += usage.get("prompt_tokens", 0) or 0
            tokens_out += usage.get("completion_tokens", 0) or 0
            model_used = data.get("model") or model_used

            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            tool_calls = msg.get("tool_calls") or []

            if not tool_calls:
                return {
                    "status": "ok",
                    "content": (msg.get("content") or "").strip()
                    or "(el modelo no devolvió texto)",
                    "tool_trace": tool_trace,
                    "model_used": model_used,
                    "tokens_input": tokens_in,
                    "tokens_output": tokens_out,
                }

            # Registrar la petición del modelo y ejecutar cada herramienta.
            messages.append({
                "role": "assistant",
                "content": msg.get("content") or "",
                "tool_calls": tool_calls,
            })
            for call in tool_calls:
                fn = (call.get("function") or {})
                name = fn.get("name")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = run_tool(self.env, name, args)
                tool_trace.append({"tool": name, "params": args, "result": result})
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "name": name,
                    "content": json.dumps(self._shrink(result), ensure_ascii=False),
                })

        # Se agotaron las iteraciones. En vez de rendirse, se pide una última
        # respuesta SIN herramientas: el modelo ya tiene los resultados en el
        # historial, así que puede redactar. Esto evita perder una propuesta de
        # escritura que sí llegó a prepararse por quedarse sin turnos.
        content = ""
        try:
            data = self._chat(messages, tools=None)
            usage = data.get("usage") or {}
            tokens_in += usage.get("prompt_tokens", 0) or 0
            tokens_out += usage.get("completion_tokens", 0) or 0
            msg = ((data.get("choices") or [{}])[0].get("message") or {})
            content = (msg.get("content") or "").strip()
        except LLMError as err:
            _logger.warning("Cierre sin herramientas también falló: %s", err)

        if content:
            return {
                "status": "ok",
                "content": content,
                "tool_trace": tool_trace,
                "model_used": model_used,
                "tokens_input": tokens_in,
                "tokens_output": tokens_out,
            }
        return {
            "status": "error",
            "content": (
                "No he podido completar la consulta en %d pasos. "
                "Reformula la pregunta de forma más concreta."
                % self.cfg["max_tool_iterations"]
            ),
            "tool_trace": tool_trace,
            "model_used": model_used,
            "tokens_input": tokens_in,
            "tokens_output": tokens_out,
        }

    # --- Interno -----------------------------------------------------
    def _chat(self, messages, tools=None):
        headers = {
            "Authorization": "Bearer %s" % self.cfg["api_key"],
            "Content-Type": "application/json",
        }
        # Cabeceras de atribución específicas de OpenRouter (otros las ignoran).
        if "openrouter" in self.cfg["base_url"]:
            headers["HTTP-Referer"] = self.cfg["http_referer"]
            headers["X-Title"] = self.cfg["app_title"]

        payload = {
            "model": self.cfg["model"],
            "messages": messages,
            "temperature": 0,
        }
        # Sin `tools` el modelo no puede pedir más herramientas: se usa para
        # forzar la redacción final cuando se agotan las iteraciones.
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        url = self.cfg["base_url"].rstrip("/") + "/chat/completions"
        data = self.transport.post_json(url, payload, headers, self.cfg["http_timeout"])
        if "error" in data and not data.get("choices"):
            raise LLMError(str(data["error"]))
        return data

    @staticmethod
    def _shrink(result):
        """Limita el nº de filas que se devuelven al modelo."""
        if not isinstance(result, dict) or not result.get("ok"):
            return result
        rows = result.get("rows") or []
        if len(rows) <= _ROWS_TO_MODEL:
            return result
        clone = dict(result)
        clone["rows"] = rows[:_ROWS_TO_MODEL]
        clone["rows_omitted"] = len(rows) - _ROWS_TO_MODEL
        return clone


# Alias retro-compatible.
OpenRouterClient = LLMClient
