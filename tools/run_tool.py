# -*- coding: utf-8 -*-
"""Probar la capa de datos a mano, sin LLM.

Uso (sustituye <BD> por tu base de datos y <RUTA> por la ruta al modulo):

    odoo-bin shell -d <BD> --shell-interface=python < <RUTA>/tools/run_tool.py

o, dentro de `odoo-bin shell`:

    >>> exec(open('<RUTA>/tools/run_tool.py').read())

Define `demo()` (ejecuta las preguntas de ejemplo de Ventas y Compras),
`t(tool, **params)` (atajo para una llamada suelta) y `catalog()` (imprime
el catalogo y las herramientas). `env` lo inyecta el propio shell de Odoo.
"""
import json
import pprint

from odoo.addons.ai_data_chat.services.tool_dispatcher import run_tool, list_tools
from odoo.addons.ai_data_chat.services.examples import EXAMPLE_QUESTIONS


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


def catalog():
    """Imprime el catalogo y las herramientas (lo que vera el LLM)."""
    print(json.dumps(list_tools(), indent=2, ensure_ascii=False, default=str))


if "env" in dir():
    print("ai_data_chat: capa de datos cargada. Funciones: demo(), t(), catalog()")
