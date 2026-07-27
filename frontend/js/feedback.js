async function loadFeedbackList() {
  const el = document.getElementById("fb-list");
  try {
    const rows = await API.get("/api/feedback");
    if (!rows.length) {
      el.innerHTML = `<div class="empty-state">No feedback submitted yet — be the first!</div>`;
      return;
    }
    const catBadge = { "prediction-quality": "badge-gold", bug: "badge-red", feature: "badge-blue", other: "badge-grey" };
    el.innerHTML = rows.map(f => `
      <div style="padding:12px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
        <div class="flex-between">
          <strong style="font-size:13.5px;">${f.subject}</strong>
          <span class="badge ${catBadge[f.category] || "badge-grey"}">${f.category}</span>
        </div>
        <div class="muted" style="font-size:12.5px; margin-top:6px;">${f.message}</div>
        <div class="muted" style="font-size:11px; margin-top:6px;">${fmtDateTime(f.created_at)}${f.rating ? " · " + "⭐".repeat(f.rating) : ""}</div>
      </div>`).join("");
  } catch (err) {
    el.innerHTML = `<div class="empty-state">${err.message}</div>`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadFeedbackList();

  document.getElementById("feedback-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("fb-btn");
    btn.disabled = true; btn.textContent = "Sending…";
    try {
      const txnIdVal = document.getElementById("fb-txn-id").value;
      const ratingVal = document.getElementById("fb-rating").value;
      await API.post("/api/feedback", {
        subject: document.getElementById("fb-subject").value.trim(),
        message: document.getElementById("fb-message").value.trim(),
        category: document.getElementById("fb-category").value,
        rating: ratingVal ? parseInt(ratingVal) : null,
        transaction_id: txnIdVal ? parseInt(txnIdVal) : null,
      });
      toast("Thanks for the feedback!", "success");
      document.getElementById("feedback-form").reset();
      loadFeedbackList();
    } catch (err) {
      toast(err.message, "error");
    } finally {
      btn.disabled = false; btn.textContent = "Send feedback";
    }
  });
});
