import { icon } from "./icons.js";
import { escapeHtml } from "../utils/format.js";
import { browserStatus } from "./browser-status.js";
import { browserViewer } from "./browser-viewer.js";
import { browserControls } from "./browser-controls.js";
import { browserActivity } from "./browser-activity.js";

function browserTabs(browser) {
  const tabs = browser?.state?.tabs || [];
  if (!tabs.length) return "";
  return `<div class="browser-tabs" aria-label="Open browser tabs">${tabs.map(tab => `<div class="browser-tab ${tab.active ? "active" : ""}" title="${escapeHtml(tab.url || "")}"><span>${escapeHtml(tab.title || tab.url || `Tab ${tab.index + 1}`)}</span></div>`).join("")}</div>`;
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
