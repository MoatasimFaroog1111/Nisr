import { icon } from "./icons.js";
import { escapeHtml } from "../utils/format.js";
import { browserStatus } from "./browser-status.js";
import { browserViewer } from "./browser-viewer.js";
import { browserControls } from "./browser-controls.js";
import { browserActivity } from "./browser-activity.js";

function browserTabs(browser) {
  const tabs = browser?.state?.tabs || [];
  if (!tabs.length) return "";
  return `<div class="browser-tabs">${tabs.map(tab => `<button class="browser-tab ${tab.active ? "active" : ""}" data-browser-tab="${escapeHtml(tab.id)}" title="${escapeHtml(tab.url || "")}"><span>${escapeHtml(tab.title || tab.url || `Tab ${tab.index + 1}`)}</span>${tabs.length > 1 ? `<span class="tab-close" data-close-browser-tab="${escapeHtml(tab.id)}">×</span>` : ""}</button>`).join("")}</div>`;
}

export function computerPanel(state) {
  const browser = state.browser || {};
  return `<aside class="panel gold-border computer-panel">
    <div class="panel-head computer-head"><div class="panel-title">${icon("computer")} Computer</div>${browserStatus(browser)}</div>
    ${browserTabs(browser)}
    <div class="computer-body">
      ${browserControls(browser)}
      ${browserViewer(browser)}
      ${browserActivity(browser)}
    </div>
  </aside>`;
}
