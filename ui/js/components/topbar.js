import { icon } from "./icons.js";

const labels = {
  chat: ["Command Center", "Plan, execute and verify an objective"], tasks: ["Tasks", "Inspect the latest execution plan"],
  approvals: ["Approvals", "Control state-changing operations"], artifacts: ["Artifacts", "Review generated outputs"],
  audit: ["Audit Log", "Trace agent and tool activity"], settings: ["Runtime", "Production status and safe configuration"],
};

export function topbar(state) {
  const [title, subtitle] = labels[state.activeView] || labels.chat;
  return `<header class="topbar"><div class="topbar-title"><h1><span class="mobile-brand">Nisr · </span>${title}</h1><p>${subtitle}</p></div><div class="topbar-actions"><button class="icon-button" data-action="refresh" aria-label="Refresh">${icon("refresh")}</button><a class="icon-button" href="/docs" target="_blank" rel="noreferrer" aria-label="Open API docs">${icon("external")}</a></div></header>`;
}
