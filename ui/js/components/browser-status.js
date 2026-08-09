import { escapeHtml, shortId } from "../utils/format.js";

export function browserStatus(browser) {
  const state = browser?.state || {};
  const connected = browser?.realtimeStatus === "connected";
  const owner = state.owner || browser?.owner || "agent";
  const control = state.control_state || browser?.controlState || "AGENT_CONTROL";
  return `<div class="browser-status">
    <div class="browser-status-row">
      <span class="status-dot ${connected ? "online" : ""}"></span>
      <strong>${connected ? "Live" : "Connecting"}</strong>
      <span class="chip gold">${escapeHtml(control)}</span>
    </div>
    <div class="browser-status-meta">
      <span>${owner === "user" ? "You control the browser" : "Agent controls the browser"}</span>
      ${browser?.sessionId ? `<span>Session ${escapeHtml(shortId(browser.sessionId))}</span>` : ""}
    </div>
  </div>`;
}
