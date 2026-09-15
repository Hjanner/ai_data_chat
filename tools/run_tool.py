# -*- coding: utf-8 -*-
"""Probar la capa de datos a mano, sin LLM.

Uso (sustituye <BD> por tu base de datos y <RUTA> por la ruta al modulo):

    odoo-bin shell -d <BD> --shell-interface=python < <RUTA>/tools/run_tool.py

o, dentro de `odoo-bin shell`:

    >>> exec(open('<RUTA>/tools/run_tool.py').read())

Define `demo()` (preguntas de ejemplo de Ventas y Compras), `demo_write()`
(los 3 casos de escritura, que solo dejan borradores sin confirmar),
`t(tool, **params)` (atajo para una llamada suelta) y `catalog()` (imprime
el catalogo y las herramientas). `env` lo inyecta el propio shell de Odoo.
"""
import json
import pprint

from odoo.addons.ai_data_chat.services.tool_dispatcher import run_tool, list_tools
from odoo.addons.ai_data_chat.services.examples import EXAMPLE_QUESTIONS, WRITE_CASES


def t(tool, **params):
    """Atajo: t('aggregate', model='sale.order', group_by=['partner_id'], ...)."""
    res = run_tool(env, tool, params)  # noqa: F821 - `env` viene del shell
    pprint.pprint(res, sort_dicts=False, width=120)
    return res


def demo():
    """Ejecuta las 5 preguntas objetivo del MVP y muestra el resultado."""
    for q in EXAMPLE_QUESTIONS:
        print("\n" + "=" * 78)
        print("%s · %s" % (q["key"].upper(), q["label"]))
        print("-" * 78)
        res = run_tool(env, q["tool"], q["params"])  # noqa: F821
        pprint.pprint(res, sort_dicts=False, width=120)


def demo_write():
    """Ejecuta los 3 casos de escritura de la fase 1.

    No escribe nada: `propose_*` solo deja borradores en `ai.chat.action`
    pendientes de que una persona los confirme desde el chat.
    """
    for case in WRITE_CASES:
        print("\n" + "=" * 78)
        print("%s · %s" % (case["key"].upper(), case["label"]))
        for i, step in enumerate(case["steps"], 1):
            print("-" * 78)
            print("  paso %d: %s %s" % (i, step["tool"], step["params"]))
            res = run_tool(env, step["tool"], step["params"])  # noqa: F821
            pprint.pprint(res, sort_dicts=False, width=120)


def catalog():
    """Imprime el catalogo y las herramientas (lo que vera el LLM)."""
    print(json.dumps(list_tools(), indent=2, ensure_ascii=False, default=str))


if "env" in dir():
    print("ai_data_chat: capa de datos cargada. Funciones: demo(), demo_write(), t(), catalog()")
