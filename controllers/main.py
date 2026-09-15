# -*- coding: utf-8 -*-
from odoo import fields, http
from odoo.exceptions import AccessError, MissingError, UserError
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

    # --- Acciones de escritura ------------------------------------------
    # El modelo de lenguaje NO llega aquí: estos dos endpoints solo los
    # dispara la persona pulsando en la ficha de confirmación del chat.

    def _get_action(self, action_id):
        action = request.env["ai.chat.action"].browse(int(action_id))
        if not action.exists():
            raise MissingError("Propuesta inexistente.")
        action.check_access_rights("read")
        action.check_access_rule("read")
        return action

    def _action_response(self, action):
        """Cierra el ciclo: deja constancia en la conversación de lo ocurrido."""
        message = None
        if action.session_id:
            msg = action.session_id.post_message(
                "assistant",
                content=action.summary_message(),
                status="error" if action.error else "ok",
            )
            message = msg.to_dict()
        return {"action": action.action_data(), "message": message}

    @http.route("/ai_data_chat/action/<int:action_id>/confirm",
                type="json", auth="user")
    def action_confirm(self, action_id):
        try:
            action = self._get_action(action_id)
        except (AccessError, MissingError) as err:
            return {"error": str(err)}
        try:
            result = action.action_confirm()
        except (AccessError, UserError) as err:
            return {"error": str(err), "action": action.action_data()}
        if not result.get("ok"):
            return {"error": result.get("error"), "action": result.get("action")}
        return self._action_response(action)

    @http.route("/ai_data_chat/action/<int:action_id>/undo",
                type="json", auth="user")
    def action_undo(self, action_id):
        try:
            action = self._get_action(action_id)
        except (AccessError, MissingError) as err:
            return {"error": str(err)}
        try:
            result = action.action_undo()
        except (AccessError, UserError) as err:
            return {"error": str(err), "action": action.action_data()}
        if not result.get("ok"):
            return {"error": result.get("error"), "action": result.get("action")}
        return self._action_response(action)

    @http.route("/ai_data_chat/action/<int:action_id>/discard",
                type="json", auth="user")
    def action_discard(self, action_id):
        try:
            action = self._get_action(action_id)
        except (AccessError, MissingError) as err:
            return {"error": str(err)}
        try:
            action.action_discard()
        except AccessError as err:
            return {"error": str(err)}
        return self._action_response(action)
