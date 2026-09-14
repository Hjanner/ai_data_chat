# -*- coding: utf-8 -*-
"""El responder: dado un texto del usuario, produce la respuesta del asistente.

Conmutable por parámetro de sistema `ai_data_chat.responder_mode`:
  * "manual" (por defecto) - sin IA. Acepta:
        - un objeto JSON {"tool": ..., "params": ...}  -> ejecuta la capa de datos
        - cualquier otra cosa -> mensaje de ayuda
  * "llm" - usa el proveedor LLM configurado (Gemini, OpenRouter, OpenAI...).

El responder NUNCA lanza excepción: siempre devuelve un dict con al menos
`content` y `status`.
"""
import json
import logging

from odoo import api, models, _

from ..services.tool_dispatcher import run_tool
from ..services import config
from ..services.llm_client import LLMClient, LLMError

_logger = logging.getLogger(__name__)

PARAM_MODE = "ai_data_chat.responder_mode"
# Cuántos mensajes previos de la conversación se pasan al modelo como contexto.
_HISTORY_LIMIT = 10


class AiChatResponder(models.AbstractModel):
    _name = "ai.chat.responder"
    _description = "Generador de respuestas del asistente de datos"

    # --- Entrada pública --------------------------------------------------
    @api.model
    def respond(self, session, user_text):
        mode = config.get("responder_mode", env=self.env)
        if mode == "llm":
            return self._respond_llm(session, user_text)
        return self._respond_manual(session, user_text)

    # --- Modo manual ----------------------------------------------------
    @api.model
    def _respond_manual(self, session, user_text):
        text = (user_text or "").strip()

        if text.startswith("{"):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as err:
                return self._error(_("No he podido leer el JSON: %s") % err)
            if not isinstance(payload, dict) or "tool" not in payload:
                return self._error(_(
                    "Formato esperado: {\"tool\": \"aggregate|query_records\", "
                    "\"params\": {...}}"
                ))
            return self._run_and_format(payload.get("tool"), payload.get("params") or {})

        return self._help()

    # --- Modo LLM (Gemini / OpenRouter / OpenAI...) -------------------
    @api.model
    def _respond_llm(self, session, user_text):
        if not config.is_configured(env=self.env):
            return self._error(_(
                "El modo con IA está activo pero falta la API key. Pon "
                "AI_DATA_CHAT_API_KEY en el fichero .env del módulo o el "
                "parámetro de sistema 'ai_data_chat.api_key'."
            ))

        history = []
        if session:
            recent = session.message_ids.filtered(
                lambda m: m.role in ("user", "assistant") and m.content
            )[-_HISTORY_LIMIT:]
            history = [{"role": m.role, "content": m.content} for m in recent]

        try:
            client = LLMClient(self.env)
            result = client.answer(user_text, history=history)
        except LLMError as err:
            _logger.warning("El proveedor LLM falló: %s", err)
            return self._error(_("Error al consultar la IA: %s") % err)

        first_tool = (result.get("tool_trace") or [{}])[0]
        return {
            "status": result.get("status", "ok"),
            "content": result.get("content"),
            "tool_name": first_tool.get("tool"),
            "tool_params": first_tool.get("params"),
            "tool_result": {
                "trace": result.get("tool_trace") or [],
                **({} if not first_tool else first_tool.get("result", {})),
            },
            "model_used": result.get("model_used"),
            "tokens_input": result.get("tokens_input", 0),
            "tokens_output": result.get("tokens_output", 0),
        }

    # --- Ejecución + formato ------------------------------------------
    @api.model
    def _run_and_format(self, tool, params, title=None):
        result = run_tool(self.env, tool, params)
        if not result.get("ok"):
            return {
                "status": "error",
                "content": "⚠️ %s" % result.get("message", _("Error desconocido.")),
                "tool_name": tool,
                "tool_params": params,
                "tool_result": result,
            }
        return {
            "status": "ok",
            "content": self._summarize(result, title=title),
            "tool_name": tool,
            "tool_params": params,
            "tool_result": result,
        }

    @api.model
    def _summarize(self, result, title=None):
        """Resumen breve en español. La UI muestra la tabla completa aparte.

        (Cuando entre el LLM, esta redacción la hará el modelo.)
        """
        lines = []
        if title:
            lines.append(title)
        rows = result.get("rows") or []
        tool = result.get("tool")

        if not rows:
            lines.append(_("No hay datos para los criterios indicados."))
            return "\n".join(lines)

        labels = result.get("labels") or {}
        if tool == "aggregate":
            group_by = result.get("group_by") or []
            measures = result.get("measures") or []
            if not group_by:
                partes = ", ".join(
                    "%s = %s" % (labels.get(m, m), _fmt(rows[0].get(m), m)) for m in measures
                )
                lines.append(_("En el periodo consultado: %s.") % partes)
            else:
                first = rows[0]
                etiqueta = _row_label(first, group_by)
                metrica = measures[0] if measures else None
                if metrica:
                    lines.append(_(
                        "%(n)s grupos. En cabeza: %(label)s (%(metric)s = %(value)s)."
                    ) % {
                        "n": result.get("group_count", len(rows)),
                        "label": etiqueta,
                        "metric": labels.get(metrica, metrica),
                        "value": _fmt(first.get(metrica), metrica),
                    })
                else:
                    lines.append(_("%s grupos.") % result.get("group_count", len(rows)))
        else:  # query_records
            total = result.get("total_count", len(rows))
            if result.get("truncated"):
                lines.append(_("%(total)s registro(s); se muestran %(shown)s.") % {
                    "total": total, "shown": len(rows),
                })
            else:
                lines.append(_("%s registro(s).") % total)

        return "\n".join(lines)

    # --- Mensajes fijos --------------------------------------------------
    @api.model
    def _help(self):
        return {
            "status": "ok",
            "content": _(
                "Estoy en modo manual: no interpreto lenguaje natural, solo "
                "llamadas de herramienta en JSON. Por ejemplo:\n"
                '   {"tool": "query_records", "params": {"model": "sale.order", '
                '"fields": ["name", "amount_total"], "limit": 5}}\n\n'
                "Para preguntar con tus propias palabras, activa el modo IA: "
                "pon 'llm' en el parámetro de sistema 'ai_data_chat.responder_mode' "
                "(o AI_DATA_CHAT_RESPONDER_MODE en el .env del módulo)."
            ),
        }

    @api.model
    def _error(self, message):
        return {"status": "error", "content": message}


def _fmt(value, measure_key=None):
    """Formato coherente con el que usa la tabla en la UI:
    medidas de conteo -> entero; el resto de numeros -> 2 decimales."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    if measure_key and (measure_key == "__count" or measure_key.endswith("_count")):
        return "{:,}".format(int(value))
    if isinstance(value, float):
        return "{:,.2f}".format(value)
    return "{:,}".format(value)


def _row_label(row, group_by):
    parts = []
    for spec in group_by:
        val = row.get(spec)
        if isinstance(val, dict):
            parts.append(val.get("name") or str(val.get("id")))
        elif val is None:
            parts.append("—")
        else:
            parts.append(str(val))
    return " / ".join(parts)
