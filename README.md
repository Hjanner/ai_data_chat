# AI Data Chat — asistente de consultas para Odoo 17

Módulo de Odoo que añade un **chat para preguntar por los datos del ERP en
lenguaje natural**. En vez de buscar el informe adecuado y configurar sus
filtros, se escribe la pregunta y el asistente responde con la cifra y una
tabla de apoyo. También puede **preparar altas y cambios de datos**, que
siempre confirma una persona.

Está pensado para una distribuidora mayorista (el ejemplo del que nace es una
droguería que suministra a farmacias), pero el catálogo de datos es
configurable y se adapta a cualquier negocio sobre Ventas y Compras.

> **El asistente nunca escribe por su cuenta.** Prepara una propuesta y la
> deja pendiente; la escritura la dispara una persona pulsando un botón.
> Además, cada usuario solo ve y solo toca los datos a los que su usuario de
> Odoo ya tiene acceso, y escribir exige un grupo aparte.

## Qué tipo de preguntas responde

**Ventas**

- ¿Cuál es el artículo con más ventas en los últimos 3 meses?
- ¿Cuántos clientes han hecho pedidos en los últimos 10 días?
- ¿Qué cliente nos ha comprado más (en importe) este trimestre?
- ¿Qué presupuestos están pendientes de confirmar y por qué importe?
- ¿Cuánto hemos vendido este mes y cuál es el ticket medio por pedido?

**Compras**

- ¿A qué proveedor le hemos comprado más este trimestre?
- ¿Qué productos hemos comprado más en los últimos 3 meses, por importe?
- ¿Qué solicitudes de presupuesto de compra están pendientes y por cuánto?

**Recepciones**

- ¿Qué tengo pendiente de recibir y de qué proveedores?
- ¿Qué recepciones están atrasadas?
- ¿Qué llega en los próximos 15 días? ¿Llega algo de [proveedor] este mes?

Un pedido de compra confirmado no significa que la mercancía haya llegado: eso
lo dice la recepción (`stock.picking`), no el pedido.

Distingue por sí solo de qué lado del negocio se habla: en *"¿qué cliente nos
ha comprado más y a qué proveedor le compramos más nosotros?"* consulta los
modelos de venta y los de compra en la misma respuesta.

## Qué puede crear y modificar

Solo esto, y solo con el grupo **Asistente de datos / Escritura**:

| Operación | Alcance |
|---|---|
| Crear producto | Nombre, precio, categoría (+ referencia, coste, código de barras) |
| Crear contacto | Nombre y rol *cliente / proveedor / ambos* (+ teléfono, email, ciudad, dirección, RIF, etiquetas) |
| Modificar un producto | Precio de venta, coste, referencia interna, código de barras, nombre |
| Modificar un contacto | Nombre, teléfono, email, ciudad, dirección, RIF, etiquetas |

Cada modificación toca **un campo de un registro**, y se puede **deshacer**
desde la propia ficha mientras nadie haya vuelto a cambiar ese valor.

El flujo es siempre el mismo:

```
"quiero dar de alta un producto"
   → el asistente pregunta qué falta (lee los campos del catálogo, no los inventa)
   → prepara la propuesta y la muestra en una ficha
   → NADA se ha escrito todavía
   → la persona pulsa «Crear»  →  ahora sí se escribe
```

Un «sí» escrito en el chat no confirma nada: el modelo no dispone de ninguna
herramienta que aplique cambios. Cada propuesta —aplicada, deshecha o
descartada— queda registrada en *Asistente de datos → Acciones de escritura*.

### Deshacer

Un cambio aplicado trae un botón **Deshacer** en su ficha: el módulo guardó el
valor anterior, así que lo devuelve a como estaba. Dos límites deliberados:

- **No pisa el trabajo de nadie.** Si alguien ha vuelto a cambiar ese campo
  desde entonces, el botón desaparece y te dice el valor actual para que lo
  mires a mano.
- **Las altas no se deshacen desde aquí.** Borrar un registro es destructivo y
  puede fallar si ya se usa en otro sitio; eso se archiva o se elimina en Odoo,
  con la cabeza fría.

## Requisitos

- **Odoo 17 Community** (o Enterprise)
- Módulos de Odoo: `sale`, `purchase`, `stock`, `web` (se instalan como
  dependencia; `stock` hace falta para las recepciones)
- Una API key de un proveedor LLM compatible con la API de *OpenAI Chat
  Completions*: **Gemini** (Google AI Studio), **OpenRouter** u **OpenAI**

Sin dependencias de Python adicionales: el cliente HTTP usa `urllib` de la
librería estándar.

## Instalación

```bash
# 1. Clonar dentro de tu carpeta de addons
cd /ruta/a/tus/addons
git clone https://github.com/Hjanner/ai_data_chat.git

# 2. Asegurarte de que esa carpeta está en addons_path (odoo.conf)
#    addons_path = /ruta/a/odoo/addons,/ruta/a/tus/addons

# 3. Instalar el módulo
odoo-bin -d <BASE_DE_DATOS> -i ai_data_chat --stop-after-init
```

Después, en Odoo: activar el modo desarrollador → *Aplicaciones* →
*Actualizar lista de aplicaciones* si no aparece.

## Configuración

Copia `.env.example` a `.env` (junto al módulo) y rellena la clave:

```ini
AI_DATA_CHAT_PROVIDER=gemini          # gemini | openrouter | openai
AI_DATA_CHAT_API_KEY=tu_api_key
AI_DATA_CHAT_MODEL=gemini-3.6-flash   # opcional: cada proveedor trae uno por defecto
AI_DATA_CHAT_RESPONDER_MODE=llm       # manual | llm
```

`.env` está en `.gitignore`: **no subas tu clave al repositorio.**

**Orden de precedencia** (de mayor a menor):

1. `ir.config_parameter` — *Ajustes → Técnico → Parámetros del sistema*
   (`ai_data_chat.provider`, `ai_data_chat.api_key`, `ai_data_chat.model`,
   `ai_data_chat.responder_mode`…)
2. Variable de entorno del proceso de Odoo
3. Fichero `.env`
4. Preset del proveedor

En producción se recomienda `ir.config_parameter` o variables de entorno; el
`.env` es la vía cómoda para desarrollo.

### Cambiar de proveedor

Cada proveedor tiene un preset en `services/config.py: PROVIDER_PRESETS` que
fija su `base_url` y su modelo por defecto. Pasar de Gemini a OpenRouter es
cambiar dos líneas del `.env` (`AI_DATA_CHAT_PROVIDER` y la API key), sin
tocar código. Para un endpoint distinto —un proxy o un modelo autoalojado—
existe `AI_DATA_CHAT_BASE_URL`.

## Uso

Menú **Asistente de datos → Asistente**.

Barra lateral con el historial de conversaciones, hilo de mensajes y caja de
texto. Las respuestas del modelo se muestran con su formato (negrita,
cursiva, `código`, viñetas) y, cuando la consulta devuelve filas, con una
tabla de columnas traducidas al español.

En **Asistente de datos → Conversaciones** hay una vista de respaldo con
todas las conversaciones y la traza técnica de cada mensaje: qué herramienta
se ejecutó, con qué parámetros, qué devolvió y cuántos tokens costó.

### Modo `manual` (sin IA)

Con `AI_DATA_CHAT_RESPONDER_MODE=manual` el chat no interpreta lenguaje
natural: solo acepta una llamada de herramienta en JSON. Sirve para probar la
capa de datos sin gastar API:

```json
{"tool": "query_records", "params": {"model": "sale.order", "fields": ["name", "amount_total"], "limit": 5}}
```

También se puede ejercitar desde `odoo-bin shell`:

```bash
odoo-bin shell -d <BASE_DE_DATOS> --shell-interface=python < tools/run_tool.py
# luego:  demo()        preguntas de ejemplo de Ventas y Compras
#         demo_write()  los 3 casos de escritura (solo dejan borradores)
#         t("aggregate", model="sale.order", ...)   /   catalog()
```

## Cómo funciona

El modelo de lenguaje **nunca escribe SQL ni toca el ORM**. Solo elige una
herramienta y rellena sus parámetros; el módulo los valida contra un catálogo
blanco antes de ejecutar nada.

```
Pregunta → LLM → {tool, params} → validación (catálogo) → ORM de Odoo
                                                             ↓
        Respuesta redactada ← LLM ← resultado (filas + etiquetas)
```

### Las herramientas

**`aggregate`** — rankings, KPIs y conteos → `read_group`

```python
run_tool(env, "aggregate", {
    "model": "sale.order.line",
    "group_by": ["product_id"],                  # [] = KPI global sin agrupar
    "measures": ["price_subtotal:sum", "product_uom_qty:sum"],
    "period": {"field": "order_id.date_order", "name": "last_3_months"},
    "order": "price_subtotal_sum desc",          # alias de medida = <campo>_<agg>
    "limit": 1,
})
```

**`query_records`** — listados filtrados → `search_read`

```python
run_tool(env, "query_records", {
    "model": "sale.order",
    "fields": ["name", "partner_id", "amount_total", "date_order"],
    "domain": [["state", "in", ["draft", "sent"]]],
    "order": "amount_total desc",
    "limit": 50,
})
```

**`describe_create`** — qué campos hacen falta para un alta. Es lo que permite
que el asistente pregunte por los datos en vez de inventárselos.

**`propose_create`** / **`propose_update`** — **preparan** un alta o un cambio y
dejan un borrador en `ai.chat.action`. No tocan la base de datos. `propose_update`
exige el `id` exacto del registro: si el nombre es ambiguo, el asistente enseña
las candidatas y pregunta.

```python
run_tool(env, "propose_update", {
    "model": "product.product",
    "record_id": 42,                    # localizado antes con query_records
    "values": {"list_price": "3,20"},   # un solo campo, un solo registro
})
```

La confirmación (`ai.chat.action.action_confirm`) **no es una herramienta**: no
aparece en el esquema que se le manda al modelo y solo la alcanzan los endpoints
`/ai_data_chat/action/<id>/confirm`, `/undo` y `/discard`, que dispara la
interfaz.

### Periodos aceptados

Hacia atrás: `today`, `yesterday`, `this_week`, `this_month`, `last_month`,
`this_quarter`, `last_quarter`, `this_year`, `last_<n>_días|semanas|meses|años`.

Hacia adelante: `tomorrow`, `next_week`, `next_month`, `next_quarter`,
`next_<n>_días|semanas|meses|años`.

Abiertos por un extremo: `until_now` (todo lo anterior a este momento — es lo
que significa "atrasado"), `until_today`, `from_now`, `from_today`.

Las fechas las calcula el módulo (`services/date_utils.py`), **nunca el
LLM**: el modelo solo nombra el periodo.

## Garantías de seguridad

- **Catálogo blanco**: solo los modelos, campos, operadores y medidas
  declarados en `services/schema_catalog.py` llegan al ORM. Cualquier otra
  cosa se rechaza antes de ejecutarse.
- **Permisos del usuario**: las consultas corren con el `env` de quien
  pregunta, así que se respetan las ACL y las reglas de registro de Odoo.
  Nunca se usa `sudo` para elevar privilegios.
- **Escritura separada y en dos tiempos**: hace falta el grupo *Asistente de
  datos / Escritura* para que se le ofrezcan siquiera las herramientas al
  modelo, y aun así este solo puede **proponer**. Lo que no se le ofrece, no
  puede pedirlo.
- **Lista blanca de escritura aparte** (`services/write_catalog.py`), mucho más
  corta que la de lectura: ni `state`, ni campos calculados, ni nada contable.
  Nunca se crean categorías, etiquetas ni contactos "de paso" para completar un
  alta: si no existen, se dice.
- **Nada masivo**: una acción modifica un campo de un registro. Los cambios
  guardan el valor anterior (`before_values`) y se pueden deshacer, salvo que
  alguien haya tocado ese campo mientras tanto.
- **Borradores con caducidad**: una propuesta sin confirmar expira a las 24 h y
  no deja rastro en los datos de negocio.
- **Pista de auditoría**: cada propuesta registra quién, cuándo, qué modelo, qué
  valores y qué registro salió — incluidas las descartadas.
- **Tope de filas**: `limit` tiene un máximo duro (`MAX_LIMIT = 200`).
- **Conversaciones privadas**: cada usuario ve únicamente las suyas
  (reglas de registro en `security/`).
- **Sin HTML inyectable**: el texto del modelo se escapa antes de renderizar
  su formato, porque puede contener datos de la base.
- **Errores controlados**: el despachador nunca propaga excepciones; devuelve
  `{"ok": false, "error": ...}` para que el chat pueda explicarlo.

> ⚠️ **Privacidad**: para responder, las preguntas y los datos consultados se
> envían al proveedor LLM que configures — y, si usas la escritura, también los
> datos de las altas (nombres de proveedores, precios…). Revisa su política de
> tratamiento de datos antes de usarlo con información real de clientes.

## Alcance de los datos

| Área | Modelos |
|---|---|
| Ventas | `sale.order`, `sale.order.line` |
| Compras | `purchase.order`, `purchase.order.line` |
| Recepciones | `stock.picking` (solo entradas) |
| Contactos | `res.partner` |
| Productos | `product.product`, `product.template` (altas) |

Ampliar el alcance es añadir una entrada al `CATALOG` de
`services/schema_catalog.py` con los campos filtrables, agrupables, medibles
y devolvibles de cada modelo nuevo.

### Compras no es un calco de Ventas

Tres diferencias que el catálogo ya contempla, y que conviene conocer si
amplías el módulo:

| | Ventas | Compras |
|---|---|---|
| Estado confirmado | `sale` | **`purchase`** |
| Cantidad pedida | `product_uom_qty` | **`product_qty`** |
| Qué es `partner_id` | Cliente | **Proveedor** |

Por eso las etiquetas admiten *overrides* por modelo
(`CATALOG[modelo]["labels"]`): el mismo `partner_id` se muestra como
"Cliente" en ventas y como "Proveedor" en compras.

### Recepciones: solo entradas, a propósito

`stock.picking` sirve tanto para lo que entra como para lo que sale, pero el
catálogo lo acota a las entradas: `picking_type_code` **no es filtrable**, así
que el filtro de "solo recepciones" no se puede desactivar desde la petición.
Gracias a eso, `partner_id` significa siempre *Proveedor* aquí. Lo que sale
hacia las farmacias se consulta por `sale.order`.

El filtro por defecto se aplica **leaf a leaf**: preguntar por las recepciones
ya hechas desactiva el filtro de estado, pero no el de "solo entradas".

> Esto sustituye al hueco que el módulo tenía antes. *"¿Qué está pendiente de
> recibir?"* parecía inviable porque exigía comparar `qty_received` contra
> `product_qty`, y los dominios de Odoo no comparan dos campos entre sí. La
> respuesta estaba en otro sitio: Odoo ya mantiene ese estado en el albarán.

### Fuera de alcance por ahora

Stock disponible y reposición (`qty_available`, `incoming_qty`): se pueden
filtrar y listar, pero **no agregar**, porque son campos calculados sin
almacenar. Haría falta marcarlos en el catálogo como "solo listar".

## Estructura

```
ai_data_chat/
├── models/          ai.chat.session, ai.chat.message, ai.chat.action, ai.chat.responder
├── services/        catálogos (lectura y escritura), herramientas, periodos,
│                    prompt y cliente LLM
├── controllers/     endpoints JSON que consume la interfaz
├── static/src/      acción cliente OWL (chat)
├── views/           menús y vistas backend de respaldo
├── security/        permisos y reglas de registro
└── tools/           utilidades para probar desde odoo-bin shell
```

## Licencia

LGPL-3. Ver el fichero [LICENSE](LICENSE).
