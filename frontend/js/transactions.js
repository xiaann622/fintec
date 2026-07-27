let currentPage = 1;
const pageSize = 25;
let totalRows = 0;

async function populateFacets() {
  try {
    const [labels, classifications, categories] = await Promise.all([
      API.get("/api/transactions/facets/labels"),
      API.get("/api/transactions/facets/classifications"),
      API.get("/api/transactions/facets/categories"),
    ]);
    fillSelect("f-label", labels.map(r => r.label));
    fillSelect("f-classification", classifications.map(r => r.classification));
    fillSelect("f-category", categories.map(r => r.category));
  } catch (err) { console.error(err); }
}

function fillSelect(id, values) {
  const sel = document.getElementById(id);
  values.filter(Boolean).sort().forEach(v => {
    const opt = document.createElement("option");
    opt.value = v; opt.textContent = v;
    sel.appendChild(opt);
  });
}

function currentFilters() {
  return {
    search: document.getElementById("f-search").value.trim(),
    label: document.getElementById("f-label").value,
    classification: document.getElementById("f-classification").value,
    category: document.getElementById("f-category").value,
    date_from: document.getElementById("f-from").value,
    date_to: document.getElementById("f-to").value,
  };
}

async function loadTransactions() {
  const tbody = document.getElementById("txn-rows");
  tbody.innerHTML = `<tr><td colspan="9" class="empty-state">Loading…</td></tr>`;
  try {
    const data = await API.get("/api/transactions", {
      page: currentPage, page_size: pageSize, ...currentFilters(),
    });
    totalRows = data.total;
    document.getElementById("page-info").textContent =
      `Page ${data.page} · ${totalRows.toLocaleString()} transactions`;

    if (!data.items.length) {
      tbody.innerHTML = `<tr><td colspan="9" class="empty-state">No transactions match these filters.</td></tr>`;
      return;
    }
    tbody.innerHTML = data.items.map(t => `
      <tr>
        <td>${fmtDateTime(t.completion_time)}</td>
        <td class="muted">${t.receipt_no || "—"}</td>
        <td style="max-width:300px; overflow:hidden; text-overflow:ellipsis;">${t.details}</td>
        <td>${fmtMoney(t.paid_in)}</td>
        <td>${fmtMoney(t.withdrawn)}</td>
        <td><span class="badge badge-blue">${t.transaction_label || "—"}</span></td>
        <td><span class="badge badge-gold">${t.transaction_classification || "—"}</span></td>
        <td><span class="badge badge-green">${t.transaction_category || "—"}</span></td>
        <td>${t.category_confidence !== null && t.category_confidence !== undefined ? fmtPct(t.category_confidence) : "—"}</td>
      </tr>
    `).join("");
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="9" class="empty-state">${err.message}</td></tr>`;
  }
}

function applyFilters() { currentPage = 1; loadTransactions(); }
function resetFilters() {
  ["f-search", "f-from", "f-to"].forEach(id => document.getElementById(id).value = "");
  ["f-label", "f-classification", "f-category"].forEach(id => document.getElementById(id).value = "");
  applyFilters();
}
function nextPage() {
  if (currentPage * pageSize >= totalRows) return;
  currentPage++; loadTransactions();
}
function prevPage() {
  if (currentPage <= 1) return;
  currentPage--; loadTransactions();
}

document.addEventListener("DOMContentLoaded", () => {
  populateFacets();
  loadTransactions();
});
