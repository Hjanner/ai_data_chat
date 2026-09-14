# -*- coding: utf-8 -*-
"""Las dos herramientas de solo lectura que ejecuta el chatbot.

    aggregate(env, ...)       -> read_group   (rankings, KPIs, conteos)
    query_records(env, ...)   -> search_read  (listados filtrados)

Contrato comun:
  * `env` es el environment de Odoo del usuario que pregunta -> se respetan
    ACL y reglas de registro. Nunca se usa sudo aqui.
  * Toda entrada se valida contra schema_catalog ANTES de tocar el ORM.
  * El resultado es siempre JSON-serializable (many2one -> {"id", "name"}).
"""
import logging
from datetime import date, datetime

from . import date_utils
from . import schema_catalog as cat

_logger = logging.getLogger(__name__)


# --- Normalizacion de valores para JSON ----------------------------------
def _norm_value(value):
    """(id, 'Nombre') -> {'id':.., 'name':..}; False -> None; resto igual."""
    if value is False or value is None:
        return None
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], int):
        return {"id": value[0], "name": value[1]}
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return value


def _apply_period(domain, period):
    """`period` = {"field": "date_order", "name": "last_3_months"} (o None)."""
    if not period:
        return domain
    if not isinstance(period, dict) or "field" not in period or "name" not in period:
        raise cat.CatalogError(
            "`period` debe ser {'field': <campo fecha>, 'name': <periodo>}."
        )
    leaves = date_utils.period_to_domain(period["field"], period["name"])
    return list(domain) + leaves


def _split_order(order):
    """'amount_total desc' -> ('amount_total', True).  None -> (None, False)."""
    if not order or not isinstance(order, str):
        return None, False
    parts = order.replace(":", "_").split()
    field = parts[0].strip()
    desc = len(parts) > 1 and parts[1].strip().lower().startswith("desc")
    return field, desc


# --- Herramienta 1: aggregate ------------------------------------------
def aggregate(env, model, group_by, measures, domain=None, period=None,
              order=None, limit=None):
    """Agrupa y agrega. Traduce a read_group.

    :param group_by: lista de campos, admite 'date_order:month'
    :param measures: lista 'campo:agg', p.ej. ['amount_total:sum', 'amount_total:avg']
    :param period: {"field": ..., "name": ...} para acotar por fecha
    :param order:  'alias desc' donde alias es '<campo>_<agg>' o un campo de group_by
    :param limit:  nº maximo de grupos devueltos (tras ordenar en Python)
    """
    cfg = cat.check_model(model)
    group_by = cat.check_group_by(model, group_by)
    parsed_measures = cat.check_measures(model, measures)

    domain = cat.validate_domain(model, domain or [])
    domain = _apply_period(domain, period)
    domain = cat.validate_domain(model, domain)

    # Estado por defecto (solo si la peticion no filtra ya por 'state').
    touches_state = any(
        isinstance(e, (list, tuple)) and len(e) == 3 and e[0] in ("state", "order_id.state")
        for e in domain
    )
    if not touches_state and cfg["default_domain"]:
        domain = list(cfg["default_domain"]) + domain

    # Campos read_group: 'alias:agg(campo)' evita colisiones de nombre.
    rg_fields = [
        "%s:%s(%s)" % (alias, agg, field)
        for (field, agg, alias) in parsed_measures
        if agg != "count"
    ]

    records = env[model].sudo(False).read_group(
        domain, fields=rg_fields, groupby=group_by, lazy=False,
    )

    rows = []
    for rec in records:
        count = rec.get("__count", 0)
        row = {"__count": count}
        for spec in group_by:
            # read_group devuelve la clave tal cual (incluida 'campo:month').
            row[spec] = _norm_value(rec.get(spec))
        for (field, agg, alias) in parsed_measures:
            row[alias] = count if agg == "count" else rec.get(alias, 0)
        rows.append(row)

    # Orden en Python (independiente del backend, admite alias de medida).
    order_field, desc = _split_order(order)
    if order_field:
        rows.sort(
            key=lambda r: (r.get(order_field) is None, r.get(order_field)),
            reverse=desc,
        )

    total_groups = len(rows)
    limit = cat.clamp_limit(limit) if limit is not None else None
    if limit is not None:
        rows = rows[:limit]

    measure_aliases = [a for (_f, _g, a) in parsed_measures]
    return {
        "tool": "aggregate",
        "model": model,
        "domain": domain,
        "group_by": group_by,
        "measures": measure_aliases,
        "row_count": len(rows),
        "group_count": total_groups,
        "truncated": limit is not None and total_groups > limit,
        "rows": rows,
        "labels": cat.column_labels(group_by + measure_aliases, model),
    }


# --- Herramienta 2: query_records ------------------------------------
def query_records(env, model, fields, domain=None, period=None,
                  order=None, limit=None):
    """Listado de registros filtrado. Traduce a search_read."""
    cfg = cat.check_model(model)
    fields = cat.check_output_fields(model, fields)

    domain = cat.validate_domain(model, domain or [])
    domain = _apply_period(domain, period)
    domain = cat.validate_domain(model, domain)

    touches_state = any(
        isinstance(e, (list, tuple)) and len(e) == 3 and e[0] in ("state", "order_id.state")
        for e in domain
    )
    if not touches_state and cfg["default_domain"]:
        domain = list(cfg["default_domain"]) + domain

    limit = cat.clamp_limit(limit)

    # Validar que el campo de orden es un campo de salida permitido.
    order_sql = None
    if order:
        order_field, desc = _split_order(order)
        if order_field not in cfg["output"]:
            raise cat.CatalogError(
                "No se puede ordenar por %r: no es un campo de salida permitido." % (order_field,)
            )
        order_sql = "%s %s" % (order_field, "desc" if desc else "asc")

    total = env[model].sudo(False).search_count(domain)
    records = env[model].sudo(False).search_read(
        domain, fields, limit=limit, order=order_sql,
    )
    for rec in records:
        for key, value in list(rec.items()):
            rec[key] = _norm_value(value)

    return {
        "tool": "query_records",
        "model": model,
        "domain": domain,
        "fields": fields,
        "row_count": len(records),
        "total_count": total,
        "truncated": total > len(records),
        "rows": records,
        "labels": cat.column_labels(fields, model),
    }
