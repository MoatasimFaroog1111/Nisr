import { api } from "./services/api-client.js";
import { store } from "./state/store.js";
import { sidebar } from "./components/sidebar.js";
import { topbar } from "./components/topbar.js";
import { chatView } from "./components/chat.js";
import { tasksView } from "./components/tasks.js";
import { approvalsView } from "./components/approvals.js";
import { artifactsView } from "./components/artifacts.js";
import { auditView } from "./components/audit.js";
import { settingsView } from "./components/settings.js";

const app = document.querySelector("#app");
const toastRoot = document.querySelector("#toast-root");

function toast(message, type = "info") {
  const node = document.createElement("div");
  node.className = `toast ${type === "error" ? "error" : ""}`;
  node.textContent = message;
  toastRoot.append(node);
  setTimeout(() => node.remove(), 4200);
}

function render(state) {
  app.innerHTML = `<div class="loading-bar ${state.busy ? "show" : ""}"></div>${sidebar(state)}<main class="workspace">${topbar(state)}<div class="content">${chatView(state)}${tasksView(state)}${approvalsView(state)}${artifactsView(state)}${auditView(state)}${settingsView(state)}</div></main>`;
  bindEvents();
  if (state.activeView === "chat") {
    requestAnimationFrame(() => {
      const messages = document.querySelector("#messages");
      if (messages) messages.scrollTop = messages.scrollHeight;
    });
  }
}

async function loadHealth() {
  try { store.set({ health: await api.health() }); }
  catch (error) { toast(`Health check failed: ${error.message}`, "error"); }
}
async function loadApprovals() {
  try { store.set({ approvals: await api.approvals() }); }
  catch (error) { toast(`Could not load approvals: ${error.message}`, "error"); }
}
async function loadArtifacts() {
  try { store.set({ artifacts: await api.artifacts() }); }
  catch (error) { toast(`Could not load artifacts: ${error.message}`, "error"); }
}
async function loadAudit() {
  try { store.set({ audit: await api.audit() }); }
  catch (error) { toast(`Could not load audit log: ${error.message}`, "error"); }
}

function resultMessage(result, label = "Verified result") {
  const reply = result.final_result || result.evidence?.at(-1) || "Execution finished without a textual result.";
  return {
    role: "agent",
    text: reply,
    meta: { label, sessionId: result.session_id, mode: result.mode },
  };
}

function applyResult(result, label = "Verified result") {
  const waiting = result.mode === "WAITING_APPROVAL";
  store.update(state => ({
    ...state,
    busy: false,
    lastRun: result,
    activeView: waiting ? "approvals" : "chat",
    messages: [...state.messages, resultMessage(result, label)],
  }));
}

async function runObjective(objective) {
  store.update(state => ({ ...state, busy: true, messages: [...state.messages, { role: "user", text: objective, meta: { label: "Objective" } }] }));
  try {
    const result = await api.run(objective, [], []);
    applyResult(result);
    await Promise.allSettled([loadApprovals(), loadArtifacts(), loadAudit()]);
  } catch (error) {
    store.update(state => ({ ...state, busy: false, messages: [...state.messages, { role: "agent", text: `Execution failed: ${error.message}`, meta: { label: "Error" } }] }));
    toast(`Execution failed: ${error.message}`, "error");
  }
}

async function approveAndResume(requestId) {
  store.set({ busy: true });
  try {
    const response = await api.approve(requestId);
    if (response.resumed && response.state) {
      applyResult(response.state, "Resumed after approval");
      toast("Approved. Nisr resumed the same session.");
    } else {
      store.set({ busy: false });
      toast(response.message || "Approval granted");
    }
    await Promise.allSettled([loadApprovals(), loadArtifacts(), loadAudit()]);
  } catch (error) {
    store.set({ busy: false });
    toast(`Approval failed: ${error.message}`, "error");
  }
}

function bindEvents() {
  document.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", async () => {
    const view = button.dataset.view;
    store.set({ activeView: view });
    if (view === "approvals") await loadApprovals();
    if (view === "artifacts") await loadArtifacts();
    if (view === "audit") await loadAudit();
  }));

  document.querySelector('[data-action="refresh"]')?.addEventListener("click", async () => {
    await loadHealth();
    if (store.state.activeView === "approvals") await loadApprovals();
    if (store.state.activeView === "artifacts") await loadArtifacts();
    if (store.state.activeView === "audit") await loadAudit();
    toast("Refreshed");
  });
  document.querySelector('[data-action="load-approvals"]')?.addEventListener("click", loadApprovals);
  document.querySelector('[data-action="load-artifacts"]')?.addEventListener("click", loadArtifacts);
  document.querySelector('[data-action="load-audit"]')?.addEventListener("click", loadAudit);

  document.querySelectorAll("[data-approve]").forEach(button => button.addEventListener("click", async () => {
    await approveAndResume(button.dataset.approve);
  }));
  document.querySelectorAll("[data-deny]").forEach(button => button.addEventListener("click", async () => {
    try { await api.deny(button.dataset.deny); toast("Approval denied"); await loadApprovals(); }
    catch (error) { toast(error.message, "error"); }
  }));

  const form = document.querySelector("#objective-form");
  const input = document.querySelector("#objective-input");
  form?.addEventListener("submit", event => {
    event.preventDefault();
    const objective = input?.value.trim();
    if (objective && !store.state.busy) runObjective(objective);
  });
  input?.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      const objective = input.value.trim();
      if (objective && !store.state.busy) runObjective(objective);
    }
  });
}

store.subscribe(render);
render(store.state);
loadHealth();
