# -*- coding: utf-8 -*-
"""Catalogo blanco de ESCRITURA: que se puede crear/modificar y con que campos.

Hermano de `schema_catalog` (que gobierna la lectura), pero mucho mas
restrictivo: aqui cada campo se declara uno a uno con su tipo, si es
obligatorio y como se valida. Nada que no este en `WRITE_CATALOG` llega
nunca a `create()` ni a `write()`.

Reglas de diseno:
  * Lista blanca de campos, no lista negra. Un campo nuevo de Odoo no se
    vuelve escribible por accidente.
  * Ni `state`, ni campos calculados, ni nada contable.
  * Las altas de producto van contra `product.template` (lo correcto en
    Odoo: la variante se genera sola); las modificaciones de precio van
    contra `product.product`, que es lo que devuelven las busquedas de
    lectura y que delega el `list_price` en su plantilla.
  * Las modificaciones son de UN campo y UN registro. Nada masivo.
"""

class WriteCatalogError(ValueError):
    """Peticion de escritura que viola el catalogo blanco."""


# --- Topes para documentos (presupuestos de compra) -----------------------
# Un presupuesto de seis cifras no deberia nacer de una frase.
MAX_DOC_LINES = 20
MAX_DOC_AMOUNT = 50000.0

# Roles de contacto: vocabulario del negocio -> campos reales de Odoo.
PARTNER_ROLES = {
    "cliente": {"customer_rank": 1},
    "proveedor": {"supplier_rank": 1},
    "ambos": {"customer_rank": 1, "supplier_rank": 1},
}

# --- Definicion de campos --------------------------------------------------
# type: char | text | float | email | phone | many2one | many2many | role
#   label    : etiqueta en espanol (UI y preguntas del asistente)
#   help     : pista que ve el modelo al preguntar por el dato
#   comodel  : (many2one/many2many) modelo destino
#   min      : (float) minimo permitido
#   max_len  : (char/text) longitud maxima
WRITE_CATALOG = {
    "product.template": {
        "label": "Producto",
        "create": {
            "required": ["name", "list_price", "categ_id"],
            "optional": ["default_code", "standard_price", "barcode"],
            # Se aplican siempre y se MUESTRAN en la confirmacion; el modelo
            # no los pregunta ni puede cambiarlos.
            "defaults": {
                "type": "product",
                "sale_ok": True,
                "purchase_ok": True,
            },
            "default_labels": {
                "type": "Tipo: Almacenable",
                "sale_ok": "Se puede vender: sí",
                "purchase_ok": "Se puede comprar: sí",
            },
            # Campos con los que se busca un posible duplicado antes de crear.
            "duplicate_on": ["default_code", "name"],
        },
        "update": {"fields": []},
        "fields": {
            "name": {
                "type": "char", "label": "Nombre", "max_len": 128,
                "help": "Nombre comercial del producto, p.ej. 'Paracetamol 500mg caja 20'.",
            },
            "list_price": {
                "type": "float", "label": "Precio de venta", "min": 0.0,
                "help": "Precio de venta unitario.",
            },
            "standard_price": {
                "type": "float", "label": "Coste", "min": 0.0,
                "help": "Coste de compra unitario (opcional).",
            },
            "categ_id": {
                "type": "many2one", "label": "Categoría", "comodel": "product.category",
                "help": "Categoría de producto YA EXISTENTE. No se crean categorías nuevas.",
            },
            "default_code": {
                "type": "char", "label": "Referencia interna", "max_len": 64,
                "help": "Referencia interna / SKU (opcional).",
            },
            "barcode": {
                "type": "char", "label": "Código de barras", "max_len": 64,
                "help": "Código de barras (opcional).",
            },
        },
    },

    "product.product": {
        "label": "Producto",
        # Las altas se hacen sobre product.template, no aqui.
        "create": None,
        "update": {"fields": [
            "list_price", "standard_price", "default_code", "barcode", "name",
        ]},
        "fields": {
            "list_price": {
                "type": "float", "label": "Precio de venta", "min": 0.0,
                "help": "Precio de venta unitario.",
            },
            "standard_price": {
                "type": "float", "label": "Coste", "min": 0.0,
                "help": "Coste de compra unitario.",
            },
            "default_code": {
                "type": "char", "label": "Referencia interna", "max_len": 64,
                "help": "Referencia interna / SKU de esta variante.",
            },
            "barcode": {
                "type": "char", "label": "Código de barras", "max_len": 64,
                "help": "Código de barras de esta variante.",
            },
            "name": {
                "type": "char", "label": "Nombre", "max_len": 128,
                "help": "Nombre del producto. OJO: vive en la plantilla, así que "
                        "el cambio afecta a todas sus variantes.",
            },
        },
        # Campos que se leen para construir el 'antes -> despues'.
        "display": ["name", "default_code", "list_price"],
    },

    "purchase.order": {
        "label": "Presupuesto de compra",
        "create": {
            "required": ["partner_id", "lines"],
            "optional": [],
            "defaults": {},
            "duplicate_on": [],
            # Documento con lineas: la cabecera lleva `lines`, y cada linea se
            # valida contra su propio mini-catalogo.
            "lines": {
                "field": "order_line",
                "required": ["product_id", "product_qty"],
                "optional": ["price_unit"],
                "max": MAX_DOC_LINES,
            },
            "max_amount": MAX_DOC_AMOUNT,
        },
        "update": {"fields": []},
        "fields": {
            "partner_id": {
                "type": "many2one", "label": "Proveedor", "comodel": "res.partner",
                # Sin dominio fijo: `supplier_rank` solo lo sube Odoo al
                # confirmar por su propio flujo, asi que en una base real casi
                # todos los proveedores lo tienen a 0. Se valida aparte, con un
                # criterio que si se sostiene (ver _check_is_supplier).
                "help": "Proveedor al que se le pide el presupuesto.",
            },
            "lines": {
                "type": "lines", "label": "Líneas",
                "help": "Lista de {product_id, product_qty} y, opcionalmente, "
                        "price_unit si la persona indica el precio a mano.",
            },
            "product_id": {
                "type": "many2one", "label": "Producto", "comodel": "product.product",
                # `create()` acepta productos no comprables: ese filtro solo
                # existe en la interfaz de Odoo, hay que ponerlo aqui.
                "domain": [("purchase_ok", "=", True)],
                "domain_hint": "no está marcado como comprable",
                "help": "Producto a comprar. Debe estar marcado como comprable.",
            },
            "product_qty": {
                "type": "float", "label": "Cantidad", "min": 0.001,
                "help": "Cantidad a pedir.",
            },
            "price_unit": {
                "type": "float", "label": "Precio unitario", "min": 0.0,
                "help": "Solo si la persona indica el precio. Si no, se toma "
                        "de la tarifa del proveedor.",
            },
        },
    },
    "res.partner": {
        "label": "Contacto",
        "create": {
            "required": ["name", "role"],
            "optional": ["phone", "email", "city", "street", "vat", "category_id"],
            # Recomendados: se preguntan, pero no bloquean la creacion.
            "recommended": ["phone", "email", "city"],
            "defaults": {"is_company": True},
            "default_labels": {"is_company": "Es una empresa: sí"},
            "duplicate_on": ["name"],
        },
        "update": {"fields": [
            "name", "phone", "email", "city", "street", "vat", "category_id",
        ]},
        "fields": {
            "name": {
                "type": "char", "label": "Nombre", "max_len": 128,
                "help": "Razón social, p.ej. 'Farmacia San Rafael'.",
            },
            "role": {
                "type": "role", "label": "Rol",
                "help": "Uno de: cliente, proveedor, ambos. Si el usuario no lo "
                        "dice con claridad, PREGÚNTALO: no lo deduzcas.",
            },
            "phone": {"type": "phone", "label": "Teléfono", "max_len": 32, "help": "Teléfono de contacto."},
            "email": {"type": "email", "label": "Email", "max_len": 128, "help": "Correo electrónico."},
            "city": {"type": "char", "label": "Ciudad", "max_len": 64, "help": "Ciudad."},
            "street": {"type": "char", "label": "Dirección", "max_len": 128, "help": "Calle y número."},
            "vat": {"type": "char", "label": "RIF / NIF", "max_len": 32, "help": "Identificación fiscal."},
            "category_id": {
                "type": "many2many", "label": "Etiquetas", "comodel": "res.partner.category",
                "help": "Etiquetas de contacto YA EXISTENTES. No se crean etiquetas nuevas.",
            },
        },
        "display": ["name", "city", "email", "phone"],
    },
}

# Operaciones soportadas.
OPERATIONS = ("create", "update")

# Un borrador sin confirmar caduca a las N horas.
DRAFT_EXPIRY_HOURS = 24

# Tope de candidatos que se muestran al desambiguar.
MAX_CANDIDATES = 10


# --- Validadores ----------------------------------------------------------
def check_model(model, operation):
    """Devuelve (cfg_modelo, cfg_operacion) o lanza."""
    if operation not in OPERATIONS:
        raise WriteCatalogError(
            "Operación no soportada: %r. Soportadas: %s" % (operation, ", ".join(OPERATIONS))
        )
    cfg = WRITE_CATALOG.get(model)
    if not cfg:
        raise WriteCatalogError(
            "Modelo no escribible: %r. Escribibles: %s"
            % (model, ", ".join(sorted(writable_models())))
        )
    op_cfg = cfg.get(operation)
    if not op_cfg:
        raise WriteCatalogError(
            "No se permite '%s' sobre %s." % (operation, model)
        )
    if operation == "update" and not op_cfg.get("fields"):
        raise WriteCatalogError(
            "No hay campos modificables declarados para %s." % (model,)
        )
    return cfg, op_cfg


def writable_models():
    return [m for m, cfg in WRITE_CATALOG.items() if cfg.get("create") or (cfg.get("update") or {}).get("fields")]


def field_spec(model, field):
    cfg = WRITE_CATALOG.get(model) or {}
    spec = (cfg.get("fields") or {}).get(field)
    if not spec:
        raise WriteCatalogError("Campo no escribible en %s: %r." % (model, field))
    return spec


def line_config(model):
    """Config de lineas de un documento, o None si el modelo no es documental."""
    cfg = WRITE_CATALOG.get(model) or {}
    return (cfg.get("create") or {}).get("lines")


def allowed_fields(model, operation):
    """Campos que la peticion puede traer para esa operacion."""
    _cfg, op_cfg = check_model(model, operation)
    if operation == "create":
        return list(op_cfg["required"]) + list(op_cfg.get("optional") or [])
    return list(op_cfg["fields"])


def check_fields(model, operation, values):
    """Rechaza cualquier campo fuera de la lista blanca de la operacion."""
    if not isinstance(values, dict):
        raise WriteCatalogError("`values` debe ser un objeto {campo: valor}.")
    allowed = set(allowed_fields(model, operation))
    extra = [f for f in values if f not in allowed]
    if extra:
        raise WriteCatalogError(
            "Campo(s) no escribible(s) en %s para '%s': %s. Permitidos: %s"
            % (model, operation, ", ".join(map(repr, extra)), ", ".join(sorted(allowed)))
        )
    return dict(values)


def label(model, field):
    try:
        return field_spec(model, field)["label"]
    except WriteCatalogError:
        return field


def check_line_fields(model, values):
    """Rechaza cualquier campo de linea fuera de la lista blanca."""
    lines_cfg = line_config(model)
    if not lines_cfg:
        raise WriteCatalogError("%s no admite lineas." % (model,))
    allowed = set(lines_cfg["required"]) | set(lines_cfg.get("optional") or [])
    if not isinstance(values, dict):
        raise WriteCatalogError("Cada linea debe ser un objeto {campo: valor}.")
    extra = [f for f in values if f not in allowed]
    if extra:
        raise WriteCatalogError(
            "Campo(s) no permitido(s) en una linea de %s: %s. Permitidos: %s"
            % (model, ", ".join(map(repr, extra)), ", ".join(sorted(allowed)))
        )
    return dict(values)


def describe_fields(model, operation):
    """Descripcion JSON-able de los campos de la operacion (para el modelo)."""
    cfg, op_cfg = check_model(model, operation)

    def _one(name):
        spec = cfg["fields"][name]
        out = {"field": name, "label": spec["label"], "type": spec["type"], "help": spec.get("help", "")}
        if spec["type"] == "role":
            out["values"] = sorted(PARTNER_ROLES)
        if spec.get("comodel"):
            out["comodel"] = spec["comodel"]
        return out

    if operation == "create":
        recommended = set(op_cfg.get("recommended") or [])
        lines_cfg = op_cfg.get("lines")
        extra = {}
        if lines_cfg:
            extra["lines"] = {
                "required": [_one(f) for f in lines_cfg["required"]],
                "optional": [_one(f) for f in (lines_cfg.get("optional") or [])],
                "max": lines_cfg["max"],
            }
        return {
            "model": model,
            "label": cfg["label"],
            **extra,
            "required": [_one(f) for f in op_cfg["required"]],
            "optional": [
                dict(_one(f), recommended=f in recommended)
                for f in (op_cfg.get("optional") or [])
            ],
            "defaults": [
                (op_cfg.get("default_labels") or {}).get(k, "%s = %s" % (k, v))
                for k, v in (op_cfg.get("defaults") or {}).items()
            ],
        }
    return {
        "model": model,
        "label": cfg["label"],
        "required": [_one(f) for f in op_cfg["fields"]],
        "optional": [],
        "defaults": [],
    }
