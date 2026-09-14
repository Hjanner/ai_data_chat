# -*- coding: utf-8 -*-
"""System prompt + esquemas de herramientas (formato OpenAI/OpenRouter).

El modelo NUNCA escribe SQL ni dominios libres arbitrarios: elige una de las
dos herramientas y rellena sus parámetros. La validación real la hace
`tool_dispatcher.run_tool` contra el catálogo blanco; aquí solo se le describe
al modelo qué puede pedir.
"""
from . import date_utils
from . import schema_catalog as cat

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
    "Solo lectura: nunca propongas crear, modificar ni borrar registros.",
    "No inventes nombres de campos: usa únicamente los listados en el catálogo.",
    "Para acotar por fechas usa el parámetro `period` con un nombre de periodo "
    "válido; no calcules fechas tú.",
    "Si la pregunta es ambigua o pide datos fuera del catálogo (stock, "
    "facturación, márgenes…), dilo con claridad en vez de adivinar.",
    "Tras recibir el resultado de una herramienta, redacta la respuesta final "
    "para la persona, citando las cifras relevantes con separador de miles.",
]


def build_system_prompt(env=None):
    catalog = cat.describe()
    lines = [_BUSINESS_CONTEXT, "", "Reglas:"]
    lines += ["- %s" % r for r in _RULES]
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


def tool_schemas():
    """Lista de herramientas en formato OpenAI 'tools'."""
    models = list(cat.CATALOG.keys())
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
