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
      const message = typeof payload === "string" ? payload : payload?.detail || payload?.message || `HTTP ${response.status}`;
      throw new Error(message);
    }
    return payload;
  }

  health() { return this.request("/health"); }
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
