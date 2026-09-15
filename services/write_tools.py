# -*- coding: utf-8 -*-
"""Herramientas de ESCRITURA. Proponen; no escriben.

Ninguna de estas funciones toca la base de datos de negocio. Lo unico que
hacen es validar la peticion contra `write_catalog`, resolver las
referencias (categoria, etiquetas...) y dejar un BORRADOR en `ai.chat.action`.

La escritura real ocurre en `ai.chat.action.action_confirm()`, que solo se
invoca desde el controlador cuando la persona pulsa el boton. El modelo de
lenguaje no tiene ninguna herramienta que confirme.

Contrato comun con las herramientas de lectura: `env` es el del usuario que
pregunta, nunca sudo, asi que las ACL y reglas de registro de Odoo se aplican
igual (tanto al proponer -- se comprueba el permiso de creacion -- como al
confirmar).
"""
import logging
import re

from odoo.exceptions import AccessError

from . import write_catalog as wcat
from .write_catalog import WriteCatalogError

_logger = logging.getLogger(__name__)

WRITE_GROUP = "ai_data_chat.group_ai_chat_write"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")
_NUMBER_RE = re.compile(r"[-+]?\d[\d.,]*")


# --- Puerta de seguridad --------------------------------------------------
def check_write_allowed(env):
    """El usuario debe pertenecer al grupo de escritura del asistente."""
    if not env.user.has_group(WRITE_GROUP):
        raise WriteCatalogError(
            "No tienes permiso para crear ni modificar datos desde el asistente. "
            "Hace falta el grupo 'Asistente de datos / Escritura'."
        )


def _check_odoo_access(env, model, operation):
    """Las ACL de Odoo mandan por encima del catalogo: se comprueban ya al
    proponer, para no pedirle 6 datos a la persona y fallar al final."""
    perm = "create" if operation == "create" else "write"
    try:
        env[model].check_access_rights(perm)
    except AccessError:
        raise WriteCatalogError(
            "Tu usuario no tiene permiso de %s sobre %s en Odoo. "
            "Habla con el administrador." % (
                "creación" if operation == "create" else "modificación",
                (wcat.WRITE_CATALOG.get(model) or {}).get("label", model),
            )
        )


# --- Normalizacion de valores --------------------------------------------
def _coerce_float(value, spec, field):
    """Acepta 12.5, '12,50', '$12.50', '12,50 dólares'."""
    if isinstance(value, bool):
        raise WriteCatalogError("%s debe ser un número." % spec["label"])
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        match = _NUMBER_RE.search(str(value or ""))
        if not match:
            raise WriteCatalogError(
                "No he entendido %r como valor de %s. Indica un número."
                % (value, spec["label"])
            )
        raw = match.group(0).replace(" ", "")
        if "," in raw and "." in raw:
            # El separador decimal es el que aparece mas a la derecha.
            if raw.rfind(",") > raw.rfind("."):
                raw = raw.replace(".", "").replace(",", ".")
            else:
                raw = raw.replace(",", "")
        elif "," in raw:
            raw = raw.replace(",", ".")
        try:
            number = float(raw)
        except ValueError:
            raise WriteCatalogError(
                "No he entendido %r como valor de %s." % (value, spec["label"])
            )
    minimum = spec.get("min")
    if minimum is not None and number < minimum:
        raise WriteCatalogError(
            "%s no puede ser menor que %s (recibido %s)." % (spec["label"], minimum, number)
        )
    return round(number, 2)


def _coerce_char(value, spec, field):
    text = str(value if value is not None else "").strip()
    if not text:
        raise WriteCatalogError("%s no puede estar vacío." % spec["label"])
    max_len = spec.get("max_len")
    if max_len and len(text) > max_len:
        raise WriteCatalogError(
            "%s es demasiado largo (máx. %d caracteres)." % (spec["label"], max_len)
        )
    return text


def _coerce_email(value, spec, field):
    text = _coerce_char(value, spec, field)
    if not _EMAIL_RE.match(text):
        raise WriteCatalogError(
            "%r no parece un correo electrónico válido." % (text,)
        )
    return text


def _coerce_role(value, spec, field):
    key = str(value or "").strip().lower()
    aliases = {
        "clientes": "cliente", "customer": "cliente", "farmacia": "cliente",
        "proveedores": "proveedor", "supplier": "proveedor", "vendor": "proveedor",
        "los dos": "ambos", "both": "ambos", "cliente y proveedor": "ambos",
    }
    key = aliases.get(key, key)
    if key not in wcat.PARTNER_ROLES:
        raise WriteCatalogError(
            "Rol no válido: %r. Debe ser uno de: %s."
            % (value, ", ".join(sorted(wcat.PARTNER_ROLES)))
        )
    return key


def _resolve_one(env, comodel, value, spec):
    """Nombre -> id de un registro EXISTENTE. Nunca crea nada."""
    Model = env[comodel].sudo(False)
    if isinstance(value, int) and not isinstance(value, bool):
        rec = Model.browse(value)
        if not rec.exists():
            raise WriteCatalogError("No existe ningún/a %s con id %s." % (spec["label"], value))
        return rec.id, rec.display_name

    text = str(value or "").strip()
    if not text:
        raise WriteCatalogError("%s no puede estar vacío." % spec["label"])

    found = Model.search([("name", "=ilike", text)], limit=wcat.MAX_CANDIDATES + 1)
    if not found:
        found = Model.search([("name", "ilike", text)], limit=wcat.MAX_CANDIDATES + 1)
    if not found:
        available = Model.search([], limit=wcat.MAX_CANDIDATES).mapped("display_name")
        raise WriteCatalogError(
            "No existe %s %r. No puedo crearla. Existentes: %s."
            % (spec["label"].lower(), text, ", ".join(available) or "ninguna")
        )
    if len(found) > 1:
        raise WriteCatalogError(
            "%r coincide con varias opciones de %s: %s. Concreta cuál."
            % (text, spec["label"].lower(), ", ".join(found.mapped("display_name")[:wcat.MAX_CANDIDATES]))
        )
    return found.id, found.display_name


def _coerce_many2one(env, value, spec, field):
    rec_id, name = _resolve_one(env, spec["comodel"], value, spec)
    return rec_id, name


def _coerce_many2many(env, value, spec, field):
    values = value if isinstance(value, (list, tuple)) else [value]
    ids, names = [], []
    for item in values:
        rec_id, name = _resolve_one(env, spec["comodel"], item, spec)
        if rec_id not in ids:
            ids.append(rec_id)
            names.append(name)
    return ids, ", ".join(names)


def normalize_values(env, model, operation, values):
    """Valida y normaliza. Devuelve (vals_orm, display) donde `display` es
    {campo: texto legible} para la ficha de confirmacion."""
    values = wcat.check_fields(model, operation, values)
    vals, display = {}, {}

    for field, raw in values.items():
        if raw is None or raw == "":
            continue
        spec = wcat.field_spec(model, field)
        kind = spec["type"]
        if kind == "float":
            value = _coerce_float(raw, spec, field)
            vals[field] = value
            display[field] = "{:,.2f}".format(value)
        elif kind == "email":
            value = _coerce_email(raw, spec, field)
            vals[field] = value
            display[field] = value
        elif kind in ("char", "text", "phone"):
            value = _coerce_char(raw, spec, field)
            vals[field] = value
            display[field] = value
        elif kind == "many2one":
            rec_id, name = _coerce_many2one(env, raw, spec, field)
            vals[field] = rec_id
            display[field] = name
        elif kind == "many2many":
            ids, names = _coerce_many2many(env, raw, spec, field)
            vals[field] = [(6, 0, ids)]
            display[field] = names
        elif kind == "role":
            role = _coerce_role(raw, spec, field)
            vals.update(wcat.PARTNER_ROLES[role])
            display[field] = role
        else:  # pragma: no cover - el catalogo no declara otros tipos
            raise WriteCatalogError("Tipo de campo no soportado: %r." % (kind,))

    return vals, display


# --- Lectura del valor actual (para el 'antes -> despues' y para deshacer) --
def read_value(record, field, spec):
    """Devuelve (valor JSON-able, texto legible) del valor que tiene ahora."""
    kind = spec["type"]
    value = record[field]
    if kind == "float":
        number = float(value or 0.0)
        return number, "{:,.2f}".format(number)
    if kind == "many2one":
        return (value.id or False), (value.display_name if value else "—")
    if kind == "many2many":
        return list(value.ids), (", ".join(value.mapped("display_name")) or "—")
    text = value or ""
    return (text or False), (str(text) if text else "—")


def raw_from_vals(spec, value):
    """Del valor listo para el ORM al valor comparable/guardable en Json.

    Los many2many viajan como [(6, 0, ids)]; para comparar y para guardar el
    'antes' interesa la lista de ids pelada.
    """
    if spec["type"] == "many2many":
        for command in value or []:
            if len(command) == 3 and command[0] == 6:
                return list(command[2])
        return []
    return value


def to_write_value(spec, raw):
    """El camino inverso: del valor guardado al valor que acepta write()."""
    if spec["type"] == "many2many":
        return [(6, 0, list(raw or []))]
    return raw if raw is not None else False


def same_value(spec, left, right):
    """Comparación tolerante con el tipo (float con céntimos, m2m sin orden)."""
    kind = spec["type"]
    if kind == "many2many":
        return sorted(left or []) == sorted(right or [])
    if kind == "float":
        return abs(float(left or 0.0) - float(right or 0.0)) < 0.005
    return (left or False) == (right or False)


def format_value(spec, raw, env=None):
    """Texto legible de un valor guardado (sin tener el registro delante)."""
    kind = spec["type"]
    if kind == "float":
        return "{:,.2f}".format(float(raw or 0.0))
    if kind in ("many2one", "many2many") and env is not None:
        ids = [raw] if kind == "many2one" else list(raw or [])
        ids = [i for i in ids if i]
        if not ids:
            return "—"
        records = env[spec["comodel"]].sudo(False).browse(ids).exists()
        return ", ".join(records.mapped("display_name")) or "—"
    return str(raw) if raw else "—"


# --- Deteccion de duplicados ---------------------------------------------
def _find_duplicates(env, model, op_cfg, values):
    domain = []
    for field in op_cfg.get("duplicate_on") or []:
        value = values.get(field)
        if isinstance(value, str) and value.strip():
            domain.append((field, "=ilike", value.strip()))
    if not domain:
        return []
    if len(domain) > 1:
        domain = ["|"] * (len(domain) - 1) + domain
    found = env[model].sudo(False).search(domain, limit=wcat.MAX_CANDIDATES)
    return [
        {"id": rec.id, "name": rec.display_name,
         "default_code": getattr(rec, "default_code", False) or None}
        for rec in found
    ]


# --- Herramientas expuestas al modelo ------------------------------------
def describe_create(env, model):
    """Que campos hacen falta para dar de alta algo. El modelo pregunta a
    partir de esto, en vez de inventarse el cuestionario."""
    check_write_allowed(env)
    spec = wcat.describe_fields(model, "create")
    return {"tool": "describe_create", "model": model, "spec": spec}


def propose_create(env, model, values=None):
    """Prepara un alta. NO escribe: deja un borrador pendiente de confirmar."""
    check_write_allowed(env)
    cfg, op_cfg = wcat.check_model(model, "create")
    _check_odoo_access(env, model, "create")
    values = values or {}

    # 1. Que falta de lo obligatorio.
    provided = {k: v for k, v in values.items() if v not in (None, "", [])}
    missing = [f for f in op_cfg["required"] if f not in provided]
    if missing:
        return {
            "tool": "propose_create",
            "model": model,
            "status": "incomplete",
            "missing": [
                {"field": f, "label": cfg["fields"][f]["label"], "help": cfg["fields"][f].get("help", "")}
                for f in missing
            ],
            "message": "Faltan datos obligatorios: %s. Pídeselos a la persona."
                       % ", ".join(cfg["fields"][f]["label"] for f in missing),
        }

    # 2. Validar y normalizar todo lo aportado.
    vals, display = normalize_values(env, model, "create", provided)

    # 3. Duplicados (avisan, no bloquean).
    duplicates = _find_duplicates(env, model, op_cfg, vals)

    # 4. Valores por defecto: se aplican, pero se ensenan.
    defaults = dict(op_cfg.get("defaults") or {})

    preview = {
        "operation": "create",
        "model": model,
        "model_label": cfg["label"],
        "title": "Crear %s: %s" % (cfg["label"].lower(), display.get("name", "(sin nombre)")),
        "lines": [
            {"label": cfg["fields"][f]["label"], "value": display[f]}
            for f in list(op_cfg["required"]) + list(op_cfg.get("optional") or [])
            if f in display
        ],
        "defaults": [
            (op_cfg.get("default_labels") or {}).get(k, "%s = %s" % (k, v))
            for k, v in defaults.items()
        ],
        "duplicates": duplicates,
    }

    action = env["ai.chat.action"].create_draft(
        operation="create", model_name=model, values=dict(vals, **defaults),
        preview=preview,
    )

    result = {
        "tool": "propose_create",
        "model": model,
        "status": "draft",
        "action_id": action.id,
        "preview": preview,
        "message": "Propuesta preparada. NO se ha escrito nada todavía: la "
                   "persona debe pulsar «Crear» en la ficha de confirmación.",
    }
    if duplicates:
        result["message"] = (
            "Atención: ya existe(n) %d registro(s) parecido(s) (%s). Avísale antes "
            "de que confirme."
            % (len(duplicates), ", ".join(d["name"] for d in duplicates))
        ) + " " + result["message"]
    return result


def propose_update(env, model, record_id=None, values=None):
    """Prepara la modificacion de UN campo de UN registro. NO escribe."""
    check_write_allowed(env)
    cfg, op_cfg = wcat.check_model(model, "update")
    _check_odoo_access(env, model, "update")
    values = values or {}

    if record_id in (None, "", False):
        raise WriteCatalogError(
            "Falta `record_id`. Busca antes el registro con `query_records` y "
            "usa el id exacto; nunca modifiques por nombre aproximado."
        )
    try:
        record_id = int(record_id)
    except (TypeError, ValueError):
        raise WriteCatalogError("`record_id` debe ser un entero.")

    provided = {k: v for k, v in values.items() if v not in (None, "", [])}
    if not provided:
        raise WriteCatalogError("No has indicado ningún valor nuevo.")
    if len(provided) > 1:
        raise WriteCatalogError(
            "Solo se puede modificar un campo por acción. Recibidos: %s."
            % ", ".join(sorted(provided))
        )

    record = env[model].sudo(False).browse(record_id)
    if not record.exists():
        raise WriteCatalogError(
            "No existe ningún registro de %s con id %s." % (cfg["label"], record_id)
        )

    vals, display = normalize_values(env, model, "update", provided)
    field = list(provided)[0]
    spec = wcat.field_spec(model, field)

    before_raw, before_txt = read_value(record, field, spec)
    after_raw = raw_from_vals(spec, vals[field])

    if same_value(spec, before_raw, after_raw):
        raise WriteCatalogError(
            "%s ya vale %s en %s; no hay nada que cambiar."
            % (spec["label"], before_txt, record.display_name)
        )

    subtitle = record.display_name
    code = getattr(record, "default_code", False)
    if code:
        subtitle = "%s (%s)" % (subtitle, code)

    preview = {
        "operation": "update",
        "model": model,
        "model_label": cfg["label"],
        "title": "Modificar %s: %s" % (cfg["label"].lower(), subtitle),
        "lines": [],
        "defaults": [],
        "duplicates": [],
        "changes": [{
            "label": spec["label"],
            "before": before_txt,
            "after": display[field],
        }],
    }

    action = env["ai.chat.action"].create_draft(
        operation="update", model_name=model, values=vals, preview=preview,
        record_id=record.id, before_values={field: before_raw},
    )

    return {
        "tool": "propose_update",
        "model": model,
        "status": "draft",
        "action_id": action.id,
        "preview": preview,
        "message": "Propuesta preparada. NO se ha modificado nada todavía: la "
                   "persona debe pulsar «Aplicar» en la ficha de confirmación.",
    }
