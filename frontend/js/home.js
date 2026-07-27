async function loadStatCards() {
  const el = document.getElementById("stat-cards");
  try {
    const summary = await API.get("/api/monitoring/summary");
    const cards = [
      {
        label: "Total transactions", value: summary.total_transactions.toLocaleString(),
        icon: "📄", bg: "rgba(76,139,224,0.15)", fg: "#8fb4ee",
      },
      {
        label: "Classification coverage", value: summary.classification_coverage_pct + "%",
        icon: "🎯", bg: "rgba(31,209,143,0.15)", fg: "#1fd18f",
      },
      {
        label: "Avg. model confidence", value: summary.avg_category_confidence ? fmtPct(summary.avg_category_confidence) : "—",
        icon: "🧠", bg: "rgba(232,184,75,0.15)", fg: "#e8b84b",
      },
      {
        label: "Statements uploaded", value: summary.total_uploads.toLocaleString(),
        icon: "📤", bg: "rgba(226,87,76,0.15)", fg: "#ff9b92",
      },
    ];
    el.innerHTML = cards.map(c => `
      <div class="card stat-card">
        <div class="stat-icon" style="background:${c.bg}; color:${c.fg};">${c.icon}</div>
        <div class="stat-label">${c.label}</div>
        <div class="stat-value">${c.value}</div>
      </div>
    `).join("");

    if (!summary.models_ready) {
      toast("ML models are not loaded on the server yet — see backend/models_store/README.md", "error");
    }
  } catch (err) {
    el.innerHTML = `<div class="card empty-state">Could not load summary: ${err.message}</div>`;
  }
}

async function loadCategoryChart() {
  try {
    const rows = await API.get("/api/transactions/facets/categories");
    new Chart(document.getElementById("chart-category"), {
      type: "doughnut",
      data: {
        labels: rows.map(r => r.category),
        datasets: [{ data: rows.map(r => r.count), backgroundColor: rows.map((_, i) => colorFor(i)), borderWidth: 0 }],
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "right" } } },
    });
  } catch (err) { console.error(err); }
}

async function loadMonthlyChart() {
  try {
    const rows = await API.get("/api/trends/monthly-overview");
    const labels = rows.map(r => `${r.year}-${String(r.month).padStart(2, "0")}`);
    new Chart(document.getElementById("chart-monthly"), {
      type: "bar",
      data: {
        labels,
        datasets: [
          { label: "Inflow", data: rows.map(r => r.total_in), backgroundColor: "#1fd18f", borderRadius: 5 },
          { label: "Outflow", data: rows.map(r => r.total_out), backgroundColor: "#e2574c", borderRadius: 5 },
        ],
      },
      options: { ...baseGridOptions(), plugins: { legend: { display: true, position: "top" } } },
    });
  } catch (err) { console.error(err); }
}

async function loadHourChart() {
  try {
    const rows = await API.get("/api/trends/time-of-day");
    new Chart(document.getElementById("chart-hour"), {
      type: "line",
      data: {
        labels: rows.map(r => r.hour + ":00"),
        datasets: [{ label: "Transactions", data: rows.map(r => r.count), borderColor: "#4c8be0", backgroundColor: "rgba(76,139,224,0.15)", fill: true, tension: 0.35, pointRadius: 0 }],
      },
      options: baseGridOptions(),
    });
  } catch (err) { console.error(err); }
}

async function loadWeekendChart() {
  try {
    const rows = await API.get("/api/trends/weekday-vs-weekend");
    new Chart(document.getElementById("chart-weekend"), {
      type: "bar",
      data: {
        labels: rows.map(r => r.bucket),
        datasets: [{ data: rows.map(r => r.count), backgroundColor: ["#1fd18f", "#e8b84b"], borderRadius: 6 }],
      },
      options: { ...baseGridOptions(), indexAxis: "y" },
    });
  } catch (err) { console.error(err); }
}

async function loadRecent() {
  const tbody = document.getElementById("recent-rows");
  try {
    const data = await API.get("/api/transactions", { page: 1, page_size: 8 });
    if (!data.items.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="empty-state">No transactions yet — head to Upload to ingest your first statement.</td></tr>`;
      return;
    }
    tbody.innerHTML = data.items.map(t => `
      <tr>
        <td>${fmtDateTime(t.completion_time)}</td>
        <td style="max-width:280px; overflow:hidden; text-overflow:ellipsis;">${t.details}</td>
        <td>${fmtMoney(t.amount)}</td>
        <td><span class="badge badge-blue">${t.transaction_label || "—"}</span></td>
        <td><span class="badge badge-gold">${t.transaction_classification || "—"}</span></td>
        <td><span class="badge badge-green">${t.transaction_category || "—"}</span></td>
      </tr>
    `).join("");
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">${err.message}</td></tr>`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadStatCards();
  loadCategoryChart();
  loadMonthlyChart();
  loadHourChart();
  loadWeekendChart();
  loadRecent();
});
