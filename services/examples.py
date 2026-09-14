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
]
