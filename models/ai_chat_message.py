# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AiChatMessage(models.Model):
    _name = "ai.chat.message"
    _description = "Mensaje de conversación con el asistente de datos"
    _order = "id asc"

    session_id = fields.Many2one(
        "ai.chat.session", string="Conversación",
        required=True, ondelete="cascade", index=True,
    )
    role = fields.Selection(
        [
            ("user", "Usuario"),
            ("assistant", "Asistente"),
            ("tool", "Herramienta"),
            ("system", "Sistema"),
        ],
        string="Rol", required=True, default="user",
    )
    content = fields.Text(string="Contenido")

    # Trazabilidad de la herramienta ejecutada (si la hubo).
    tool_name = fields.Char(string="Herramienta")
    tool_params = fields.Json(string="Parámetros")
    tool_result = fields.Json(string="Resultado")
    # Acción de escritura propuesta en este mensaje (si la hubo).
    action_id = fields.Many2one(
        "ai.chat.action", string="Acción propuesta", ondelete="set null",
    )
    status = fields.Selection(
        [("ok", "OK"), ("error", "Error")],
        string="Estado", default="ok",
    )

    # Uso de tokens / modelo (lo rellenará la capa LLM más adelante).
    model_used = fields.Char(string="Modelo IA")
    tokens_input = fields.Integer(string="Tokens entrada", default=0)
    tokens_output = fields.Integer(string="Tokens salida", default=0)

    @api.depends("role", "content")
    def _compute_display_name(self):
        for msg in self:
            preview = (msg.content or "").strip().replace("\n", " ")
            if len(preview) > 60:
                preview = preview[:57] + "..."
            msg.display_name = "[%s] %s" % (msg.role, preview or "(sin texto)")

    def to_dict(self):
        """Serialización para el controller / la UI."""
        self.ensure_one()
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content or "",
            "status": self.status,
            "tool_name": self.tool_name or None,
            "tool_result": self.tool_result or None,
            "action": self.action_id.action_data() if self.action_id else None,
            "create_date": fields.Datetime.to_string(self.create_date),
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
        }
