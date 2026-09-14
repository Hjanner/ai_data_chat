# -*- coding: utf-8 -*-
from odoo import fields, http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request


class AiDataChatController(http.Controller):
    """Endpoints JSON para la UI de chat. Todo con auth='user'.

    Las conversaciones se resuelven siempre para el usuario en sesión; las
    reglas de registro impiden ver las de otros usuarios.
    """

    def _get_session(self, session_id):
        session = request.env["ai.chat.session"].browse(int(session_id))
        if not session.exists():
            raise MissingError("Conversación inexistente.")
        session.check_access_rights("read")
        session.check_access_rule("read")
        return session

    @http.route("/ai_data_chat/sessions", type="json", auth="user")
    def list_sessions(self):
        sessions = request.env["ai.chat.session"].search([])
        return {
            "sessions": [
                {
                    "id": s.id,
                    "name": s.name,
                    "state": s.state,
                    "message_count": s.message_count,
                    "last_message_date": fields.Datetime.to_string(s.last_message_date)
                    if s.last_message_date else None,
                }
                for s in sessions
            ]
        }

    @http.route("/ai_data_chat/session/new", type="json", auth="user")
    def new_session(self, name=None):
        vals = {}
        if name:
            vals["name"] = name
        session = request.env["ai.chat.session"].create(vals)
        return session.message_data()

    @http.route("/ai_data_chat/session/<int:session_id>/messages",
                type="json", auth="user")
    def session_messages(self, session_id):
        try:
            session = self._get_session(session_id)
        except (AccessError, MissingError) as err:
            return {"error": str(err)}
        return session.message_data()

    @http.route("/ai_data_chat/session/<int:session_id>/ask",
                type="json", auth="user")
    def session_ask(self, session_id, message=""):
        try:
            session = self._get_session(session_id)
        except (AccessError, MissingError) as err:
            return {"error": str(err)}
        if not (message or "").strip():
            return {"error": "Mensaje vacío."}
        return session.ask(message)

    @http.route("/ai_data_chat/session/<int:session_id>/close",
                type="json", auth="user")
    def session_close(self, session_id):
        try:
            session = self._get_session(session_id)
        except (AccessError, MissingError) as err:
            return {"error": str(err)}
        session.action_close()
        return {"session_id": session.id, "state": session.state}
