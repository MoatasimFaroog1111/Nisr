import { icon } from "./icons.js";
import { escapeHtml, shortId } from "../utils/format.js";
import { computerPanel } from "./computer-panel.js";

function message(item) {
  const role = item.role === "user" ? "user" : "agent";
  const meta = item.meta || {};
  return `<div class="message ${role}"><div class="avatar ${role}">${icon(role === "user" ? "send" : "eagle")}</div><div><div class="bubble">${escapeHtml(item.text)}</div><div class="message-meta">${meta.label ? `<span>${escapeHtml(meta.label)}</span>` : ""}${meta.sessionId ? `<span>Session ${escapeHtml(shortId(meta.sessionId))}</span>` : ""}${meta.mode ? `<span>${escapeHtml(meta.mode)}</span>` : ""}</div></div></div>`;
}

function executionStrip(run) {
  if (!run) return `<div class="execution-strip"><span>Ready for a new objective</span></div>`;
  const budget = run.provider_budget || {};
  const runTokens = Number.isFinite(budget.run_tokens_used) ? `<span>Tokens ${budget.run_tokens_used}/${budget.run_token_budget ?? "—"}</span>` : "";
  const providerRemaining = Number.isFinite(budget.provider_remaining_tokens) ? `<span>TPM remaining ${budget.provider_remaining_tokens}</span>` : "";
  return `<div class="execution-strip"><span><strong>${escapeHtml(run.run_status || run.mode || "READY")}</strong></span><span>Steps ${run.step_count ?? 0}</span><span>Completed ${run.completed_tasks?.length ?? 0}</span><span>Blocked ${run.blocked_tasks?.length ?? 0}</span>${runTokens}${providerRemaining}${run.session_id ? `<span>Session ${escapeHtml(shortId(run.session_id))}</span>` : ""}</div>`;
}

export function chatView(state) {
  const run = state.lastRun;
  return `<section class="view ${state.activeView === "chat" ? "active" : ""}" data-section="chat">
    <div class="hero-card"><div><div class="hero-eyebrow">Production Agent</div><h2>Command Nisr.</h2><p>Describe the outcome you want. Watch the live Computer panel while Nisr browses, and take control safely whenever your input is required.</p></div><div class="hero-orbit">${icon("eagle")}</div></div>
    <div class="workbench-grid">
      <div class="panel gold-border chat-panel"><div class="panel-head"><div class="panel-title">${icon("chat")} Chat</div><span class="chip ${state.busy ? "gold" : run?.run_status === "WAITING_USER" ? "danger" : "success"}">${state.busy ? "Executing" : run?.run_status === "WAITING_USER" ? "Waiting for you" : "Ready"}</span></div>
        ${executionStrip(run)}
        <div class="messages" id="messages">${state.messages.map(message).join("")}</div>
        <form class="composer" id="objective-form"><div class="composer-box"><textarea id="objective-input" name="objective" placeholder="Example: Open a site, research the options, and continue until the objective is verified." required ${state.busy ? "disabled" : ""}></textarea><div class="composer-actions"><span class="hint">Enter to send · Shift+Enter for a new line</span><button class="gold-button" type="submit" ${state.busy ? "disabled" : ""}>${icon("send")} ${state.busy ? "Running…" : "Run objective"}</button></div></div></form>
      </div>
      ${computerPanel(state)}
    </div>
  </section>`;
}
