import { escapeHtml } from "../utils/format.js";

export function browserActivity(browser) {
  const events = (browser?.activity || []).slice(-10).reverse();
  return `<div class="browser-activity"><div class="browser-section-label">Activity</div><div class="browser-activity-list">
    ${events.length ? events.map(event => `<div class="browser-activity-item"><span class="activity-dot"></span><div><strong>${escapeHtml(event.message || event.type || "Browser event")}</strong><span>${escapeHtml((event.type || "").replaceAll("browser.", ""))}</span></div></div>`).join("") : `<div class="browser-activity-empty">Browser actions will appear here without exposing model chain-of-thought.</div>`}
  </div></div>`;
}
