export class NisrApiClient {
  constructor(baseUrl = "") { this.baseUrl = baseUrl.replace(/\/$/, ""); }

  async request(path, options = {}) {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
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

  health() { return this.request("/health"); }
  readiness() { return this.request("/readiness"); }
  run(objective, constraints = [], approvals = []) {
    return this.request("/run", { method: "POST", body: JSON.stringify({ objective, constraints, approvals }) });
  }
  approvals(status = "") { return this.request(`/approvals${status ? `?status=${encodeURIComponent(status)}` : ""}`); }
  approve(requestId) { return this.request(`/approvals/${encodeURIComponent(requestId)}/approve`, { method: "POST" }); }
  deny(requestId) { return this.request(`/approvals/${encodeURIComponent(requestId)}/deny`, { method: "POST" }); }
  artifacts() { return this.request("/artifacts"); }
  audit() { return this.request("/audit"); }
}

export const api = new NisrApiClient();
