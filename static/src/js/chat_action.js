/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import {
    Component, useState, useRef, onWillStart, onMounted, onPatched, markup,
} from "@odoo/owl";

/**
 * Markdown mínimo -> HTML, para lo que realmente devuelve el modelo:
 * negrita, cursiva, `código`, viñetas y encabezados.
 *
 * El texto incluye datos de la base (nombres de productos, clientes...), así
 * que se ESCAPA primero y solo después se inyectan las etiquetas que genera
 * esta función. Nunca se vuelca HTML venido del modelo o de la BD.
 */
function renderMarkdown(text) {
    const escaped = String(text || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");

    const html = escaped
        // Encabezados "### Titulo" -> negrita (evita mostrar las almohadillas).
        .replace(/^#{1,6}[ \t]+(.*)$/gm, "<strong>$1</strong>")
        // Viñetas "* item" / "- item" al principio de línea.
        .replace(/^[ \t]*[*-][ \t]+/gm, "• ")
        // `código`
        .replace(/`([^`\n]+)`/g, "<code>$1</code>")
        // **negrita** y __negrita__ (antes que la cursiva, si no se la come).
        .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
        .replace(/__([^_\n]+)__/g, "<strong>$1</strong>")
        // *cursiva* y _cursiva_
        .replace(/(^|[^*\w])\*([^*\n]+)\*(?![*\w])/g, "$1<em>$2</em>")
        .replace(/(^|[^_\w])_([^_\n]+)_(?![_\w])/g, "$1<em>$2</em>");

    return markup(html);
}

export class AiDataChat extends Component {
    setup() {
        this.rpc = useService("rpc");
        this.notification = useService("notification");
        this.threadRef = useRef("thread");
        this.state = useState({
            sessions: [],
            activeId: null,
            messages: [],
            input: "",
            loading: false,
            // Id de la acción que se está confirmando/descartando ahora mismo.
            actionBusy: null,
        });

        // Bajar al final solo cuando el hilo ha cambiado, no en cada patch:
        // si no, leer mensajes antiguos es imposible porque cualquier
        // repintado (el spinner, un botón) te devuelve al fondo.
        this.pendingScroll = true;

        onWillStart(async () => {
            await this.loadSessions();
            if (this.state.sessions.length) {
                await this.selectSession(this.state.sessions[0].id);
            } else {
                await this.newSession();
            }
        });

        // `onPatched` NO se dispara en el primer renderizado. Como los
        // mensajes se cargan en `onWillStart`, al abrir la conversación el
        // hilo aparecía por arriba: hace falta `onMounted` también.
        onMounted(() => this.scrollToBottom());
        onPatched(() => {
            if (this.pendingScroll) {
                this.scrollToBottom();
            }
        });
    }

    scrollToBottom() {
        this.pendingScroll = false;
        const el = this.threadRef.el;
        if (!el) {
            return;
        }
        el.scrollTop = el.scrollHeight;
        // Segunda pasada en el siguiente fotograma: las tablas de resultados
        // y las fichas de confirmación cambian la altura después del primer
        // cálculo, y con una sola pasada el hilo se queda a medio bajar.
        requestAnimationFrame(() => {
            const thread = this.threadRef.el;
            if (thread) {
                thread.scrollTop = thread.scrollHeight;
            }
        });
    }

    async loadSessions() {
        const res = await this.rpc("/ai_data_chat/sessions");
        this.state.sessions = res.sessions || [];
    }

    async selectSession(sessionId) {
        this.state.activeId = sessionId;
        const data = await this.rpc(`/ai_data_chat/session/${sessionId}/messages`);
        this.state.messages = data.messages || [];
        this.pendingScroll = true;
    }

    async newSession() {
        const data = await this.rpc("/ai_data_chat/session/new", {});
        await this.loadSessions();
        this.state.activeId = data.session_id;
        this.state.messages = data.messages || [];
        this.pendingScroll = true;
    }

    async send(text) {
        const message = (text ?? this.state.input).trim();
        if (!message || this.state.loading || !this.state.activeId) {
            return;
        }
        this.state.input = "";
        this.state.loading = true;
        try {
            const res = await this.rpc(
                `/ai_data_chat/session/${this.state.activeId}/ask`,
                { message }
            );
            if (res.error) {
                this.notification.add(res.error, { type: "danger" });
                return;
            }
            this.state.messages.push(...(res.messages || []));
            this.pendingScroll = true;
            await this.loadSessions();
        } finally {
            this.state.loading = false;
        }
    }

    // --- Acciones de escritura ---------------------------------------
    // El botón es el único camino hacia la escritura real: el modelo no
    // tiene ninguna herramienta que confirme.
    async confirmAction(message) {
        await this._resolveAction(message, "confirm");
    }

    async discardAction(message) {
        await this._resolveAction(message, "discard");
    }

    async undoAction(message) {
        await this._resolveAction(message, "undo");
    }

    async _resolveAction(message, verb) {
        const action = message.action;
        if (!action || this.state.actionBusy) {
            return;
        }
        this.state.actionBusy = action.id;
        try {
            const res = await this.rpc(`/ai_data_chat/action/${action.id}/${verb}`);
            if (res.action) {
                message.action = res.action;
            }
            if (res.error) {
                this.notification.add(res.error, { type: "danger" });
                return;
            }
            if (res.message) {
                this.state.messages.push(res.message);
                this.pendingScroll = true;
            }
            await this.loadSessions();
        } finally {
            this.state.actionBusy = null;
        }
    }

    onInputKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.send();
        }
    }

    // --- Helpers de render -------------------------------------------
    formatContent(message) {
        return renderMarkdown(message.content);
    }

    resultRows(message) {
        const r = message.tool_result;
        if (!r || !r.ok || !Array.isArray(r.rows) || !r.rows.length) {
            return null;
        }
        const rows = r.rows.slice(0, 15);
        const labels = r.labels || {};
        const columns = Object.keys(rows[0])
            .filter((k) => k !== "__count")
            .map((key, index) => ({
                key,
                label: labels[key] || key,
                numeric: rows.some((row) => typeof row[key] === "number"),
                isLabel: index === 0,
            }));
        return { columns, rows };
    }

    /** Número con separador de miles, para la tabla del documento. */
    num(value, decimals = 2) {
        if (typeof value !== "number") {
            return value ?? "—";
        }
        return value.toLocaleString("en-US", {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
        });
    }

    cell(value, column) {
        if (value === null || value === undefined) {
            return "—";
        }
        if (typeof value === "object") {
            return value.name ?? value.id ?? JSON.stringify(value);
        }
        if (typeof value === "number") {
            const isCount =
                column && (column.key === "__count" || column.key.endsWith("_count"));
            return value.toLocaleString("en-US", {
                minimumFractionDigits: isCount ? 0 : 2,
                maximumFractionDigits: isCount ? 0 : 2,
            });
        }
        return value;
    }
}

AiDataChat.template = "ai_data_chat.ChatAction";

registry.category("actions").add("ai_data_chat.chat", AiDataChat);
