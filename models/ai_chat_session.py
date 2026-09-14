# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class AiChatSession(models.Model):
    _name = "ai.chat.session"
    _description = "Conversación con el asistente de datos"
    _order = "last_message_date desc, id desc"

    name = fields.Char(string="Título", required=True, default=lambda s: s._default_name())
    user_id = fields.Many2one(
        "res.users", string="Usuario", required=True, index=True,
        default=lambda s: s.env.user,
    )
    state = fields.Selection(
        [("open", "Abierta"), ("closed", "Cerrada")],
        string="Estado", default="open", required=True,
    )
    message_ids = fields.One2many("ai.chat.message", "session_id", string="Mensajes")
    message_count = fields.Integer(
        string="Nº mensajes", compute="_compute_message_count",
    )
    last_message_date = fields.Datetime(
        string="Último mensaje", compute="_compute_last_message_date",
        store=True, compute_sudo=False,
    )

    @api.model
    def _default_name(self):
        return _("Consulta del %s") % fields.Datetime.context_timestamp(
            self, fields.Datetime.now()
        ).strftime("%d/%m/%Y %H:%M")

    @api.depends("message_ids")
    def _compute_message_count(self):
        for session in self:
            session.message_count = len(session.message_ids)

    @api.depends("message_ids", "message_ids.create_date")
    def _compute_last_message_date(self):
        for session in self:
            session.last_message_date = max(
                session.message_ids.mapped("create_date"),
                default=session.create_date,
            )

    # --- API de conversación ------------------------------------------
    def post_message(self, role, content=None, **values):
        """Crea un mensaje en la conversación y lo devuelve."""
        self.ensure_one()
        return self.env["ai.chat.message"].create({
            "session_id": self.id,
            "role": role,
            "content": content,
            **values,
        })

    def ask(self, user_text):
        """Punto de entrada: registra la pregunta, obtiene respuesta y la registra.

        Devuelve dict con los mensajes nuevos y metadatos de la conversación.
        """
        self.ensure_one()
        user_text = (user_text or "").strip()
        user_msg = self.post_message("user", content=user_text)

        answer = self.env["ai.chat.responder"].respond(self, user_text)
        assistant_msg = self.post_message(
            "assistant",
            content=answer.get("content"),
            status=answer.get("status", "ok"),
            tool_name=answer.get("tool_name"),
            tool_params=answer.get("tool_params"),
            tool_result=answer.get("tool_result"),
            model_used=answer.get("model_used"),
            tokens_input=answer.get("tokens_input", 0),
            tokens_output=answer.get("tokens_output", 0),
        )
        return {
            "session_id": self.id,
            "state": self.state,
            "messages": [user_msg.to_dict(), assistant_msg.to_dict()],
        }

    def message_data(self):
        self.ensure_one()
        return {
            "session_id": self.id,
            "name": self.name,
            "state": self.state,
            "messages": [m.to_dict() for m in self.message_ids],
        }

    def action_close(self):
        self.write({"state": "closed"})

    def action_reopen(self):
        self.write({"state": "open"})
