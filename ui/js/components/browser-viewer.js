import { icon } from "./icons.js";

export function browserViewer(browser) {
  const frame = browser?.frame;
  const userControl = (browser?.state?.owner || browser?.owner) === "user";
  if (!frame?.src) {
    return `<div class="browser-viewer empty-viewer" id="browser-viewer" tabindex="${userControl ? "0" : "-1"}">
      <div class="viewer-placeholder">${icon("computer", "viewer-placeholder-icon")}<strong>Live browser</strong><span>Waiting for the agent to open a page…</span></div>
    </div>`;
  }
  return `<div class="browser-viewer ${userControl ? "user-control" : ""}" id="browser-viewer" tabindex="${userControl ? "0" : "-1"}" data-frame-width="${frame.width || 1280}" data-frame-height="${frame.height || 720}">
    <img id="browser-frame" src="${frame.src}" alt="Live browser view" draggable="false" />
    ${userControl ? `<div class="viewer-control-badge">You have control</div>` : `<div class="viewer-control-badge agent">Agent control</div>`}
  </div>`;
}
