# -*- coding: utf-8 -*-
"""Punto de entrada unico de la capa de datos.

El cliente LLM (o los tests, o `odoo shell`) llaman siempre aqui:

    run_tool(env, "aggregate", {"model": "sale.order", ...})

Nunca se ejecuta una herramienta que no este en TOOLS, y cualquier
excepcion de validacion/ejecucion se devuelve como {"error": ...} en vez
de propagarse, para que el bucle del chatbot pueda reaccionar.
"""
import logging

from . import query_tools
from . import schema_catalog as cat
from . import date_utils

_logger = logging.getLogger(__name__)

TOOLS = {
    "aggregate": query_tools.aggregate,
    "query_records": query_tools.query_records,
}


def run_tool(env, tool, params):
    """Valida y ejecuta una herramienta. Devuelve siempre un dict."""
    if tool not in TOOLS:
        return {"ok": False, "error": "unknown_tool",
                "message": "Herramienta desconocida: %r. Validas: %s"
                           % (tool, ", ".join(sorted(TOOLS)))}
    if not isinstance(params, dict):
        return {"ok": False, "error": "bad_params", "message": "`params` debe ser un objeto."}

    try:
        result = TOOLS[tool](env, **params)
        result["ok"] = True
        return result
    except cat.CatalogError as err:
        return {"ok": False, "error": "catalog_error", "message": str(err)}
    except date_utils.PeriodError as err:
        return {"ok": False, "error": "period_error", "message": str(err)}
    except TypeError as err:
        # Normalmente: parametro inesperado o falta uno obligatorio.
        return {"ok": False, "error": "bad_params", "message": str(err)}
    except Exception as err:  # noqa: BLE001 - frontera: nada debe escapar al chatbot
        _logger.exception("Fallo ejecutando la herramienta %s con %r", tool, params)
        return {"ok": False, "error": "execution_error", "message": str(err)}


# --- Metadatos para construir el system prompt del LLM (fase cliente) ------
def list_tools():
    """Descripcion de las herramientas y del catalogo, JSON-serializable."""
    return {
        "tools": {
            "aggregate": {
                "description": "Agrupa y agrega registros (rankings, KPIs, conteos). "
                               "Traduce a read_group.",
                "params": {
                    "model": "str - uno de los modelos del catalogo",
                    "group_by": "list[str] - campos de agrupacion (admite 'date_order:month')",
                    "measures": "list[str] - 'campo:agg' con agg en sum|avg|min|max|count",
                    "domain": "list - domain de Odoo (opcional)",
                    "period": "{'field': <campo fecha>, 'name': <periodo>} (opcional)",
                    "order": "str - 'alias desc' (opcional)",
                    "limit": "int - nº maximo de grupos (opcional)",
                },
            },
            "query_records": {
                "description": "Devuelve un listado de registros filtrado. Traduce a search_read.",
                "params": {
                    "model": "str - uno de los modelos del catalogo",
                    "fields": "list[str] - campos a devolver",
                    "domain": "list - domain de Odoo (opcional)",
                    "period": "{'field': <campo fecha>, 'name': <periodo>} (opcional)",
                    "order": "str - 'campo desc' (opcional)",
                    "limit": "int - por defecto %d, maximo %d" % (cat.DEFAULT_LIMIT, cat.MAX_LIMIT),
                },
            },
        },
        "periods": date_utils.supported_periods(),
        "catalog": cat.describe(),
    }
