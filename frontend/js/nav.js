/* Renders the shared sidebar into any element with id="sidebar-root",
   and highlights the current page link. */

const NAV_LINKS = [
  { href: "home.html", icon: "🏠", label: "Home", section: "Overview" },
  { href: "upload.html", icon: "📤", label: "Upload Statements", section: "Overview" },
  { href: "transactions.html", icon: "📄", label: "Transactions", section: "Overview" },
  { href: "labels.html", icon: "🏷️", label: "Labels", section: "Intelligence" },
  { href: "classification.html", icon: "🧩", label: "Classification", section: "Intelligence" },
  { href: "categories.html", icon: "🗂️", label: "Categories", section: "Intelligence" },
  { href: "predictions.html", icon: "🔮", label: "Predict a Transaction", section: "Intelligence" },
  { href: "trends.html", icon: "📈", label: "Trends & Patterns", section: "Analytics" },
  { href: "monitoring.html", icon: "🛰️", label: "Monitoring", section: "Analytics" },
  { href: "feedback.html", icon: "💬", label: "Feedback", section: "Support" },
  { href: "about.html", icon: "ℹ️", label: "About", section: "Support" },
];

function renderSidebar() {
  const root = document.getElementById("sidebar-root");
  if (!root) return;
  const current = location.pathname.split("/").pop() || "home.html";
  const user = API.currentUser() || { full_name: "Guest User", role: "analyst" };
  const initials = (user.full_name || "U").split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase();

  let sections = {};
  NAV_LINKS.forEach(l => {
    sections[l.section] = sections[l.section] || [];
    sections[l.section].push(l);
  });

  let linksHtml = "";
  Object.entries(sections).forEach(([section, links]) => {
    linksHtml += `<div class="nav-section-label">${section}</div>`;
    links.forEach(l => {
      linksHtml += `<a class="nav-link ${l.href === current ? "active" : ""}" href="${l.href}">
        <span class="ic">${l.icon}</span><span>${l.label}</span>
      </a>`;
    });
  });

  root.innerHTML = `
    <div class="brand">
      <div class="brand-mark">M</div>
      <div>
        <div class="brand-name">M-Pesa Intel</div>
        <div class="brand-sub">Transaction Intelligence</div>
      </div>
    </div>
    <nav style="flex:1; overflow-y:auto;">${linksHtml}</nav>
    <div class="sidebar-footer">
      <div class="user-chip">
        <div class="user-avatar">${initials}</div>
        <div style="flex:1; min-width:0;">
          <div class="user-name">${user.full_name}</div>
          <div class="user-role">${user.role || "analyst"}</div>
        </div>
        <button class="btn btn-secondary btn-sm" onclick="logout()" title="Log out">⏻</button>
      </div>
    </div>
  `;
}

document.addEventListener("DOMContentLoaded", () => {
  if (document.getElementById("sidebar-root")) {
    requireAuth();
    renderSidebar();
  }
});
