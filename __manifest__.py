# -*- coding: utf-8 -*-
{
    'name': "AI Data Chat - Capa de datos",
    'summary': "Chat de IA sobre los datos de Ventas, Compras, Contactos y Productos: "
               "consulta en lenguaje natural y altas/cambios con confirmación humana.",
    'description': """
Capa de datos del modulo AI Data Chat.

Expone un conjunto acotado de herramientas que traducen peticiones
estructuradas ({tool, params}) en llamadas al ORM de Odoo:

    Lectura:
    - aggregate(...)       -> read_group (rankings, KPIs, conteos)
    - query_records(...)   -> search_read (listados filtrados)

    Escritura (requiere el grupo 'Asistente de datos / Escritura'):
    - describe_create(...) -> que campos hacen falta para un alta
    - propose_create(...)  -> prepara un alta   (NO escribe)
    - propose_update(...)  -> prepara un cambio (NO escribe)

Las herramientas de escritura solo dejan un borrador en 'ai.chat.action'. La
escritura real la dispara una persona desde la interfaz; el modelo no dispone
de ninguna herramienta que confirme. Un cambio aplicado se puede deshacer
desde la misma ficha mientras nadie haya tocado ese campo despues.

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
    'version': '17.0.1.2.0',
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
        'security/ai_chat_groups.xml',
        'security/ir.model.access.csv',
        'security/ai_chat_security.xml',
        'views/ai_chat_client_action.xml',
        'views/ai_chat_views.xml',
        'views/ai_chat_action_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ai_data_chat/static/src/scss/chat_action.scss',
            'ai_data_chat/static/src/js/chat_action.js',
            'ai_data_chat/static/src/xml/chat_action.xml',
        ],
    },
}
