import { icon } from "./icons.js";
import { escapeHtml } from "../utils/format.js";

export function tasksView(state) {
  const tasks = state.lastRun?.plan?.tasks || [];
  return `<section class="view ${state.activeView === "tasks" ? "active" : ""}" data-section="tasks"><div class="section-head"><div><h2>Execution tasks</h2><p>The latest plan produced by Nisr's planning service.</p></div><span class="chip gold">${tasks.length} task${tasks.length === 1 ? "" : "s"}</span></div><div class="card-list">${tasks.length ? tasks.map((task,index) => `<div class="data-card task-row"><div class="task-number">${index + 1}</div><div class="data-main"><div class="data-title">${escapeHtml(task.title || task.id)}</div><div class="data-sub">${escapeHtml(task.description || "No description")}</div>${task.verification?.length ? `<div class="data-sub">Verification: ${escapeHtml(task.verification.join(" · "))}</div>` : ""}</div><span class="chip ${task.status === "completed" ? "success" : task.status === "blocked" ? "danger" : "gold"}">${escapeHtml(task.status || "pending")}</span></div>`).join("") : `<div class="empty">${icon("tasks")}<div>No task plan yet. Run an objective from Chat.</div></div>`}</div></section>`;
}
