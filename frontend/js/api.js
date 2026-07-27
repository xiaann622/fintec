/* Central API client for the M-Pesa Intelligence System frontend. */

const API = (() => {
  // Set in js/config.js. Empty string "" means "same origin" (used when
  // nginx proxies /api to the backend, e.g. in the docker-compose setup).
  const BASE_URL = typeof window.MPESA_API_BASE !== "undefined"
    ? window.MPESA_API_BASE
    : "http://localhost:8000";

  function token() {
    return localStorage.getItem("mpesa_token");
  }

  function setSession(token_, user) {
    localStorage.setItem("mpesa_token", token_);
    localStorage.setItem("mpesa_user", JSON.stringify(user));
  }

  function clearSession() {
    localStorage.removeItem("mpesa_token");
    localStorage.removeItem("mpesa_user");
  }

  function currentUser() {
    try {
      return JSON.parse(localStorage.getItem("mpesa_user") || "null");
    } catch {
      return null;
    }
  }

  async function request(path, { method = "GET", body, isForm = false, params } = {}) {
    let url = BASE_URL + path;
    if (params) {
      const q = new URLSearchParams(
        Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")
      );
      const qs = q.toString();
      if (qs) url += (url.includes("?") ? "&" : "?") + qs;
    }

    const headers = {};
    const t = token();
    if (t) headers["Authorization"] = `Bearer ${t}`;
    if (!isForm) headers["Content-Type"] = "application/json";

    const res = await fetch(url, {
      method,
      headers,
      body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
    });

    if (res.status === 401) {
      clearSession();
      if (!location.pathname.endsWith("index.html") && location.pathname !== "/") {
        location.href = "index.html";
      }
      throw new Error("Session expired. Please log in again.");
    }

    let data = null;
    try {
      data = await res.json();
    } catch {
      /* no body */
    }

    if (!res.ok) {
      const message = (data && (data.detail || data.message)) || `Request failed (${res.status})`;
      throw new Error(typeof message === "string" ? message : JSON.stringify(message));
    }
    return data;
  }

  return {
    BASE_URL,
    token,
    setSession,
    clearSession,
    currentUser,
    get: (path, params) => request(path, { method: "GET", params }),
    post: (path, body) => request(path, { method: "POST", body }),
    del: (path) => request(path, { method: "DELETE" }),
    upload: (path, formData) => request(path, { method: "POST", body: formData, isForm: true }),

    // Auth
    login: (email, password) => request("/api/auth/login", { method: "POST", body: { email, password } }),
    register: (payload) => request("/api/auth/register", { method: "POST", body: payload }),
    me: () => request("/api/auth/me"),
  };
})();

function requireAuth() {
  if (!API.token()) {
    location.href = "index.html";
  }
}

function logout() {
  API.clearSession();
  location.href = "index.html";
}

function toast(msg, type = "info") {
  let el = document.getElementById("mpesa-toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "mpesa-toast";
    el.style.cssText = `
      position:fixed; bottom:24px; right:24px; z-index:9999; padding:13px 18px;
      border-radius:10px; font-size:13.5px; font-weight:600; max-width:340px;
      box-shadow:0 10px 30px rgba(0,0,0,0.4); transition:opacity .25s, transform .25s;
      font-family: 'Inter', sans-serif;`;
    document.body.appendChild(el);
  }
  const colors = {
    info: ["rgba(76,139,224,0.95)", "#fff"],
    success: ["rgba(31,209,143,0.95)", "#04140f"],
    error: ["rgba(226,87,76,0.95)", "#fff"],
  };
  const [bg, fg] = colors[type] || colors.info;
  el.style.background = bg;
  el.style.color = fg;
  el.textContent = msg;
  el.style.opacity = "1";
  el.style.transform = "translateY(0)";
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => {
    el.style.opacity = "0";
    el.style.transform = "translateY(8px)";
  }, 3200);
}

function fmtMoney(n) {
  if (n === null || n === undefined || isNaN(n)) return "KES 0";
  return "KES " + Number(n).toLocaleString("en-KE", { maximumFractionDigits: 0 });
}

function fmtDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleString("en-KE", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function fmtPct(n) {
  if (n === null || n === undefined) return "—";
  return (n * 100).toFixed(1) + "%";
}
