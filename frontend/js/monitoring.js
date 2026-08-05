async function loadMonStats() {
  const el = document.getElementById("mon-stat-cards");
  try {
    const s = await API.get("/api/monitoring/summary");
    const cards = [
      { label: "Models loaded", value: s.models_ready ? "Ready ✅" : "Not loaded ⚠️", bg: s.models_ready ? "rgba(31,209,143,0.15)" : "rgba(226,87,76,0.15)", fg: s.models_ready ? "#1fd18f" : "#ff9b92", icon: "🧠" },
      { label: "Unclassified rows", value: s.unclassified_transactions.toLocaleString(), bg: "rgba(232,184,75,0.15)", fg: "#e8b84b", icon: "🕵️" },
      { label: "Classification coverage", value: s.classification_coverage_pct + "%", bg: "rgba(76,139,224,0.15)", fg: "#8fb4ee", icon: "📊" },
      { label: "Failed uploads", value: s.failed_uploads.toLocaleString(), bg: "rgba(226,87,76,0.15)", fg: "#ff9b92", icon: "🚫" },
    ];
    el.innerHTML = cards.map(c => `
      <div class="card stat-card">
        <div class="stat-icon" style="background:${c.bg}; color:${c.fg};">${c.icon}</div>
        <div class="stat-label">${c.label}</div>
        <div class="stat-value">${c.value}</div>
      </div>`).join("");

    if (s.unclassified_transactions > 0 && s.models_ready) {
      const banner = document.createElement("div");
      banner.className = "card";
      banner.style.marginTop = "14px";
      banner.innerHTML = `
        <div class="flex-between">
          <span>⚠️ ${s.unclassified_transactions} transactions were ingested before models were ready.</span>
          <button class="btn btn-secondary btn-sm" onclick="runBackfill()">Run backfill now</button>
        </div>`;
      el.parentElement.insertBefore(banner, el.nextSibling);
    }
  } catch (err) {
    el.innerHTML = `<div class="card empty-state">${err.message}</div>`;
  }
}

async function runBackfill() {
  try {
    toast("Backfilling predictions…", "info");
    const r = await API.post("/api/predictions/backfill", {});
    toast(`Updated ${r.updated} transactions`, "success");
    loadMonStats();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function loadConfidenceTrend() {
  try {
    const rows = await API.get("/api/monitoring/confidence-trend", { days: 30 });
    const days = [...new Set(rows.map(r => r.day))].sort();
    const stages = ["label", "classification", "category"];
    const colors = { label: "#4c8be0", classification: "#e8b84b", category: "#1fd18f" };

    const datasets = stages.map(stage => ({
      label: stage[0].toUpperCase() + stage.slice(1),
      data: days.map(d => {
        const r = rows.find(x => x.day === d && x.stage === stage);
        return r ? r.avg_confidence : null;
      }),
      borderColor: colors[stage], backgroundColor: colors[stage] + "22",
      tension: 0.3, spanGaps: true, pointRadius: 2,
    }));

    new Chart(document.getElementById("chart-confidence"), {
      type: "line",
      data: { labels: days, datasets },
      options: { ...baseGridOptions(), plugins: { legend: { display: true, position: "top" } },
        scales: { ...baseGridOptions().scales, y: { min: 0, max: 1, grid: { color: "rgba(255,255,255,0.06)" } } } },
    });
  } catch (err) {
    console.error(err);
  }
}

async function loadDrift() {
  try {
    const rows = await API.get("/api/monitoring/category-drift");
    rows.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
    new Chart(document.getElementById("chart-drift"), {
      type: "bar",
      data: {
        labels: rows.map(r => r.category),
        datasets: [{ label: "Δ vs prior 30 days (pts)", data: rows.map(r => r.delta),
          backgroundColor: rows.map(r => r.delta >= 0 ? "#1fd18f" : "#e2574c"), borderRadius: 5 }],
      },
      options: { ...baseGridOptions(), indexAxis: "y", plugins: { legend: { display: false } } },
    });
  } catch (err) { console.error(err); }
}

async function loadBatchHealth() {
  const tbody = document.getElementById("mon-batches");
  try {
    const rows = await API.get("/api/monitoring/upload-batches", { limit: 10 });
    const statusBadge = { completed: "badge-green", processing: "badge-gold", failed: "badge-red" };
    tbody.innerHTML = rows.length ? rows.map(b => `
      <tr>
        <td style="max-width:180px; overflow:hidden; text-overflow:ellipsis;">${escapeHtml(b.filename)}</td>
        <td><span class="badge ${statusBadge[b.status] || "badge-grey"}">${b.status}</span></td>
        <td>${b.rows_ingested}</td>
        <td>${b.rows_failed}</td>
        <td><button class="btn btn-secondary btn-sm" data-batch-id="${b.id}">Delete</button></td>
      </tr>`).join("") : `<tr><td colspan="5" class="empty-state">No uploads yet.</td></tr>`;

    // Real event listeners instead of inline onclick -- an inline
    // onclick="deleteBatch(${id}, ${JSON.stringify(filename)})" breaks the
    // moment JSON.stringify's double-quoted string collides with the
    // onclick attribute's own double quotes (the browser closes the
    // attribute at the first inner quote, silently truncating/breaking the
    // handler). Filename is looked up from the in-memory `rows` array at
    // click time instead of being round-tripped through an HTML attribute
    // at all, so this class of bug can't happen here.
    const rowsById = Object.fromEntries(rows.map(b => [b.id, b]));
    tbody.querySelectorAll("button[data-batch-id]").forEach(btn => {
      const id = Number(btn.dataset.batchId);
      btn.addEventListener("click", () => deleteBatch(id, rowsById[id]?.filename));
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${err.message}</td></tr>`;
  }
}

function escapeHtml(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

async function deleteBatch(batchId, filename) {
  if (!confirm(`Delete "${filename}" and all its transactions? This can't be undone.`)) return;
  try {
    const r = await API.del(`/api/upload/batches/${batchId}`);
    toast(`Deleted ${r.transactions_deleted} transaction(s) from "${r.filename}"`, "success");
    loadBatchHealth();
    loadMonStats();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function loadLowConfidence() {
  const tbody = document.getElementById("mon-lowconf");
  try {
    const rows = await API.get("/api/monitoring/low-confidence", { threshold: 0.55, limit: 30 });
    tbody.innerHTML = rows.length ? rows.map(t => `
      <tr>
        <td>${fmtDateTime(t.completion_time)}</td>
        <td style="max-width:280px; overflow:hidden; text-overflow:ellipsis;">${t.details}</td>
        <td>${fmtMoney(t.amount)}</td>
        <td><span class="badge badge-gold">${t.transaction_category || "—"}</span></td>
        <td>${fmtPct(t.category_confidence)}</td>
      </tr>`).join("") : `<tr><td colspan="5" class="empty-state">Nothing below the confidence threshold 🎉</td></tr>`;
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${err.message}</td></tr>`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadMonStats();
  loadConfidenceTrend();
  loadDrift();
  loadBatchHealth();
  loadLowConfidence();
});