import { icon } from "./icons.js";
import { escapeHtml, formatDate, safeJson } from "../utils/format.js";

export function auditView(state) {
  const rows = state.audit || [];
  return `<section class="view ${state.activeView === "audit" ? "active" : ""}" data-section="audit"><div class="section-head"><div><h2>Audit trail</h2><p>Operational events recorded by Nisr with secret redaction.</p></div><button class="secondary-button" data-action="load-audit">${icon("refresh")} Refresh</button></div><div class="card-list">${rows.length ? rows.slice().reverse().map(row => `<div class="data-card"><div class="data-main"><div class="data-title">${escapeHtml(row.event || row.type || "Event")}</div><div class="data-sub">${escapeHtml(formatDate(row.timestamp || row.created_at))}${row.session_id ? ` · session ${escapeHtml(String(row.session_id).slice(0,10))}…` : ""}</div>${row.data ? `<details style="margin-top:9px"><summary class="data-sub">Details</summary><pre class="code-block">${escapeHtml(safeJson(row.data))}</pre></details>` : ""}</div></div>`).join("") : `<div class="empty">${icon("audit")}<div>No audit entries loaded.</div></div>`}</div></section>`;
}
