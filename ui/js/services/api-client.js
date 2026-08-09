export class NisrApiClient {
  constructor(baseUrl = "") { this.baseUrl = baseUrl.replace(/\/$/, ""); }

  async request(path, options = {}) {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
    const type = response.headers.get("content-type") || "";
    const payload = type.includes("application/json") ? await response.json() : await response.text();
    if (!response.ok) {
      const structured = typeof payload === "object" && payload ? payload.error : null;
      const detail = typeof payload === "object" && payload ? payload.detail : null;
      const message =
        structured?.message ||
        (typeof detail === "string" ? detail : detail?.message) ||
        (typeof payload === "string" ? payload : payload?.message) ||
        `HTTP ${response.status}`;
      const error = new Error(message);
      error.code = structured?.code || `http_${response.status}`;
      error.requestId = structured?.request_id || null;
      error.retryable = Boolean(structured?.retryable);
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  browserHeaders(token) {
    return token ? { "x-nisr-browser-token": token } : {};
  }

  health() { return this.request("/health"); }
  readiness() { return this.request("/readiness"); }
  run(objective, constraints = [], approvals = [], sessionId = null, browserToken = "") {
    return this.request("/run", {
      method: "POST",
      headers: this.browserHeaders(browserToken),
      body: JSON.stringify({ objective, constraints, approvals, session_id: sessionId }),
    });
  }
  createBrowserSession() {
    return this.request("/browser/sessions", { method: "POST", body: "{}" });
  }
  browserState(sessionId, token) {
    return this.request(`/browser/sessions/${encodeURIComponent(sessionId)}`, { headers: this.browserHeaders(token) });
  }
  takeBrowserControl(sessionId, token) {
    return this.request(`/browser/sessions/${encodeURIComponent(sessionId)}/take-control`, {
      method: "POST",
      headers: this.browserHeaders(token),
      body: "{}",
    });
  }
  returnBrowserControl(sessionId, token) {
    return this.request(`/browser/sessions/${encodeURIComponent(sessionId)}/return-control`, {
      method: "POST",
      headers: this.browserHeaders(token),
      body: "{}",
    });
  }
  closeBrowserSession(sessionId, token) {
    return this.request(`/browser/sessions/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
      headers: this.browserHeaders(token),
    });
  }
  approvals(status = "") { return this.request(`/approvals${status ? `?status=${encodeURIComponent(status)}` : ""}`); }
  approve(requestId) { return this.request(`/approvals/${encodeURIComponent(requestId)}/approve`, { method: "POST" }); }
  deny(requestId) { return this.request(`/approvals/${encodeURIComponent(requestId)}/deny`, { method: "POST" }); }
  artifacts() { return this.request("/artifacts"); }
  audit() { return this.request("/audit"); }
}

export const api = new NisrApiClient();
