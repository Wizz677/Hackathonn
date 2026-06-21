// Tiny same-origin API client. All calls go to /api (proxied to FastAPI in dev),
// so the app makes no external network requests (spec §1/§10.4).

const BASE = "/api";

async function handle(res) {
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  health: () => fetch(`${BASE}/health`).then(handle),
  dashboard: () => fetch(`${BASE}/dashboard`).then(handle),
  settings: () => fetch(`${BASE}/settings`).then(handle),
  setSettings: (evaluation_date) =>
    fetch(`${BASE}/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ evaluation_date }),
    }).then(handle),

  list: (params = {}) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v)
    ).toString();
    return fetch(`${BASE}/exceptions${q ? `?${q}` : ""}`).then(handle);
  },
  detail: (id) => fetch(`${BASE}/exceptions/${id}`).then(handle),
  action: (id, action) =>
    fetch(`${BASE}/exceptions/${id}/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    }).then(handle),

  report: () => fetch(`${BASE}/report`).then(handle),
  upload: (file, mode) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch(`${BASE}/upload?mode=${mode}`, {
      method: "POST",
      body: fd,
    }).then(handle);
  },

  // Direct download URLs (anchor href targets).
  reportPdfUrl: `${BASE}/report.pdf`,
  reportXlsxUrl: `${BASE}/report.xlsx`,
  reportTxtUrl: `${BASE}/report/download`,
  exportJsonUrl: `${BASE}/export.json`,
  exportCsvUrl: `${BASE}/export.csv`,
};
