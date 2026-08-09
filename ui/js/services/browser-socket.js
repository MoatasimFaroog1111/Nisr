export class BrowserRealtimeClient {
  constructor({ onEvent, onStatus } = {}) {
    this.onEvent = onEvent || (() => {});
    this.onStatus = onStatus || (() => {});
    this.socket = null;
    this.sessionId = null;
    this.token = null;
    this.closedByClient = false;
    this.retry = 0;
    this.retryTimer = null;
  }

  connect(sessionId, token) {
    this.disconnect(false);
    this.sessionId = sessionId;
    this.token = token;
    this.closedByClient = false;
    this.#open();
  }

  #open() {
    if (!this.sessionId || !this.token || this.closedByClient) return;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocol}//${window.location.host}/ws/browser/${encodeURIComponent(this.sessionId)}`;
    this.onStatus("connecting");
    const socket = new WebSocket(url, ["nisr-browser", this.token]);
    this.socket = socket;
    socket.addEventListener("open", () => {
      this.retry = 0;
      this.onStatus("connected");
    });
    socket.addEventListener("message", event => {
      try { this.onEvent(JSON.parse(event.data)); }
      catch { this.onEvent({ type: "browser.error", message: "Invalid browser realtime event" }); }
    });
    socket.addEventListener("close", () => {
      if (this.socket === socket) this.socket = null;
      this.onStatus("disconnected");
      if (!this.closedByClient) this.#scheduleReconnect();
    });
    socket.addEventListener("error", () => this.onStatus("error"));
  }

  #scheduleReconnect() {
    clearTimeout(this.retryTimer);
    const delay = Math.min(10000, 500 * (2 ** this.retry));
    this.retry += 1;
    this.retryTimer = setTimeout(() => this.#open(), delay);
  }

  sendUserInput(action, payload = {}) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return false;
    this.socket.send(JSON.stringify({ type: "browser.user_input", action, payload }));
    return true;
  }

  ping() {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return;
    this.socket.send(JSON.stringify({ type: "browser.ping" }));
  }

  disconnect(markClosed = true) {
    clearTimeout(this.retryTimer);
    if (markClosed) this.closedByClient = true;
    if (this.socket) {
      this.socket.close(1000, "client disconnect");
      this.socket = null;
    }
  }
}
