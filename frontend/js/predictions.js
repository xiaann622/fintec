document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("predict-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("predict-btn");
    const resultEl = document.getElementById("predict-result");
    btn.disabled = true; btn.textContent = "Running…";
    resultEl.innerHTML = `<div class="spinner"></div>`;

    try {
      const payload = {
        details: document.getElementById("p-details").value.trim(),
        paid_in: parseFloat(document.getElementById("p-paidin").value || 0),
        withdrawn: parseFloat(document.getElementById("p-withdrawn").value || 0),
      };
      const timeVal = document.getElementById("p-time").value;
      if (timeVal) payload.completion_time = new Date(timeVal).toISOString();

      const r = await API.post("/api/predictions/predict", payload);

      const overrideNote = r.category_override_applied
        ? `<div class="success-banner show" style="margin-top:14px;">
             🔧 Keyword override applied — raw model said <strong>${r.transaction_category_raw_model}</strong>,
             overridden to <strong>${r.transaction_category}</strong>
             ${r.counterparty_alias ? `based on business name "<em>${r.counterparty_alias}</em>"` : ""}.
           </div>`
        : "";

      resultEl.innerHTML = `
        <div class="section">
          <div class="stat-label">Cleaned text (details_nlp)</div>
          <div class="muted" style="margin-top:6px; font-size:13px;">${r.details_nlp || "—"}</div>
        </div>
        <div class="grid grid-3">
          <div>
            <div class="stat-label">Label</div>
            <div style="margin-top:8px;"><span class="badge badge-blue">${r.transaction_label}</span></div>
            <div class="muted" style="margin-top:6px; font-size:12px;">${r.label_confidence ? fmtPct(r.label_confidence) + " confidence" : ""}</div>
          </div>
          <div>
            <div class="stat-label">Classification</div>
            <div style="margin-top:8px;"><span class="badge badge-gold">${r.transaction_classification}</span></div>
            <div class="muted" style="margin-top:6px; font-size:12px;">${r.classification_confidence ? fmtPct(r.classification_confidence) + " confidence" : ""}</div>
          </div>
          <div>
            <div class="stat-label">Category</div>
            <div style="margin-top:8px;"><span class="badge badge-green">${r.transaction_category}</span></div>
            <div class="muted" style="margin-top:6px; font-size:12px;">${r.category_confidence ? fmtPct(r.category_confidence) + " confidence" : ""}</div>
          </div>
        </div>
        ${overrideNote}`;
    } catch (err) {
      resultEl.innerHTML = `<div class="error-banner show">${err.message}</div>`;
    } finally {
      btn.disabled = false; btn.textContent = "Run pipeline";
    }
  });
});
