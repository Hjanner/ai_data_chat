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


# Campos que "cubren" a otro a efectos del filtro por defecto: si la peticion
# filtra por `order_id.state`, ya esta hablando del estado y no hay que
# imponer el nuestro.
_DEFAULT_EQUIVALENTS = {
    "state": ("state", "order_id.state"),
}


def _is_leaf(element):
    """Un leaf es (campo, operador, valor). Ojo: un fragmento con OR tambien
    tiene tres elementos ('|', leaf, leaf), y no es un leaf."""
    return (
        isinstance(element, (list, tuple))
        and len(element) == 3
        and isinstance(element[0], str)
        and element[0] not in cat.LOGIC_OPERATORS
        and isinstance(element[1], str)
    )


def _domain_fields(domain):
    """Campos que aparecen a la izquierda de algun leaf, recursivamente."""
    found = set()
    for element in domain:
        if isinstance(element, str):  # '&', '|', '!'
            continue
        if _is_leaf(element):
            found.add(element[0])
        elif isinstance(element, (list, tuple)):  # fragmento anidado
            found.update(_domain_fields(element))
    return found


def _resolve_placeholders(domain):
    """'@today' -> la fecha de hoy. El catalogo es estatico; las fechas no."""
    today = date.today().strftime("%Y-%m-%d")
    out = []
    for element in domain:
        if isinstance(element, str):
            out.append(element)
        elif _is_leaf(element):
            field, operator, value = element
            out.append((field, operator, today if value == "@today" else value))
        else:
            out.extend(_resolve_placeholders(list(element)))
    return out


def _apply_default_domain(cfg, domain):
    """Anade los leaves del filtro por defecto que la peticion no contradice.

    Leaf a leaf: pedir recepciones ya hechas desactiva el filtro de estado,
    pero no el de "solo entradas".
    """
    default = cfg.get("default_domain") or []
    if not default:
        return domain
    asked = _domain_fields(domain)
    missing = []
    for condition in default:
        # Un elemento puede ser un leaf suelto o un fragmento con su propio
        # operador logico (p.ej. "vigente" = sin fecha de fin O fecha futura).
        if _is_leaf(condition):
            fields_used = {condition[0]}
            fragment = _resolve_placeholders([condition])
        else:
            fields_used = _domain_fields(condition)
            fragment = _resolve_placeholders(list(condition))
        covered = set()
        for field in fields_used:
            covered.update(_DEFAULT_EQUIVALENTS.get(field, (field,)))
        if not asked.intersection(covered):
            missing.extend(fragment)
    return missing + list(domain)


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
    model = cat.normalize_model(model)
    cfg = cat.check_model(model)
    group_by = cat.check_group_by(model, group_by)
    parsed_measures = cat.check_measures(model, measures)

    domain = cat.validate_domain(model, domain or [])
    domain = _apply_period(domain, period)
    domain = cat.validate_domain(model, domain)

    domain = _apply_default_domain(cfg, domain)

    # Las medias ponderadas no las calcula SQL: se piden las dos sumas que las
    # componen y se dividen despues, por grupo.
    weighted_map = cfg.get("weighted") or {}
    weighted = [
        (field, alias, weighted_map[field])
        for (field, agg, alias) in parsed_measures
        if agg == "weighted"
    ]

    # Campos read_group: 'alias:agg(campo)' evita colisiones de nombre.
    rg_fields = [
        "%s:%s(%s)" % (alias, agg, field)
        for (field, agg, alias) in parsed_measures
        if agg not in ("count", "weighted")
    ]
    # Sumas auxiliares para las ponderadas (con alias propio para no pisar
    # una medida que el usuario haya pedido a la vez).
    for _field, alias, (amount_field, qty_field) in weighted:
        rg_fields.append("%s__amount:sum(%s)" % (alias, amount_field))
        rg_fields.append("%s__qty:sum(%s)" % (alias, qty_field))

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
            if agg == "count":
                row[alias] = count
            elif agg == "weighted":
                amount = rec.get("%s__amount" % alias) or 0.0
                qty = rec.get("%s__qty" % alias) or 0.0
                # Sin cantidad no hay precio medio: mejor None que un 0 que
                # el modelo leeria como "gratis".
                row[alias] = round(amount / qty, 2) if qty else None
            else:
                row[alias] = rec.get(alias, 0)
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
    model = cat.normalize_model(model)
    cfg = cat.check_model(model)
    fields = cat.check_output_fields(model, fields)

    domain = cat.validate_domain(model, domain or [])
    domain = _apply_period(domain, period)
    domain = cat.validate_domain(model, domain)

    domain = _apply_default_domain(cfg, domain)

    limit = cat.clamp_limit(limit)

    # Validar que el campo de orden es un campo de salida permitido.
    order_sql = None
    sort_in_python = None
    if order:
        order_field, desc = _split_order(order)
        if order_field not in cfg["output"]:
            raise cat.CatalogError(
                "No se puede ordenar por %r: no es un campo de salida permitido." % (order_field,)
            )
        if order_field in cat.unsortable_fields(model):
            # Odoo no puede ordenar por estos... y lo peor es que NO avisa:
            # ignora el orden en silencio y devuelve un ranking con toda la
            # apariencia de ser correcto. Se ordena aqui, en Python.
            sort_in_python = (order_field, desc)
            order_sql = None
            if order_field not in fields:
                fields = list(fields) + [order_field]
        order_sql = "%s %s" % (order_field, "desc" if desc else "asc")

    total = env[model].sudo(False).search_count(domain)

    partial_ranking = False
    if sort_in_python:
        # Para ordenar hay que leer antes: se trae un bloque acotado, se
        # ordena y se recorta. Si los candidatos no caben en el bloque, el
        # ranking es PARCIAL y hay que decirlo: un top-10 sacado de una
        # muestra no es un top-10.
        records = env[model].sudo(False).search_read(
            domain, fields, limit=cat.MAX_LIMIT, order=None,
        )
        partial_ranking = total > len(records)
        order_field, desc = sort_in_python
        records.sort(
            key=lambda r: (r.get(order_field) is None, r.get(order_field)),
            reverse=desc,
        )
        records = records[:limit]
    else:
        records = env[model].sudo(False).search_read(
            domain, fields, limit=limit, order=order_sql,
        )

    for rec in records:
        for key, value in list(rec.items()):
            rec[key] = _norm_value(value)

    result = {
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
    if sort_in_python:
        result["sorted_in_python"] = sort_in_python[0]
    if partial_ranking:
        result["partial_ranking"] = True
        result["ranking_note"] = (
            "Hay %d registros que cumplen el filtro y solo se han podido "
            "ordenar los primeros %d: este orden es PARCIAL, no un ranking "
            "global. Acota más el filtro." % (total, cat.MAX_LIMIT)
        )
    return result
