# -*- coding: utf-8 -*-
"""System prompt + esquemas de herramientas (formato OpenAI/OpenRouter).

El modelo NUNCA escribe SQL ni dominios libres arbitrarios: elige una de las
dos herramientas y rellena sus parámetros. La validación real la hace
`tool_dispatcher.run_tool` contra el catálogo blanco; aquí solo se le describe
al modelo qué puede pedir.
"""
from . import date_utils
from . import schema_catalog as cat
from . import write_catalog as wcat
from .write_tools import WRITE_GROUP

_BUSINESS_CONTEXT = (
    "Eres el asistente de datos de una droguería (distribuidora mayorista) que "
    "suministra productos a farmacias de la ciudad. Respondes preguntas sobre "
    "los datos de Ventas, Compras, Contactos y Productos del ERP Odoo.\n"
    "\n"
    "Vocabulario del negocio:\n"
    "- VENTAS (lo que la droguería vende a las farmacias): modelos `sale.order` "
    "y `sale.order.line`. Ahí, \"cliente\" o \"farmacia\" = el contacto del "
    "campo partner_id. Estado confirmado: 'sale'; presupuesto: 'draft'/'sent'.\n"
    "- COMPRAS (lo que la droguería compra a sus proveedores, laboratorios o "
    "distribuidores): modelos `purchase.order` y `purchase.order.line`. Ahí "
    "partner_id es el PROVEEDOR, no el cliente. Estado confirmado: 'purchase'; "
    "solicitud de presupuesto (RFQ): 'draft'/'sent'.\n"
    "- Si la pregunta habla de vender, facturar a farmacias o clientes, usa los "
    "modelos de venta. Si habla de comprar, proveedores, aprovisionar o "
    "reponer stock, usa los de compra."
)

_RULES = [
    "Responde SIEMPRE en español, de forma breve y concreta.",
    "Para obtener datos usa exclusivamente las herramientas `aggregate` y "
    "`query_records`. No inventes cifras.",
    "Por defecto solo consultas: no propongas crear, modificar ni borrar nada "
    "salvo que la persona lo pida explícitamente.",
    "No inventes nombres de campos: usa únicamente los listados en el catálogo.",
    "Para acotar por fechas usa el parámetro `period` con un nombre de periodo "
    "válido; no calcules fechas tú.",
    "Si la pregunta es ambigua o pide datos fuera del catálogo (stock, "
    "facturación, márgenes…), dilo con claridad en vez de adivinar.",
    "Tras recibir el resultado de una herramienta, redacta la respuesta final "
    "para la persona, citando las cifras relevantes con separador de miles.",
    "No inventes la moneda: los importes no llevan símbolo salvo que el dato lo "
    "traiga. Escribe '5,75', no '5,75 €'.",
]


_WRITE_RULES = [
    "Puedes preparar altas y modificaciones, pero NUNCA las aplicas tú: las "
    "herramientas `propose_*` solo dejan una propuesta que la persona confirma "
    "pulsando un botón. Si te responde \"sí\" o \"confirma\" por escrito, "
    "recuérdale que tiene que pulsar el botón de la ficha.",
    "Antes de preparar un alta, usa `describe_create` para saber qué campos "
    "hacen falta y pregúntalos TODOS en un mismo mensaje. No te inventes el "
    "cuestionario ni rellenes datos que la persona no te ha dado.",
    "Si falta algún dato obligatorio, pide solo lo que falte; no repitas lo "
    "que ya te han dicho.",
    "Nunca inventes categorías, etiquetas ni contactos: si lo que te dicen no "
    "existe, dilo y ofrece las opciones existentes que devuelva el error.",
    "Para modificar, primero localiza el registro con `query_records` y usa el "
    "`id` exacto en `propose_update`. Si hay varios candidatos, enséñaselos y "
    "pregunta cuál; nunca elijas tú.",
    "No se admiten cambios masivos: una acción modifica un campo de un "
    "registro. Si piden algo tipo \"sube todos los X un 10%\", explica que no "
    "puedes hacerlo.",
    "Al contar una propuesta preparada, resume qué se va a crear o cambiar y "
    "avisa de los duplicados si el resultado los menciona.",
]


def can_write(env):
    """Solo se ofrecen las herramientas de escritura a quien tiene el grupo."""
    if env is None:
        return False
    try:
        return env.user.has_group(WRITE_GROUP)
    except Exception:  # noqa: BLE001 - entorno sin usuario (tests, shell)
        return False


def _write_catalog_lines():
    lines = ["", "Datos que se pueden CREAR o MODIFICAR (nada más):"]
    for model, cfg in wcat.WRITE_CATALOG.items():
        create_cfg = cfg.get("create")
        update_cfg = (cfg.get("update") or {}).get("fields")
        if not create_cfg and not update_cfg:
            continue
        lines.append("• %s — %s" % (model, cfg["label"]))
        if create_cfg:
            lines.append("    crear, obligatorios: %s" % ", ".join(create_cfg["required"]))
            if create_cfg.get("optional"):
                lines.append("    crear, opcionales: %s" % ", ".join(create_cfg["optional"]))
        if update_cfg:
            lines.append("    modificar (requiere record_id): %s" % ", ".join(update_cfg))
    lines.append("    roles válidos de contacto: %s" % ", ".join(sorted(wcat.PARTNER_ROLES)))
    return lines


def build_system_prompt(env=None):
    catalog = cat.describe()
    writable = can_write(env)
    lines = [_BUSINESS_CONTEXT, "", "Reglas:"]
    lines += ["- %s" % r for r in _RULES]
    if writable:
        lines += ["", "Reglas de escritura:"]
        lines += ["- %s" % r for r in _WRITE_RULES]
    else:
        lines += ["- Solo lectura: no dispones de herramientas para crear ni "
                  "modificar datos. Si te lo piden, di que no tienes permiso."]
    lines += ["", "Periodos válidos para `period.name`:",
              "  " + ", ".join(date_utils.supported_periods())]
    lines += ["", "Catálogo de modelos (lo único consultable):"]
    for model, cfg in catalog.items():
        lines.append("• %s — %s" % (model, cfg["label"]))
        lines.append("    filtrar por: %s" % ", ".join(cfg["filter"]))
        if cfg["group_by"]:
            lines.append("    agrupar por: %s" % ", ".join(cfg["group_by"]))
        if cfg["measures"]:
            lines.append("    medir (sum/avg/min/max): %s" % ", ".join(cfg["measures"]))
        lines.append("    devolver (query_records): %s" % ", ".join(cfg["output"]))
        if cfg["default_domain"]:
            lines.append("    filtro por defecto aplicado: %s" % cfg["default_domain"])
    if writable:
        lines += _write_catalog_lines()
    return "\n".join(lines)


def _domain_schema():
    return {
        "type": "array",
        "description": (
            "Domain de Odoo: lista de tripletas [campo, operador, valor] y, "
            "opcionalmente, operadores lógicos '&' '|' '!' como elementos sueltos. "
            "Los campos deben pertenecer al catálogo del modelo."
        ),
        "items": {},
    }


def _period_schema():
    return {
        "type": "object",
        "description": "Acota por un campo de fecha a un periodo con nombre.",
        "properties": {
            "field": {"type": "string", "description": "Campo de fecha del modelo, p.ej. 'date_order'."},
            "name": {"type": "string", "description": "Periodo, p.ej. 'last_3_months', 'this_month'."},
        },
        "required": ["field", "name"],
    }


def tool_schemas(env=None):
    """Lista de herramientas en formato OpenAI 'tools'.

    Las de escritura solo se incluyen si el usuario tiene el grupo: lo que no
    se le ofrece al modelo, el modelo no puede pedirlo.
    """
    models = list(cat.CATALOG.keys())
    schemas = _read_tool_schemas(models)
    if can_write(env):
        schemas += _write_tool_schemas()
    return schemas


def _read_tool_schemas(models):
    return [
        {
            "type": "function",
            "function": {
                "name": "aggregate",
                "description": (
                    "Agrupa y agrega registros para rankings, KPIs y conteos "
                    "(se traduce a read_group)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "model": {"type": "string", "enum": models},
                        "group_by": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Campos de agrupación (admite 'date_order:month'). "
                                "Lista vacía = KPI global sin agrupar."
                            ),
                        },
                        "measures": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Medidas 'campo:agg' con agg en sum|avg|min|max|count, "
                                "p.ej. 'amount_total:sum'."
                            ),
                        },
                        "domain": _domain_schema(),
                        "period": _period_schema(),
                        "order": {
                            "type": "string",
                            "description": (
                                "Orden, p.ej. 'amount_total_sum desc'. El alias de una "
                                "medida es '<campo>_<agg>'."
                            ),
                        },
                        "limit": {"type": "integer", "description": "Máximo de grupos a devolver."},
                    },
                    "required": ["model", "group_by", "measures"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_records",
                "description": "Devuelve un listado de registros filtrado (se traduce a search_read).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "model": {"type": "string", "enum": models},
                        "fields": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Campos a devolver (deben estar en 'devolver' del catálogo).",
                        },
                        "domain": _domain_schema(),
                        "period": _period_schema(),
                        "order": {"type": "string", "description": "p.ej. 'amount_total desc'."},
                        "limit": {"type": "integer", "description": "Máx. %d." % cat.MAX_LIMIT},
                    },
                    "required": ["model", "fields"],
                },
            },
        },
    ]


def _write_tool_schemas():
    """Herramientas que PREPARAN escrituras. Ninguna aplica cambios: el
    commit lo dispara la persona desde la interfaz."""
    creatable = [m for m, cfg in wcat.WRITE_CATALOG.items() if cfg.get("create")]
    updatable = [m for m, cfg in wcat.WRITE_CATALOG.items() if (cfg.get("update") or {}).get("fields")]
    values_schema = {
        "type": "object",
        "description": "Pares {campo: valor} con los campos del catálogo de escritura.",
        "additionalProperties": True,
    }
    return [
        {
            "type": "function",
            "function": {
                "name": "describe_create",
                "description": (
                    "Devuelve qué campos hacen falta para dar de alta un registro "
                    "(obligatorios, opcionales y valores por defecto). Úsala ANTES "
                    "de preguntarle los datos a la persona."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"model": {"type": "string", "enum": creatable}},
                    "required": ["model"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "propose_create",
                "description": (
                    "Prepara un alta y la deja PENDIENTE DE CONFIRMAR. No escribe "
                    "en la base de datos. Si faltan campos obligatorios, devuelve "
                    "cuáles para que los preguntes."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "model": {"type": "string", "enum": creatable},
                        "values": values_schema,
                    },
                    "required": ["model", "values"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "propose_update",
                "description": (
                    "Prepara la modificación de UN campo de UN registro existente y "
                    "la deja PENDIENTE DE CONFIRMAR. No escribe en la base de datos. "
                    "Requiere el id exacto, localizado antes con `query_records`."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "model": {"type": "string", "enum": updatable},
                        "record_id": {
                            "type": "integer",
                            "description": "Id exacto del registro a modificar.",
                        },
                        "values": values_schema,
                    },
                    "required": ["model", "record_id", "values"],
                },
            },
        },
    ]
