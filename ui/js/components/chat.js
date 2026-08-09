import { icon } from "./icons.js";
import { escapeHtml, shortId } from "../utils/format.js";

function message(item) {
  const role = item.role === "user" ? "user" : "agent";
  const meta = item.meta || {};
  return `<div class="message ${role}"><div class="avatar ${role}">${icon(role === "user" ? "send" : "eagle")}</div><div><div class="bubble">${escapeHtml(item.text)}</div><div class="message-meta">${meta.label ? `<span>${escapeHtml(meta.label)}</span>` : ""}${meta.sessionId ? `<span>Session ${escapeHtml(shortId(meta.sessionId))}</span>` : ""}${meta.mode ? `<span>${escapeHtml(meta.mode)}</span>` : ""}</div></div></div>`;
}

export function chatView(state) {
  const run = state.lastRun;
  return `<section class="view ${state.activeView === "chat" ? "active" : ""}" data-section="chat">
    <div class="hero-card"><div><div class="hero-eyebrow">Production Agent</div><h2>Command Nisr.</h2><p>Describe the outcome you want. Nisr will plan the work, select tools, execute the task, verify the result, and return evidence.</p></div><div class="hero-orbit">${icon("eagle")}</div></div>
    <div class="grid"><div class="panel gold-border chat-panel"><div class="panel-head"><div class="panel-title">${icon("chat")} Agent conversation</div><span class="chip ${state.busy ? "gold" : "success"}">${state.busy ? "Executing" : "Ready"}</span></div>
      <div class="messages" id="messages">${state.messages.map(message).join("")}</div>
      <form class="composer" id="objective-form"><div class="composer-box"><textarea id="objective-input" name="objective" placeholder="Example: Research the repository, identify the highest-risk issue, and propose the smallest verified fix." required ${state.busy ? "disabled" : ""}></textarea><div class="composer-actions"><span class="hint">Enter to send · Shift+Enter for a new line</span><button class="gold-button" type="submit" ${state.busy ? "disabled" : ""}>${icon("send")} ${state.busy ? "Running…" : "Run objective"}</button></div></div></form>
    </div>
    <aside class="panel"><div class="panel-head"><div class="panel-title">${icon("tasks")} Last execution</div></div><div class="panel-body"><div class="metric-grid"><div class="metric"><div class="metric-label">Mode</div><div class="metric-value gold">${escapeHtml(run?.mode || "READY")}</div></div><div class="metric"><div class="metric-label">Steps</div><div class="metric-value">${run?.step_count ?? 0}</div></div><div class="metric"><div class="metric-label">Completed</div><div class="metric-value">${run?.completed_tasks?.length ?? 0}</div></div><div class="metric"><div class="metric-label">Blocked</div><div class="metric-value">${run?.blocked_tasks?.length ?? 0}</div></div></div>${run?.session_id ? `<div class="data-sub" style="margin-top:14px">Session ${escapeHtml(shortId(run.session_id))}</div>` : ""}</div></aside></div>
  </section>`;
}
