# AI Data Chat — Capa de datos

Herramientas de **solo lectura** que traducen peticiones estructuradas
(`{tool, params}`) en consultas al ORM de Odoo. El cliente LLM habla la API
de **OpenAI Chat Completions**, así que funciona con cualquier proveedor que
la exponga —Gemini (Google AI Studio), OpenRouter, OpenAI...— sin tocar
código: se elige con `AI_DATA_CHAT_PROVIDER` en el `.env`.

## Estado

| Componente | Estado |
|---|---|
| `services/date_utils.py` — periodos relativos → rangos de fecha | ✅ |
| `services/schema_catalog.py` — catálogo blanco (modelos, campos, operadores, medidas) | ✅ |
| `services/query_tools.py` — `aggregate` (read_group) y `query_records` (search_read) | ✅ |
| `services/tool_dispatcher.py` — punto de entrada único `run_tool(env, tool, params)` | ✅ |
| `models/ai_chat_session` + `ai_chat_message` — persistencia de conversaciones | ✅ |
| `models/ai_chat_responder` — responder conmutable (`manual` / `llm`) | ✅ |
| `controllers/main.py` — endpoints JSON para la UI | ✅ |
| `static/src` — acción cliente OWL (chat) | ✅ |
| `views/` — menús + vistas backend de respaldo | ✅ |
| `services/config.py` — carga `.env` / entorno / `ir.config_parameter` | ✅ |
| `services/llm_prompt.py` — system prompt + esquemas de herramientas (formato OpenAI) | ✅ |
| `services/llm_client.py` — `LLMClient` (Chat Completions) + bucle de tool-calling | ✅ |
| `_respond_llm` conectado al cliente | ✅ |
| `tests/` — 59 tests (datos, preguntas objetivo de Ventas y Compras, flujo de chat, reglas de registro, cliente LLM con transporte simulado) | ✅ |
| Prueba real contra la API del proveedor | ✅ validado en vivo con Gemini |

## Configuración (`.env`)

Copia `.env.example` a `.env` (junto al módulo) y pega la clave:

```
AI_DATA_CHAT_PROVIDER=gemini
AI_DATA_CHAT_API_KEY=...           # de Google AI Studio
AI_DATA_CHAT_MODEL=gemini-3.6-flash
AI_DATA_CHAT_RESPONDER_MODE=llm
```

Proveedores soportados vía presets (`services/config.py: PROVIDER_PRESETS`):
`gemini` (Google AI Studio), `openrouter`, `openai`. Cada uno fija su
`base_url` y modelo por defecto; se pueden pisar con `AI_DATA_CHAT_BASE_URL` /
`AI_DATA_CHAT_MODEL`. Cambiar de Gemini a OpenRouter cuando esté pagado es
solo cambiar `AI_DATA_CHAT_PROVIDER` + `AI_DATA_CHAT_API_KEY` en el `.env`.

`.env` está en `.gitignore`. Precedencia: `ir.config_parameter` >
variable de entorno > `.env` > preset del proveedor. En producción se usa
`ir.config_parameter` (Ajustes → Técnico → Parámetros del sistema):
`ai_data_chat.provider`, `ai_data_chat.api_key`, `ai_data_chat.model`,
`ai_data_chat.responder_mode`, etc.

## Modo del responder

`ai_data_chat.responder_mode` (o `AI_DATA_CHAT_RESPONDER_MODE` en `.env`):

- `manual` (por defecto) — sin IA, no interpreta lenguaje natural. Solo
  acepta una llamada de herramienta en JSON (`{"tool": ..., "params": ...}`);
  cualquier otra cosa devuelve un mensaje de ayuda.
- `llm` — usa el proveedor configurado. `AiChatResponder._respond_llm`
  construye el system prompt (`llm_prompt`), pasa hasta 10 mensajes de
  historial y delega en `LLMClient.answer()`, que ejecuta el bucle de
  tool-calling (`aggregate` / `query_records`) hasta `max_tool_iterations`
  y devuelve el texto final + traza de herramientas + tokens.

## UI

Menú **Asistente de datos → Asistente** (acción cliente `ai_data_chat.chat`).
Barra lateral de conversaciones + hilo de mensajes + caja de texto. El
Markdown que devuelve el modelo (negrita, cursiva, `código`, viñetas) se
renderiza escapando antes el HTML. Las consultas corren con los permisos del
usuario; quien no tenga acceso a Ventas o Compras recibe un error controlado.

## Herramientas

### `aggregate` — rankings, KPIs, conteos → `read_group`

```python
run_tool(env, "aggregate", {
    "model": "sale.order.line",
    "group_by": ["product_id"],                 # [] = KPI global
    "measures": ["price_subtotal:sum", "product_uom_qty:sum"],
    "period": {"field": "order_id.date_order", "name": "last_3_months"},
    "order": "price_subtotal_sum desc",          # alias = <campo>_<agg>
    "limit": 1,
})
```

### `query_records` — listados filtrados → `search_read`

```python
run_tool(env, "query_records", {
    "model": "sale.order",
    "fields": ["name", "partner_id", "amount_total", "date_order"],
    "domain": [["state", "in", ["draft", "sent"]]],
    "order": "amount_total desc",
    "limit": 50,
})
```

## Garantías de seguridad

- Solo los modelos/campos/operadores/medidas del `CATALOG` llegan al ORM.
- Las consultas corren con el `env` del usuario → se respetan ACL y reglas
  de registro. Nunca se usa `sudo` para elevar privilegios.
- `limit` tiene tope duro (`MAX_LIMIT = 200`).
- Solo lectura: no hay ninguna ruta de escritura.
- El `tool_dispatcher` nunca propaga excepciones: devuelve `{"ok": False, "error": ...}`.

## Periodos aceptados

`today`, `yesterday`, `this_week`, `this_month`, `last_month`,
`this_quarter`, `last_quarter`, `this_year`,
`last_<n>_days`, `last_<n>_weeks`, `last_<n>_months`, `last_<n>_years`.

Las fechas las calcula `date_utils`, **nunca el LLM**.

## Probar

### Tests automáticos

```bash
# batería normal (excluye el smoke de navegador)
./odoo/odoo-bin -c ~/.odoorc -d odoo_migracion_test -u ai_data_chat \
    --test-enable --test-tags 'ai_data_chat,-ai_data_chat_ui' --stop-after-init

# smoke de la UI OWL con Chrome (requiere websocket-client y un Chrome compatible)
./odoo/odoo-bin -c ~/.odoorc -d odoo_migracion_test \
    --test-enable --test-tags ai_data_chat_ui --stop-after-init
```

### A mano (haciendo de LLM)

```bash
./odoo/odoo-bin shell -c ~/.odoorc -d odoo_migracion_test --shell-interface=python \
    < custom_addons/ai_data_chat/tools/run_tool.py
# luego: demo()   /   t("aggregate", model="sale.order", ...)   /   catalog()
```

## Preguntas objetivo (criterio de "funciona")

Viven como tests en `tests/test_target_questions.py`, contrastadas contra SQL
de control calculado en tiempo de ejecución.

**Ventas (Q1–Q5)**

1. ¿Cuál es el artículo con más ventas en los últimos 3 meses?
2. ¿Cuántas farmacias han hecho pedidos en los últimos 10 días?
3. ¿Qué farmacia nos ha comprado más (en importe) este trimestre?
4. ¿Qué presupuestos están pendientes de confirmar y por qué importe?
5. ¿Cuánto hemos vendido este mes y cuál es el ticket medio por pedido?

**Compras (C1–C3)**

1. ¿A qué proveedor le hemos comprado más este trimestre?
2. ¿Qué productos hemos comprado más en los últimos 3 meses, por importe?
3. ¿Qué solicitudes de presupuesto de compra están pendientes y por cuánto?

## Compras: diferencias frente a Ventas

Al añadir `purchase.order` / `purchase.order.line` hay tres trampas que el
catálogo ya contempla:

| | Ventas | Compras |
|---|---|---|
| Estado confirmado | `sale` | **`purchase`** |
| Cantidad pedida | `product_uom_qty` | **`product_qty`** |
| `partner_id` significa | Cliente (farmacia) | **Proveedor** |

Por eso `column_label()` acepta un `model`: las etiquetas admiten overrides
por modelo (`CATALOG[modelo]["labels"]`), y el mismo `partner_id` se muestra
como "Cliente" en ventas y "Proveedor" en compras.

### Fuera de alcance por ahora

*"¿Qué pedidos de compra están pendientes de recibir?"* no se puede expresar:
requiere comparar dos campos entre sí (`qty_received < product_qty`) y los
dominios de Odoo solo comparan campo contra valor. Necesitaría una
herramienta nueva.
