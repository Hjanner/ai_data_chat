# -*- coding: utf-8 -*-
"""Acciones de escritura propuestas por el asistente y pendientes de confirmar.

Este modelo es la frontera entre "el asistente ha entendido lo que quieres"
y "se ha escrito en la base de datos". Un registro en estado `draft` no ha
tocado nada todavía.

Quien confirma es SIEMPRE una persona, pulsando en la ficha del chat: el
modelo de lenguaje no dispone de ninguna herramienta que llame a
`action_confirm`, y un "sí" escrito en el chat tampoco la dispara.

La escritura se hace con el `env` del usuario (sin sudo), así que las ACL y
reglas de registro de Odoo se aplican igual que en cualquier formulario.
"""
import logging

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from ..services import write_catalog as wcat
from ..services import write_tools

_logger = logging.getLogger(__name__)


class AiChatAction(models.Model):
    _name = "ai.chat.action"
    _description = "Acción de escritura propuesta por el asistente"
    _order = "id desc"

    session_id = fields.Many2one(
        "ai.chat.session", string="Conversación", ondelete="cascade", index=True,
    )
    user_id = fields.Many2one(
        "res.users", string="Usuario", required=True, index=True,
        default=lambda s: s.env.user,
    )
    operation = fields.Selection(
        [("create", "Creación"), ("update", "Modificación")],
        string="Operación", required=True,
    )
    model_name = fields.Char(string="Modelo", required=True)
    record_id = fields.Integer(string="Registro afectado")

    values = fields.Json(string="Valores propuestos")
    before_values = fields.Json(string="Valores anteriores")
    preview = fields.Json(string="Ficha de confirmación")

    state = fields.Selection(
        [
            ("draft", "Pendiente de confirmar"),
            ("done", "Aplicada"),
            ("discarded", "Descartada"),
            ("expired", "Caducada"),
            ("reverted", "Deshecha"),
        ],
        string="Estado", default="draft", required=True, index=True,
    )
    result_id = fields.Integer(string="Registro creado/modificado")
    result_name = fields.Char(string="Resultado")
    error = fields.Char(string="Error")

    # --- Creación del borrador ------------------------------------------
    @api.model
    def create_draft(self, operation, model_name, values, preview,
                     record_id=None, before_values=None):
        """Llamado por `services/write_tools`. La conversación llega por
        contexto porque las herramientas solo reciben `env`."""
        return self.create({
            "session_id": self.env.context.get("ai_chat_session_id") or False,
            "operation": operation,
            "model_name": model_name,
            "record_id": record_id or 0,
            "values": values,
            "before_values": before_values or {},
            "preview": preview,
        })

    # --- Caducidad -------------------------------------------------------
    def _is_expired(self):
        self.ensure_one()
        if not self.create_date:
            return False
        age = fields.Datetime.now() - self.create_date
        return age.total_seconds() > wcat.DRAFT_EXPIRY_HOURS * 3600

    # --- Confirmar / descartar ------------------------------------------
    def action_confirm(self):
        """Escribe de verdad. Único punto del módulo que lo hace."""
        self.ensure_one()
        if self.user_id != self.env.user:
            raise AccessError(_("Esta acción pertenece a otro usuario."))
        if self.state != "draft":
            raise UserError(_("Esta acción ya no está pendiente (%s).") % self.state)
        if self._is_expired():
            self.state = "expired"
            raise UserError(_(
                "La propuesta ha caducado (más de %d horas). Vuelve a pedirla."
            ) % wcat.DRAFT_EXPIRY_HOURS)

        # Revalidar la lista blanca: el borrador pudo quedarse guardado
        # mientras el catálogo cambiaba.
        wcat.check_model(self.model_name, self.operation)
        vals = dict(self.values or {})
        if not vals:
            raise UserError(_("La propuesta no tiene valores que aplicar."))

        Model = self.env[self.model_name].sudo(False)
        try:
            if self.operation == "create":
                record = Model.create(vals)
            else:
                record = Model.browse(self.record_id)
                if not record.exists():
                    raise UserError(_("El registro ya no existe."))
                record.write(vals)
        except (AccessError, UserError, ValidationError) as err:
            # Se queda en borrador: la persona puede corregir y reintentar.
            self.error = str(err)
            _logger.info("ai.chat.action %s rechazada: %s", self.id, err)
            return {"ok": False, "error": str(err), "action": self.action_data()}
        except Exception as err:  # noqa: BLE001 - frontera: nada revienta el chat
            self.error = str(err)
            _logger.exception("Fallo aplicando ai.chat.action %s", self.id)
            return {"ok": False, "error": str(err), "action": self.action_data()}

        self.write({
            "state": "done",
            "error": False,
            "result_id": record.id,
            "result_name": record.display_name,
        })
        _logger.info(
            "ai.chat.action %s aplicada por %s: %s %s#%s",
            self.id, self.env.user.login, self.operation, self.model_name, record.id,
        )
        return {"ok": True, "action": self.action_data()}

    # --- Deshacer --------------------------------------------------------
    def _undo_blocker(self):
        """Por qué NO se puede deshacer esta acción, o None si sí se puede.

        Solo se deshacen modificaciones: para deshacer un alta habría que
        borrar el registro, que es destructivo y puede fallar si ya se usa en
        otro sitio. Eso se hace a mano en Odoo, con la cabeza fría.
        """
        self.ensure_one()
        if self.state != "done":
            return _("Solo se puede deshacer un cambio ya aplicado.")
        if self.operation != "update":
            return _(
                "Las altas no se deshacen desde aquí: para quitar el registro, "
                "archívalo o elimínalo en Odoo."
            )
        if not self.before_values:
            return _("No se guardó el valor anterior de este cambio.")
        record = self.env[self.model_name].sudo(False).browse(self.record_id)
        if not record.exists():
            return _("El registro ya no existe.")

        field = list(self.before_values)[0]
        try:
            spec = wcat.field_spec(self.model_name, field)
        except wcat.WriteCatalogError as err:
            return str(err)

        # Si alguien lo ha vuelto a cambiar por su cuenta, deshacer pisaría su
        # trabajo sin avisar. Mejor negarse y que lo mire una persona.
        current, current_txt = write_tools.read_value(record, field, spec)
        applied = write_tools.raw_from_vals(spec, (self.values or {}).get(field))
        if not write_tools.same_value(spec, current, applied):
            return _(
                "%(label)s ha cambiado desde entonces (ahora %(current)s). "
                "No lo piso: revísalo a mano."
            ) % {"label": spec["label"], "current": current_txt}
        return None

    def action_undo(self):
        """Devuelve el campo a su valor anterior. Solo para modificaciones."""
        self.ensure_one()
        if self.user_id != self.env.user:
            raise AccessError(_("Esta acción pertenece a otro usuario."))
        blocker = self._undo_blocker()
        if blocker:
            raise UserError(blocker)

        field = list(self.before_values)[0]
        spec = wcat.field_spec(self.model_name, field)
        record = self.env[self.model_name].sudo(False).browse(self.record_id)

        try:
            record.write({field: write_tools.to_write_value(spec, self.before_values[field])})
        except (AccessError, UserError, ValidationError) as err:
            self.error = str(err)
            return {"ok": False, "error": str(err), "action": self.action_data()}
        except Exception as err:  # noqa: BLE001 - frontera
            self.error = str(err)
            _logger.exception("Fallo deshaciendo ai.chat.action %s", self.id)
            return {"ok": False, "error": str(err), "action": self.action_data()}

        self.write({"state": "reverted", "error": False})
        _logger.info(
            "ai.chat.action %s deshecha por %s: %s#%s.%s",
            self.id, self.env.user.login, self.model_name, self.record_id, field,
        )
        return {"ok": True, "action": self.action_data()}

    def action_discard(self):
        self.ensure_one()
        if self.user_id != self.env.user:
            raise AccessError(_("Esta acción pertenece a otro usuario."))
        if self.state == "draft":
            self.state = "discarded"
        return {"ok": True, "action": self.action_data()}

    # --- Serialización para la UI ---------------------------------------
    def action_data(self):
        self.ensure_one()
        state = self.state
        if state == "draft" and self._is_expired():
            state = "expired"
        preview = dict(self.preview or {})
        blocker = self._undo_blocker() if self.state == "done" else None
        return {
            "id": self.id,
            "state": state,
            "can_undo": self.state == "done" and not blocker,
            "undo_blocked": blocker if self.operation == "update" else None,
            "operation": self.operation,
            "model": self.model_name,
            "confirm_label": _("Crear") if self.operation == "create" else _("Aplicar"),
            "preview": preview,
            "result_id": self.result_id or None,
            "result_name": self.result_name or None,
            "result_url": self._result_url(),
            "error": self.error or None,
        }

    def _result_url(self):
        self.ensure_one()
        if self.state not in ("done", "reverted") or not self.result_id:
            return None
        return "/web#id=%s&model=%s&view_type=form" % (self.result_id, self.model_name)

    # --- Resumen para el mensaje del chat tras confirmar -----------------
    def summary_message(self):
        self.ensure_one()
        label = (self.preview or {}).get("model_label") or self.model_name
        if self.state == "done" and self.operation == "create":
            return _("✅ %(label)s creado: **%(name)s** (id %(id)s).") % {
                "label": label, "name": self.result_name, "id": self.result_id,
            }
        if self.state == "done":
            changes = (self.preview or {}).get("changes") or [{}]
            change = changes[0]
            return _("✅ %(label)s actualizado: **%(name)s** — %(field)s %(before)s → %(after)s.") % {
                "label": label, "name": self.result_name,
                "field": change.get("label", ""),
                "before": change.get("before", ""), "after": change.get("after", ""),
            }
        if self.state == "reverted":
            changes = (self.preview or {}).get("changes") or [{}]
            change = changes[0]
            return _("↩️ Cambio deshecho: %(name)s vuelve a tener %(field)s %(before)s.") % {
                "name": self.result_name, "field": change.get("label", ""),
                "before": change.get("before", ""),
            }
        if self.state == "discarded":
            return _("Propuesta descartada. No se ha escrito nada.")
        if self.state == "expired":
            return _("La propuesta había caducado. No se ha escrito nada.")
        return _("La propuesta sigue pendiente.")
