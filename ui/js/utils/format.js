export function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

export function shortId(value = "") {
  const text = String(value);
  return text.length > 14 ? `${text.slice(0, 8)}…${text.slice(-4)}` : text || "—";
}

export function safeJson(value) {
  try { return JSON.stringify(value, null, 2); } catch { return String(value); }
}
