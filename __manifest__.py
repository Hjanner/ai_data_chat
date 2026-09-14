# -*- coding: utf-8 -*-
{
    'name': "AI Data Chat - Capa de datos",
    'summary': "Herramientas de consulta de solo lectura sobre datos de Ventas/CRM/Contactos "
               "para alimentar un chatbot de IA.",
    'description': """
Capa de datos del modulo AI Data Chat.

Expone un conjunto acotado de herramientas de SOLO LECTURA que traducen
peticiones estructuradas ({tool, params}) en consultas al ORM de Odoo:

    - aggregate(...)       -> read_group (rankings, KPIs, conteos)
    - query_records(...)   -> search_read (listados filtrados)

Toda peticion se valida contra un catalogo blanco de modelos, campos,
operadores y medidas antes de ejecutarse. Las consultas corren con los
permisos del usuario que las invoca (se respetan reglas de registro y ACL).

El cliente LLM habla la API de OpenAI Chat Completions, asi que funciona con
cualquier proveedor que la exponga (Gemini/Google AI Studio, OpenRouter,
OpenAI...) sin tocar codigo: se elige con AI_DATA_CHAT_PROVIDER en el .env
del modulo o el parametro de sistema 'ai_data_chat.provider'.
    """,
    'author': "Dromax",
    'category': 'Productivity',
    'version': '17.0.1.0.0',
    'license': 'LGPL-3',
    'application': False,
    'installable': True,
    'depends': [
        'base',
        'sale',
        'purchase',
        'web',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/ai_chat_security.xml',
        'views/ai_chat_client_action.xml',
        'views/ai_chat_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ai_data_chat/static/src/scss/chat_action.scss',
            'ai_data_chat/static/src/js/chat_action.js',
            'ai_data_chat/static/src/xml/chat_action.xml',
        ],
    },
}
