# -*- coding: utf-8 -*-
"""Catalogo blanco: que se puede consultar y como.

Ningun modelo, campo, operador o medida fuera de este catalogo llega al ORM.
Es la unica frontera de seguridad de la capa de datos (junto con las ACL de
Odoo, que se aplican igualmente porque las consultas corren con el env del
usuario).

Alcance: Ventas + Compras + Recepciones + Contactos + Producto.
"""

# --- Operadores permitidos en los domains -----------------------------------
ALLOWED_OPERATORS = {
    "=", "!=", "<", "<=", ">", ">=",
    "in", "not in",
    "like", "not like", "ilike", "not ilike",
    "child_of", "parent_of",
}
# Operadores logicos que pueden aparecer como elementos sueltos del domain.
LOGIC_OPERATORS = {"&", "|", "!"}

# Agregaciones permitidas en las medidas de `aggregate`.
ALLOWED_AGGREGATES = {"sum", "avg", "min", "max", "count"}

# Granularidades permitidas al agrupar por un campo de fecha (campo:granularidad).
ALLOWED_DATE_GRANULARITY = {"day", "week", "month", "quarter", "year"}

# Tope duro de filas devueltas por cualquier herramienta.
MAX_LIMIT = 200
DEFAULT_LIMIT = 20

# --- Catalogo de modelos ---------------------------------------------------
# Por cada modelo:
#   filter   : campos usables en el domain (izquierda del leaf). Se admite un
#              salto de relacion (p.ej. 'order_id.date_order').
#   group_by : campos usables en groupby de `aggregate`.
#   measures : campos numericos agregables en las medidas de `aggregate`.
#   output   : campos devolvibles por `query_records`.
#   default_domain : se aplica LEAF A LEAF, y solo si la peticion no filtra ya
#                    por ese mismo campo. Asi, preguntar por recepciones ya
#                    hechas quita el filtro de estado pero NO el de "solo
#                    entradas", que es lo que delimita el modelo.
CATALOG = {
    "sale.order": {
        "label": "Pedidos de venta",
        "filter": {
            "state", "date_order", "partner_id", "user_id", "team_id",
            "company_id", "amount_total", "amount_untaxed", "name",
            "partner_id.category_id", "partner_id.city", "partner_id.country_id",
        },
        "group_by": {
            "partner_id", "state", "user_id", "team_id", "company_id", "date_order",
        },
        "measures": {"amount_total", "amount_untaxed", "amount_tax"},
        "output": {
            "name", "partner_id", "date_order", "state",
            "amount_total", "amount_untaxed", "user_id", "team_id",
        },
        "default_domain": [("state", "in", ["sale", "done"])],
        "labels": {"name": "Referencia"},
    },
    "sale.order.line": {
        "label": "Lineas de pedido de venta",
        "filter": {
            "state", "product_id", "order_id.state", "order_id.date_order",
            "order_id.partner_id", "order_partner_id", "salesman_id",
            "price_subtotal", "product_uom_qty", "qty_delivered", "qty_invoiced",
            "product_id.categ_id",
        },
        "group_by": {
            "product_id", "order_partner_id", "salesman_id", "state",
            "product_id.categ_id",
        },
        "measures": {
            "price_subtotal", "price_total", "product_uom_qty",
            "qty_delivered", "qty_invoiced",
        },
        "output": {
            "product_id", "name", "product_uom_qty", "qty_delivered",
            "price_subtotal", "price_total", "order_id", "order_partner_id",
        },
        "default_domain": [("state", "in", ["sale", "done"])],
    },
    "purchase.order": {
        "label": "Pedidos de compra",
        # OJO: en compras el estado confirmado es 'purchase' (no 'sale'), y
        # 'draft'/'sent' son solicitudes de presupuesto (RFQ).
        "filter": {
            "state", "date_order", "date_approve", "date_planned", "partner_id",
            "user_id", "company_id", "amount_total", "amount_untaxed", "name",
            "invoice_status",
            "partner_id.category_id", "partner_id.city", "partner_id.country_id",
        },
        "group_by": {
            "partner_id", "state", "user_id", "company_id", "date_order",
            "date_approve", "invoice_status",
        },
        "measures": {"amount_total", "amount_untaxed", "amount_tax"},
        "output": {
            "name", "partner_id", "date_order", "date_planned", "state",
            "amount_total", "amount_untaxed", "user_id", "invoice_status",
        },
        "default_domain": [("state", "in", ["purchase", "done"])],
        # partner_id aqui es el proveedor, no el cliente.
        "labels": {"partner_id": "Proveedor", "name": "Referencia"},
    },
    "purchase.order.line": {
        "label": "Líneas de pedido de compra",
        "filter": {
            "state", "product_id", "order_id.state", "order_id.date_order",
            "order_id.partner_id", "partner_id", "date_planned",
            "price_subtotal", "product_qty", "qty_received", "qty_invoiced",
            "product_id.categ_id",
        },
        "group_by": {
            "product_id", "partner_id", "state", "product_id.categ_id",
            "date_planned",
        },
        "measures": {
            "price_subtotal", "price_total", "product_qty",
            "qty_received", "qty_invoiced",
        },
        "output": {
            "product_id", "name", "product_qty", "qty_received",
            "price_subtotal", "price_total", "order_id", "partner_id",
            "date_planned",
        },
        "default_domain": [("state", "in", ["purchase", "done"])],
        "labels": {"partner_id": "Proveedor"},
    },
    "stock.picking": {
        "label": "Recepciones de compra",
        # Solo entradas: `picking_type_code` NO es filtrable a proposito, asi
        # que el leaf del default_domain no se puede desactivar desde la
        # peticion. Las entregas a farmacias se consultan por sale.order.
        "filter": {
            "state", "scheduled_date", "date_deadline", "partner_id", "origin",
            "name", "company_id", "picking_type_id",
            "partner_id.category_id", "partner_id.city",
        },
        "group_by": {
            "partner_id", "state", "picking_type_id", "company_id",
            "scheduled_date",
        },
        # No hay importes en un albaran: solo se cuentan.
        "measures": set(),
        "output": {
            "name", "partner_id", "scheduled_date", "date_deadline", "state",
            "origin", "picking_type_id",
        },
        "default_domain": [
            ("picking_type_code", "=", "incoming"),
            ("state", "not in", ["done", "cancel"]),
        ],
        # Aqui partner_id es el proveedor del que se espera la mercancia.
        "labels": {
            "partner_id": "Proveedor",
            "name": "Referencia",
            "origin": "Pedido de origen",
            "scheduled_date": "Fecha prevista",
            "picking_type_id": "Tipo de operación",
        },
    },
    "res.partner": {
        "label": "Contactos",
        "filter": {
            "customer_rank", "supplier_rank", "country_id", "state_id", "city",
            "category_id", "is_company", "active", "parent_id", "name",
        },
        "group_by": {"country_id", "state_id", "city", "category_id", "is_company"},
        "measures": {"customer_rank", "supplier_rank"},
        "output": {
            "name", "email", "phone", "city", "category_id",
            "customer_rank", "is_company", "parent_id",
        },
        "default_domain": [],
    },
    "product.product": {
        "label": "Productos",
        "filter": {"type", "categ_id", "active", "sale_ok", "purchase_ok", "list_price", "default_code", "name"},
        "group_by": {"categ_id", "type"},
        "measures": {"list_price", "standard_price"},
        "output": {"name", "default_code", "list_price", "categ_id", "type", "uom_id"},
        "default_domain": [("active", "in", [True, False])],
    },
}


class CatalogError(ValueError):
    """Peticion que viola el catalogo blanco."""


# --- Validadores ----------------------------------------------------------
def check_model(model):
    if model not in CATALOG:
        raise CatalogError(
            "Modelo no permitido: %r. Permitidos: %s"
            % (model, ", ".join(sorted(CATALOG)))
        )
    return CATALOG[model]


def _base_field(spec):
    """'date_order:month' -> ('date_order', 'month');  'partner_id' -> ('partner_id', None)."""
    if ":" in spec:
        field, gran = spec.split(":", 1)
        return field.strip(), gran.strip()
    return spec.strip(), None


def check_group_by(model, group_by):
    """Valida los campos de agrupacion. Se admite lista vacia = KPI global."""
    cfg = check_model(model)
    if group_by in (None, False):
        return []
    if not isinstance(group_by, (list, tuple)):
        raise CatalogError("`group_by` debe ser una lista de campos (o lista vacia).")
    for spec in group_by:
        field, gran = _base_field(spec)
        if field not in cfg["group_by"]:
            raise CatalogError(
                "Campo de agrupacion no permitido para %s: %r. Permitidos: %s"
                % (model, field, ", ".join(sorted(cfg["group_by"])))
            )
        if gran is not None and gran not in ALLOWED_DATE_GRANULARITY:
            raise CatalogError(
                "Granularidad de fecha no permitida: %r. Permitidas: %s"
                % (gran, ", ".join(sorted(ALLOWED_DATE_GRANULARITY)))
            )
    return list(group_by)


def parse_measure(spec):
    """'amount_total:sum' -> ('amount_total', 'sum', 'amount_total_sum').

    El alias evita colisiones cuando se piden dos agregados del mismo campo.
    """
    if not isinstance(spec, str) or ":" not in spec:
        raise CatalogError("Medida mal formada: %r (esperado 'campo:agg')." % (spec,))
    field, agg = (p.strip() for p in spec.split(":", 1))
    if agg not in ALLOWED_AGGREGATES:
        raise CatalogError(
            "Agregacion no permitida: %r. Permitidas: %s"
            % (agg, ", ".join(sorted(ALLOWED_AGGREGATES)))
        )
    return field, agg, "%s_%s" % (field, agg)


def check_measures(model, measures):
    cfg = check_model(model)
    if not measures or not isinstance(measures, (list, tuple)):
        raise CatalogError("`measures` debe ser una lista con al menos una medida.")
    parsed = []
    for spec in measures:
        field, agg, alias = parse_measure(spec)
        if agg != "count" and field not in cfg["measures"]:
            raise CatalogError(
                "Campo de medida no permitido para %s: %r. Permitidos: %s"
                % (model, field, ", ".join(sorted(cfg["measures"])))
            )
        parsed.append((field, agg, alias))
    return parsed


def check_output_fields(model, fields):
    cfg = check_model(model)
    if not fields or not isinstance(fields, (list, tuple)):
        raise CatalogError("`fields` debe ser una lista con al menos un campo.")
    bad = [f for f in fields if f not in cfg["output"]]
    if bad:
        raise CatalogError(
            "Campos no permitidos para %s: %s. Permitidos: %s"
            % (model, ", ".join(map(repr, bad)), ", ".join(sorted(cfg["output"])))
        )
    return list(fields)


def validate_domain(model, domain):
    """Valida un domain de Odoo contra el catalogo. Devuelve el domain tal cual."""
    cfg = check_model(model)
    if domain in (None, [], False):
        return []
    if not isinstance(domain, (list, tuple)):
        raise CatalogError("El domain debe ser una lista.")
    allowed_fields = cfg["filter"]
    for element in domain:
        if isinstance(element, str):
            if element not in LOGIC_OPERATORS:
                raise CatalogError("Operador logico no valido en domain: %r" % (element,))
            continue
        if not isinstance(element, (list, tuple)) or len(element) != 3:
            raise CatalogError("Leaf de domain mal formado: %r" % (element,))
        field, operator, _value = element
        if not isinstance(field, str) or field not in allowed_fields:
            raise CatalogError(
                "Campo no filtrable para %s: %r. Permitidos: %s"
                % (model, field, ", ".join(sorted(allowed_fields)))
            )
        if operator not in ALLOWED_OPERATORS:
            raise CatalogError(
                "Operador no permitido: %r. Permitidos: %s"
                % (operator, ", ".join(sorted(ALLOWED_OPERATORS)))
            )
    return list(domain)


def clamp_limit(limit):
    if limit in (None, False):
        return DEFAULT_LIMIT
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        raise CatalogError("`limit` debe ser un entero.")
    if limit <= 0:
        raise CatalogError("`limit` debe ser positivo.")
    return min(limit, MAX_LIMIT)


# --- Descripcion para el prompt del LLM (se usara en la fase del cliente) ---
def describe(models=None):
    """Estructura JSON-able que resume el catalogo para el system prompt."""
    names = models or list(CATALOG)
    out = {}
    for name in names:
        cfg = check_model(name)
        out[name] = {
            "label": cfg["label"],
            "filter": sorted(cfg["filter"]),
            "group_by": sorted(cfg["group_by"]),
            "measures": sorted(cfg["measures"]),
            "output": sorted(cfg["output"]),
            "default_domain": cfg["default_domain"],
        }
    return out


# --- Etiquetas en español para mostrar en la UI (tablas, resumen) ----------
# Independiente de la validación: si falta una traducción, se muestra el
# nombre técnico tal cual (nunca rompe nada).
FIELD_LABELS = {
    "name": "Nombre",
    "state": "Estado",
    "date_order": "Fecha del pedido",
    "partner_id": "Cliente",
    "order_id": "Pedido",
    "order_partner_id": "Cliente",
    "user_id": "Comercial",
    "salesman_id": "Comercial",
    "team_id": "Equipo de ventas",
    "company_id": "Compañía",
    "amount_total": "Importe total",
    "amount_untaxed": "Base imponible",
    "amount_tax": "Impuestos",
    "product_id": "Producto",
    "product_uom_qty": "Cantidad",
    "product_qty": "Cantidad pedida",
    "qty_delivered": "Cantidad entregada",
    "qty_received": "Cantidad recibida",
    "qty_invoiced": "Cantidad facturada",
    "date_approve": "Fecha de confirmación",
    "date_planned": "Fecha prevista",
    "invoice_status": "Estado de facturación",
    "price_subtotal": "Subtotal",
    "price_total": "Total línea",
    "categ_id": "Categoría",
    "country_id": "País",
    "state_id": "Provincia",
    "city": "Ciudad",
    "category_id": "Etiquetas",
    "customer_rank": "Rango de cliente",
    "supplier_rank": "Rango de proveedor",
    "is_company": "Es empresa",
    "parent_id": "Empresa matriz",
    "active": "Activo",
    "email": "Email",
    "phone": "Teléfono",
    "type": "Tipo",
    "list_price": "Precio de venta",
    "standard_price": "Coste",
    "default_code": "Referencia",
    "uom_id": "Unidad de medida",
    "sale_ok": "Se puede vender",
    "purchase_ok": "Se puede comprar",
}

_GRANULARITY_LABELS = {
    "day": "día", "week": "semana", "month": "mes", "quarter": "trimestre", "year": "año",
}
_AGG_LABELS = {"sum": "suma", "avg": "promedio", "min": "mínimo", "max": "máximo"}


def field_label(field, model=None):
    """Etiqueta en español de un campo, o el propio nombre si no hay traducción.

    Los overrides por modelo mandan sobre el diccionario global: el mismo
    `partner_id` es "Cliente" en ventas y "Proveedor" en compras.
    """
    if model:
        overrides = CATALOG.get(model, {}).get("labels") or {}
        if field in overrides:
            return overrides[field]
    return FIELD_LABELS.get(field, field)


def column_label(key, model=None):
    """Traduce una clave de columna (campo de group_by con o sin granularidad,
    alias de medida '<campo>_<agg>', o campo de salida) a una etiqueta legible.
    """
    if key in ("__count",) or key.endswith("_count"):
        return "Nº de registros"
    if ":" in key:
        base, suffix = key.split(":", 1)
        if suffix in _GRANULARITY_LABELS:
            return "%s (%s)" % (field_label(base, model), _GRANULARITY_LABELS[suffix])
        return field_label(base, model)
    for agg, word in _AGG_LABELS.items():
        suffix = "_%s" % agg
        if key.endswith(suffix):
            return "%s (%s)" % (field_label(key[: -len(suffix)], model), word)
    return field_label(key, model)


def column_labels(keys, model=None):
    """Dict {clave: etiqueta} para un conjunto de columnas."""
    return {k: column_label(k, model) for k in keys}
