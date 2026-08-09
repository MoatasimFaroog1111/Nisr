import { icon } from "./icons.js";
import { escapeHtml, formatDate } from "../utils/format.js";

export function artifactsView(state) {
  const rows = state.artifacts || [];
  return `<section class="view ${state.activeView === "artifacts" ? "active" : ""}" data-section="artifacts"><div class="section-head"><div><h2>Artifacts</h2><p>Files and outputs produced by agent workflows.</p></div><button class="secondary-button" data-action="load-artifacts">${icon("refresh")} Refresh</button></div><div class="card-list">${rows.length ? rows.map(row => `<div class="data-card"><div class="data-main"><div class="data-title">${escapeHtml(row.name || row.path || "Artifact")}</div><div class="data-sub">${row.size != null ? `${escapeHtml(row.size)} bytes` : ""}${row.created_at ? ` · ${escapeHtml(formatDate(row.created_at))}` : ""}${row.sha256 ? ` · SHA ${escapeHtml(String(row.sha256).slice(0,12))}…` : ""}</div></div><span class="chip gold">artifact</span></div>`).join("") : `<div class="empty">${icon("artifacts")}<div>No generated artifacts yet.</div></div>`}</div></section>`;
}
