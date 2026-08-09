import { icon } from "./icons.js";

const items = [
  ["chat", "Chat", "chat"], ["tasks", "Tasks", "tasks"], ["approvals", "Approvals", "approvals"],
  ["artifacts", "Artifacts", "artifacts"], ["audit", "Audit", "audit"], ["settings", "Settings", "settings"],
];

export function sidebar(state) {
  const online = Boolean(state.health?.ok);
  return `<aside class="sidebar">
    <div class="brand"><div class="brand-mark">${icon("eagle")}</div><div class="brand-copy"><div class="brand-name">Nisr</div><div class="brand-sub">Autonomous Agent</div></div></div>
    <nav class="nav-list" aria-label="Primary navigation">
      ${items.map(([id,label,ico]) => `<button class="nav-button ${state.activeView === id ? "active" : ""}" data-view="${id}" aria-label="${label}">${icon(ico)}<span class="nav-label">${label}</span></button>`).join("")}
    </nav>
    <div class="sidebar-footer"><div class="status-row"><span class="status-dot ${online ? "online" : ""}"></span><strong>${online ? "Production online" : "Checking service"}</strong></div><div class="version">${state.health?.version ? `Nisr v${state.health.version}` : "Railway production"}</div></div>
  </aside>`;
}
