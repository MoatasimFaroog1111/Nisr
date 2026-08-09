import { icon } from "./icons.js";
import { escapeHtml } from "../utils/format.js";

export function settingsView(state) {
  const health = state.health || {};
  return `<section class="view ${state.activeView === "settings" ? "active" : ""}" data-section="settings"><div class="section-head"><div><h2>Runtime</h2><p>Safe production information. Secrets remain in Railway Variables.</p></div><a class="secondary-button" href="/docs" target="_blank" rel="noreferrer">${icon("external")} API docs</a></div><div class="settings-grid"><div class="setting-card"><h3>Service</h3><p>${escapeHtml(health.service || "nisr")} · version ${escapeHtml(health.version || "—")}</p></div><div class="setting-card"><h3>Environment</h3><p>Railway production · same-origin API client</p></div><div class="setting-card"><h3>Model credentials</h3><p>Managed server-side through environment variables. Keys are never exposed to this interface.</p></div><div class="setting-card"><h3>Architecture</h3><p>Domain + Application + Ports + Adapters + Infrastructure. UI components communicate only through the API client and state store.</p></div></div></section>`;
}
