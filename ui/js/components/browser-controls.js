import { icon } from "./icons.js";
import { escapeHtml } from "../utils/format.js";

export function browserControls(browser) {
  const state = browser?.state || {};
  const owner = state.owner || browser?.owner || "agent";
  const ready = Boolean(browser?.sessionId);
  const userControl = owner === "user";
  const url = state.url && state.url !== "about:blank" ? state.url : "";
  return `<div class="browser-controls">
    <div class="browser-address-row">
      <button class="browser-nav-button" data-browser-input="back" title="Back" ${!userControl ? "disabled" : ""}>${icon("back")}</button>
      <button class="browser-nav-button" data-browser-input="forward" title="Forward" ${!userControl ? "disabled" : ""}>${icon("forward")}</button>
      <button class="browser-nav-button" data-browser-input="refresh" title="Refresh" ${!userControl ? "disabled" : ""}>${icon("refresh")}</button>
      <input id="browser-address" class="browser-address" value="${escapeHtml(url)}" placeholder="https://example.com" ${!userControl ? "readonly" : ""} aria-label="Browser address" />
    </div>
    <div class="browser-control-actions">
      ${userControl
        ? `<button class="gold-button" data-action="return-browser-control" ${!ready ? "disabled" : ""}>${icon("handoff")} Return Control to Agent</button>`
        : `<button class="gold-button" data-action="take-browser-control" ${!ready ? "disabled" : ""}>${icon("cursor")} Take Control</button>`}
      <span class="browser-control-note">${userControl ? "Click the live frame, scroll, or type into the focused field. Sensitive text is never written to the activity log." : "You can watch every browser action while Nisr works."}</span>
    </div>
    ${userControl ? `<div class="browser-input-row"><input id="browser-user-text" type="password" autocomplete="off" placeholder="Type into the focused browser field (not logged)" aria-label="Private browser input" /><button class="secondary-button" data-action="send-browser-text">Type</button><button class="secondary-button" data-browser-key="Tab">Tab</button><button class="secondary-button" data-browser-key="Enter">Enter</button><button class="secondary-button" data-browser-key="Escape">Esc</button></div>` : ""}
  </div>`;
}
