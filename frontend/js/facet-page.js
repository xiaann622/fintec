/* Generic "distribution + drill-down list" page.
   Each page sets window.FACET_CONFIG before including this script:
   {
     facetEndpoint: "/api/transactions/facets/labels",
     facetKey: "label",                // key in the facet objects returned
     filterParam: "label",             // query param name for /api/transactions
     title: "Transaction Labels"
   }
*/
async function loadFacetChart() {
  const cfg = window.FACET_CONFIG;
  try {
    const rows = await API.get(cfg.facetEndpoint);
    rows.sort((a, b) => b.count - a.count);

    new Chart(document.getElementById("facet-chart"), {
      type: "bar",
      data: {
        labels: rows.map(r => r[cfg.facetKey]),
        datasets: [{ data: rows.map(r => r.count), backgroundColor: rows.map((_, i) => colorFor(i)), borderRadius: 6 }],
      },
      options: { ...baseGridOptions(), indexAxis: "y" },
    });

    const total = rows.reduce((s, r) => s + r.count, 0) || 1;
    const listEl = document.getElementById("facet-list");
    listEl.innerHTML = rows.map((r, i) => `
      <div class="flex-between" style="padding:9px 0; border-bottom:1px solid rgba(255,255,255,0.05); cursor:pointer;"
           onclick="drillInto('${(r[cfg.facetKey] || "").replace(/'/g, "\\'")}')">
        <span><span class="badge ${badgeClassFor(i)}" style="margin-right:8px;">${r[cfg.facetKey]}</span></span>
        <span class="muted">${r.count.toLocaleString()} · ${(100 * r.count / total).toFixed(1)}%</span>
      </div>
    `).join("");
  } catch (err) {
    document.getElementById("facet-list").innerHTML = `<div class="empty-state">${err.message}</div>`;
  }
}

let facetFilterValue = "";
async function loadFacetTable() {
  const cfg = window.FACET_CONFIG;
  const tbody = document.getElementById("facet-txn-rows");
  tbody.innerHTML = `<tr><td colspan="6" class="empty-state">Loading…</td></tr>`;
  try {
    const params = { page: 1, page_size: 15 };
    if (facetFilterValue) params[cfg.filterParam] = facetFilterValue;
    const data = await API.get("/api/transactions", params);
    if (!data.items.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="empty-state">No matching transactions.</td></tr>`;
      return;
    }
    tbody.innerHTML = data.items.map(t => `
      <tr>
        <td>${fmtDateTime(t.completion_time)}</td>
        <td style="max-width:260px; overflow:hidden; text-overflow:ellipsis;">${t.details}</td>
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

function drillInto(value) {
  facetFilterValue = value;
  document.getElementById("drill-label").textContent = value ? `Filtered by: ${value}` : "";
  loadFacetTable();
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("page-title-el").textContent = window.FACET_CONFIG.title;
  loadFacetChart();
  loadFacetTable();
});
