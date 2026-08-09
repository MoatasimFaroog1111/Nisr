import { api } from "./services/api-client.js";
import { BrowserRealtimeClient } from "./services/browser-socket.js";
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
const browserSocket = new BrowserRealtimeClient({
  onEvent: handleBrowserEvent,
  onStatus: status => updateBrowser({ realtimeStatus: status }),
});

function toast(message, type = "info") {
  const node = document.createElement("div");
  node.className = `toast ${type === "error" ? "error" : ""}`;
  node.textContent = message;
  toastRoot.append(node);
  setTimeout(() => node.remove(), 4200);
}

function updateBrowser(patch, silent = false) {
  const updater = state => ({
    ...state,
    browser: { ...state.browser, ...patch },
  });
  silent ? store.updateSilent(updater) : store.update(updater);
}

function updateBrowserState(patch) {
  const current = store.state.browser.state || {};
  updateBrowser({
    state: { ...current, ...patch },
    owner: patch.owner ?? current.owner ?? store.state.browser.owner,
    controlState: patch.control_state ?? current.control_state ?? store.state.browser.controlState,
  });
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

function applyFrame(event) {
  const data = event.data || {};
  if (!data.data_base64) return;
  const frame = {
    src: `data:${data.mime_type || "image/jpeg"};base64,${data.data_base64}`,
    width: data.width || 1280,
    height: data.height || 720,
    capturedAt: data.captured_at || event.timestamp,
  };
  const existing = document.querySelector("#browser-frame");
  updateBrowser({ frame }, Boolean(existing));
  if (existing) {
    existing.src = frame.src;
    const viewer = document.querySelector("#browser-viewer");
    if (viewer) {
      viewer.dataset.frameWidth = String(frame.width);
      viewer.dataset.frameHeight = String(frame.height);
    }
  }
}

function addBrowserActivity(event) {
  if (["browser.frame", "browser.pong"].includes(event.type)) return;
  const compact = {
    type: event.type,
    message: event.message || event.type,
    actor: event.actor || "system",
    timestamp: event.timestamp || new Date().toISOString(),
  };
  const activity = [...(store.state.browser.activity || []), compact].slice(-40);
  updateBrowser({ activity });
}

function realtimeStatePatch(data = {}) {
  return {
    url: data.url ?? store.state.browser.state?.url,
    title: data.title ?? store.state.browser.state?.title,
    loading: data.loading ?? store.state.browser.state?.loading,
    tabs: data.tabs ?? store.state.browser.state?.tabs,
    owner: data.owner ?? store.state.browser.state?.owner,
    control_state: data.control_state ?? store.state.browser.state?.control_state,
  };
}

function handleBrowserEvent(event) {
  if (!event || !event.type) return;
  if (event.type === "browser.frame") {
    applyFrame(event);
    return;
  }
  const data = event.data || {};
  if (["browser.started", "browser.loaded", "browser.url_changed"].includes(event.type)) {
    updateBrowserState(realtimeStatePatch(data));
  } else if (event.type === "browser.control_changed") {
    updateBrowserState(realtimeStatePatch(data));
    updateBrowser({ takeoverRequested: data.owner === "user" ? store.state.browser.takeoverRequested : false });
  } else if (event.type === "browser.session_ready") {
    updateBrowser({ owner: data.owner || "agent", controlState: data.control_state || "AGENT_CONTROL" });
  } else if (event.type === "user_takeover_requested") {
    updateBrowser({ takeoverRequested: true, takeoverReason: data.reason || event.message });
    const duplicate = store.state.messages.at(-1)?.meta?.label === "User input required";
    if (!duplicate) {
      store.update(state => ({
        ...state,
        messages: [...state.messages, {
          role: "agent",
          text: "Your input is required to continue this step. Use Take Control in the Computer panel.",
          meta: { label: "User input required", sessionId: event.session_id, mode: "WAITING_USER" },
        }],
      }));
    }
  } else if (event.type === "browser.closed") {
    updateBrowser({ state: null, frame: null, owner: "agent", controlState: "AGENT_CONTROL" });
  }
  addBrowserActivity(event);
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
  const waitingApproval = result.mode === "WAITING_APPROVAL";
  const waitingUser = result.mode === "WAITING_USER" || result.run_status === "WAITING_USER";
  store.update(state => ({
    ...state,
    busy: false,
    lastRun: result,
    activeView: waitingApproval ? "approvals" : "chat",
    browser: {
      ...state.browser,
      takeoverRequested: waitingUser || state.browser.takeoverRequested,
      takeoverReason: waitingUser ? (result.waiting_reason || state.browser.takeoverReason) : state.browser.takeoverReason,
    },
    messages: [...state.messages, resultMessage(result, waitingUser ? "Waiting for your input" : label)],
  }));
}

async function closeCurrentBrowser() {
  const { sessionId, token } = store.state.browser;
  browserSocket.disconnect();
  if (sessionId && token) {
    try { await api.closeBrowserSession(sessionId, token); }
    catch { /* cleanup is best-effort */ }
  }
  updateBrowser({
    sessionId: null,
    token: null,
    realtimeStatus: "disconnected",
    owner: "agent",
    controlState: "AGENT_CONTROL",
    state: null,
    frame: null,
    activity: [],
    takeoverRequested: false,
    takeoverReason: null,
  });
}

async function createLiveBrowser() {
  await closeCurrentBrowser();
  const created = await api.createBrowserSession();
  updateBrowser({
    sessionId: created.session_id,
    token: created.token,
    owner: created.owner || "agent",
    controlState: created.control_state || "AGENT_CONTROL",
    state: { owner: created.owner || "agent", control_state: created.control_state || "AGENT_CONTROL", tabs: [], url: "about:blank", title: "" },
    frame: null,
    activity: [],
  });
  browserSocket.connect(created.session_id, created.token);
  return created;
}

async function runObjective(objective) {
  if (store.state.lastRun?.run_status === "WAITING_USER" || browserHasUserControl()) {
    toast("Return browser control to Nisr before starting another objective.", "error");
    return;
  }
  store.update(state => ({ ...state, busy: true, messages: [...state.messages, { role: "user", text: objective, meta: { label: "Objective" } }] }));
  try {
    const browser = await createLiveBrowser();
    const result = await api.run(objective, [], [], browser.session_id, browser.token);
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

async function denyAndClose(requestId) {
  store.set({ busy: true });
  try {
    const response = await api.deny(requestId);
    if (response.state) {
      applyResult(response.state, "Stopped after denial");
      toast("Approval denied. The protected action was not executed.");
    } else {
      store.set({ busy: false });
      toast("Approval denied");
    }
    await Promise.allSettled([loadApprovals(), loadAudit()]);
  } catch (error) {
    store.set({ busy: false });
    toast(`Deny failed: ${error.message}`, "error");
  }
}

async function takeBrowserControl() {
  const { sessionId, token } = store.state.browser;
  if (!sessionId || !token) return;
  try {
    const response = await api.takeBrowserControl(sessionId, token);
    updateBrowser({ state: response.state, owner: response.state.owner, controlState: response.state.control_state });
    toast("You now control the same browser session.");
    requestAnimationFrame(() => document.querySelector("#browser-viewer")?.focus());
  } catch (error) { toast(`Take control failed: ${error.message}`, "error"); }
}

async function returnBrowserControl() {
  const { sessionId, token } = store.state.browser;
  if (!sessionId || !token) return;
  store.set({ busy: true });
  try {
    const response = await api.returnBrowserControl(sessionId, token);
    updateBrowser({
      state: response.browser,
      owner: response.browser.owner,
      controlState: response.browser.control_state,
      takeoverRequested: false,
      takeoverReason: null,
    });
    if (response.resumed && response.state) applyResult(response.state, "Continued after user takeover");
    else store.set({ busy: false });
    toast("Control returned to Nisr. Continuing from the current browser state.");
  } catch (error) {
    store.set({ busy: false });
    toast(`Return control failed: ${error.message}`, "error");
  }
}

function browserHasUserControl() {
  return (store.state.browser.state?.owner || store.state.browser.owner) === "user";
}

function sendBrowser(action, payload = {}) {
  if (!browserHasUserControl()) return false;
  const sent = browserSocket.sendUserInput(action, payload);
  if (!sent) toast("Live browser channel is reconnecting. Try again in a moment.", "error");
  return sent;
}

function bindBrowserViewer() {
  const viewer = document.querySelector("#browser-viewer");
  const image = document.querySelector("#browser-frame");
  if (!viewer || !browserHasUserControl()) return;

  image?.addEventListener("click", event => {
    const rect = image.getBoundingClientRect();
    const width = Number(viewer.dataset.frameWidth || image.naturalWidth || 1280);
    const height = Number(viewer.dataset.frameHeight || image.naturalHeight || 720);
    const x = Math.max(0, Math.min(width, (event.clientX - rect.left) * width / rect.width));
    const y = Math.max(0, Math.min(height, (event.clientY - rect.top) * height / rect.height));
    sendBrowser("pointer.click", { x, y });
    viewer.focus();
  });

  viewer.addEventListener("wheel", event => {
    event.preventDefault();
    sendBrowser("scroll", { delta_x: event.deltaX, delta_y: event.deltaY });
  }, { passive: false });

  viewer.addEventListener("keydown", event => {
    const allowed = new Set(["Tab", "Enter", "Escape", "Backspace", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "PageUp", "PageDown", "Home", "End"]);
    if (!allowed.has(event.key)) return;
    event.preventDefault();
    sendBrowser("key.press", { key: event.key });
  });
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

  document.querySelectorAll("[data-approve]").forEach(button => button.addEventListener("click", async () => approveAndResume(button.dataset.approve)));
  document.querySelectorAll("[data-deny]").forEach(button => button.addEventListener("click", async () => denyAndClose(button.dataset.deny)));
  document.querySelector('[data-action="take-browser-control"]')?.addEventListener("click", takeBrowserControl);
  document.querySelector('[data-action="return-browser-control"]')?.addEventListener("click", returnBrowserControl);

  document.querySelectorAll("[data-browser-input]").forEach(button => button.addEventListener("click", () => sendBrowser(button.dataset.browserInput, {})));
  document.querySelectorAll("[data-browser-key]").forEach(button => button.addEventListener("click", () => sendBrowser("key.press", { key: button.dataset.browserKey })));
  document.querySelectorAll("[data-browser-tab]").forEach(button => button.addEventListener("click", event => {
    if (event.target.closest("[data-close-browser-tab]")) return;
    sendBrowser("switchTab", { tab_id: button.dataset.browserTab });
  }));
  document.querySelectorAll("[data-close-browser-tab]").forEach(button => button.addEventListener("click", event => {
    event.stopPropagation();
    sendBrowser("closeTab", { tab_id: button.dataset.closeBrowserTab });
  }));

  const browserAddress = document.querySelector("#browser-address");
  browserAddress?.addEventListener("keydown", event => {
    if (event.key === "Enter" && browserHasUserControl()) {
      event.preventDefault();
      sendBrowser("navigate", { url: browserAddress.value.trim() });
    }
  });
  const privateText = document.querySelector("#browser-user-text");
  const typePrivate = () => {
    if (!privateText?.value) return;
    const text = privateText.value;
    privateText.value = "";
    sendBrowser("text.insert", { text });
  };
  document.querySelector('[data-action="send-browser-text"]')?.addEventListener("click", typePrivate);
  privateText?.addEventListener("keydown", event => {
    if (event.key === "Enter") { event.preventDefault(); typePrivate(); }
  });
  bindBrowserViewer();

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

window.addEventListener("beforeunload", () => browserSocket.disconnect());
store.subscribe(render);
render(store.state);
loadHealth();
