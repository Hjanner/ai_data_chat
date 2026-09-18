# -*- coding: utf-8 -*-
"""Las 5 preguntas objetivo del MVP como fixtures de desarrollo.

Único consumidor: `tools/run_tool.py` (`demo()`), que las ejecuta contra la
capa de datos desde `odoo shell` para comprobar de un vistazo que las
consultas siguen dando los valores esperados.

NO son un atajo del chat: el asistente se prueba escribiendo las preguntas
en lenguaje natural (modo `llm`) o mandando `{"tool": ..., "params": ...}`
en JSON (modo `manual`).
"""

EXAMPLE_QUESTIONS = [
    {
        "key": "q1",
        "label": "¿Cuál es el artículo con más ventas en los últimos 3 meses?",
        "tool": "aggregate",
        "params": {
            "model": "sale.order.line",
            "group_by": ["product_id"],
            "measures": ["price_subtotal:sum", "product_uom_qty:sum"],
            "period": {"field": "order_id.date_order", "name": "last_3_months"},
            "order": "price_subtotal_sum desc",
            "limit": 3,
        },
    },
    {
        "key": "q2",
        "label": "¿Cuántas farmacias han hecho pedidos en los últimos 10 días?",
        "tool": "aggregate",
        "params": {
            "model": "sale.order",
            "group_by": ["partner_id"],
            "measures": ["amount_total:count"],
            "period": {"field": "date_order", "name": "last_10_days"},
        },
    },
    {
        "key": "q3",
        "label": "¿Qué farmacia nos ha comprado más (en importe) este trimestre?",
        "tool": "aggregate",
        "params": {
            "model": "sale.order",
            "group_by": ["partner_id"],
            "measures": ["amount_total:sum"],
            "period": {"field": "date_order", "name": "this_quarter"},
            "order": "amount_total_sum desc",
            "limit": 3,
        },
    },
    {
        "key": "q4",
        "label": "¿Qué presupuestos están pendientes de confirmar y por qué importe?",
        "tool": "query_records",
        "params": {
            "model": "sale.order",
            "fields": ["name", "partner_id", "amount_total", "date_order"],
            "domain": [["state", "in", ["draft", "sent"]]],
            "order": "amount_total desc",
            "limit": 50,
        },
    },
    {
        "key": "q5",
        "label": "¿Cuánto hemos vendido este mes y cuál es el ticket medio por pedido?",
        "tool": "aggregate",
        "params": {
            "model": "sale.order",
            "group_by": [],
            "measures": ["amount_total:sum", "amount_total:avg"],
            "period": {"field": "date_order", "name": "this_month"},
        },
    },
    # --- Compras -------------------------------------------------------
    {
        "key": "c1",
        "label": "¿A qué proveedor le hemos comprado más este trimestre?",
        "tool": "aggregate",
        "params": {
            "model": "purchase.order",
            "group_by": ["partner_id"],
            "measures": ["amount_total:sum"],
            "period": {"field": "date_order", "name": "this_quarter"},
            "order": "amount_total_sum desc",
            "limit": 3,
        },
    },
    {
        "key": "c2",
        "label": "¿Qué productos hemos comprado más en los últimos 3 meses, por importe?",
        "tool": "aggregate",
        "params": {
            "model": "purchase.order.line",
            "group_by": ["product_id"],
            "measures": ["price_subtotal:sum", "product_qty:sum"],
            "period": {"field": "order_id.date_order", "name": "last_3_months"},
            "order": "price_subtotal_sum desc",
            "limit": 5,
        },
    },
    {
        "key": "c3",
        "label": "¿Qué solicitudes de presupuesto de compra están pendientes y por cuánto?",
        "tool": "query_records",
        "params": {
            "model": "purchase.order",
            "fields": ["name", "partner_id", "amount_total", "date_order"],
            "domain": [["state", "in", ["draft", "sent"]]],
            "order": "amount_total desc",
            "limit": 50,
        },
    },
    {
        "key": "c4",
        "label": "¿A qué proveedor le compramos más barato un producto?",
        "tool": "aggregate",
        "params": {
            "model": "purchase.order.line",
            "group_by": ["partner_id"],
            # Ponderado por cantidad: el promedio simple de precios unitarios
            # miente en cuanto las cantidades no son iguales.
            "measures": ["price_unit:weighted", "product_qty:sum", "price_subtotal:sum"],
            "domain": [["product_id.categ_id", "ilike", "All"]],
            "order": "price_unit_weighted asc",
            "limit": 10,
        },
    },
    {
        "key": "c5",
        "label": "¿Qué proveedores tengo para un producto, a qué precio y plazo?",
        "tool": "query_records",
        "params": {
            "model": "product.supplierinfo",
            "fields": ["partner_id", "price", "price_discounted", "min_qty",
                       "delay", "currency_id"],
            "domain": [["product_tmpl_id.name", "ilike", "Large Cabinet"]],
            # El precio va ligado a la cantidad mínima: ordenar solo por precio
            # puede poner en cabeza un escalón que no se alcanza.
            "order": "price asc",
            "limit": 20,
        },
    },
    # --- Recepciones ---------------------------------------------------
    {
        "key": "r1",
        "label": "¿Cuántas recepciones tengo pendientes y de qué proveedores?",
        "tool": "aggregate",
        "params": {
            "model": "stock.picking",
            "group_by": ["partner_id"],
            # stock.picking no tiene importes: solo se cuenta.
            "measures": ["name:count"],
            "order": "name_count desc",
        },
    },
    {
        "key": "r2",
        "label": "¿Qué recepciones están atrasadas?",
        "tool": "query_records",
        "params": {
            "model": "stock.picking",
            "fields": ["name", "partner_id", "scheduled_date", "state", "origin"],
            # 'atrasado' = fecha prevista ya pasada. Que siga pendiente lo pone
            # el filtro por defecto del catálogo.
            "period": {"field": "scheduled_date", "name": "until_now"},
            "order": "scheduled_date asc",
            "limit": 50,
        },
    },
    {
        "key": "r3",
        "label": "¿Qué recepciones llegan en los próximos 15 días?",
        "tool": "query_records",
        "params": {
            "model": "stock.picking",
            "fields": ["name", "partner_id", "scheduled_date", "origin"],
            "period": {"field": "scheduled_date", "name": "next_15_days"},
            "order": "scheduled_date asc",
            "limit": 50,
        },
    },
]


# --- Fase 1 de escritura: los 3 casos objetivo -----------------------------
# Igual que EXAMPLE_QUESTIONS, son fixtures de desarrollo: se ejecutan desde
# `tools/run_tool.py` (`demo_write()`) para comprobar la capa de escritura sin
# gastar API. NINGUNO escribe en la base de datos: `propose_*` solo deja un
# borrador en `ai.chat.action` pendiente de que una persona lo confirme.
WRITE_CASES = [
    {
        "key": "w1",
        "label": "Crear un producto (alta simple con relleno por turnos)",
        "steps": [
            # 1) El asistente consulta qué campos hacen falta antes de preguntar.
            {"tool": "describe_create", "params": {"model": "product.template"}},
            # 2) Petición incompleta: debe responder qué falta, no inventarlo.
            {"tool": "propose_create", "params": {
                "model": "product.template",
                "values": {"name": "Ibuprofeno 400mg caja 20"},
            }},
            # 3) Petición completa -> borrador pendiente de confirmar.
            {"tool": "propose_create", "params": {
                "model": "product.template",
                "values": {
                    "name": "Ibuprofeno 400mg caja 20",
                    "list_price": "12,50",
                    "categ_id": "All",
                    "default_code": "IBU-400-20",
                },
            }},
        ],
    },
    {
        "key": "w2",
        "label": "Crear un contacto distinguiendo cliente de proveedor",
        "steps": [
            # 1) Sin rol: falta un obligatorio, debe preguntarlo.
            {"tool": "propose_create", "params": {
                "model": "res.partner",
                "values": {"name": "Farmacia San Rafael"},
            }},
            # 2) Email inválido: lo rechaza el módulo, no el ORM.
            {"tool": "propose_create", "params": {
                "model": "res.partner",
                "values": {"name": "Farmacia San Rafael", "role": "cliente",
                           "email": "no-es-un-email"},
            }},
            # 3) Completo, rol "ambos" -> customer_rank y supplier_rank.
            {"tool": "propose_create", "params": {
                "model": "res.partner",
                "values": {
                    "name": "Distribuidora Centro",
                    "role": "ambos",
                    "phone": "+58 212 555 0110",
                    "email": "contacto@distcentro.test",
                    "city": "Caracas",
                },
            }},
        ],
    },
    {
        "key": "w3",
        "label": "Actualizar el precio de venta de un producto",
        "steps": [
            # 1) Localizar el registro (esto ya lo hace la capa de lectura).
            {"tool": "query_records", "params": {
                "model": "product.product",
                "fields": ["name", "default_code", "list_price"],
                "domain": [["name", "ilike", "a"]],
                "limit": 5,
            }},
            # 2) Sin record_id: se rechaza, hay que desambiguar antes.
            {"tool": "propose_update", "params": {
                "model": "product.product",
                "values": {"list_price": 3.20},
            }},
            # 3) Campo fuera de la lista blanca de modificación.
            {"tool": "propose_update", "params": {
                "model": "product.product",
                "record_id": 1,
                "values": {"name": "Nombre nuevo"},
            }},
        ],
    },
]
