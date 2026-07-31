let selectedFile = null;

function setupDropzone() {
  const dz = document.getElementById("dropzone");
  const input = document.getElementById("file-input");
  const btn = document.getElementById("upload-btn");
  const chipWrap = document.getElementById("file-chip-wrap");

  dz.addEventListener("click", () => input.click());
  dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("dragover"); });
  dz.addEventListener("dragleave", () => dz.classList.remove("dragover"));
  dz.addEventListener("drop", (e) => {
    e.preventDefault();
    dz.classList.remove("dragover");
    if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
  });
  input.addEventListener("change", () => {
    if (input.files.length) handleFile(input.files[0]);
  });

  function handleFile(file) {
    selectedFile = file;
    btn.disabled = false;
    chipWrap.innerHTML = `
      <div class="file-chip">
        <span>📎 ${file.name} <span class="muted">(${(file.size / 1024).toFixed(0)} KB)</span></span>
        <button class="btn btn-secondary btn-sm" onclick="clearFile()">Remove</button>
      </div>`;
  }

  window.clearFile = () => {
    selectedFile = null;
    input.value = "";
    btn.disabled = true;
    chipWrap.innerHTML = "";
  };

  btn.addEventListener("click", doUpload);
}

async function doUpload() {
  if (!selectedFile) return;
  const btn = document.getElementById("upload-btn");
  const resultEl = document.getElementById("upload-result");
  const progWrap = document.getElementById("progress-wrap");
  const progBar = document.getElementById("progress-bar");

  btn.disabled = true;
  btn.textContent = "Processing…";
  progWrap.style.display = "block";
  progBar.style.width = "30%";
  resultEl.innerHTML = "";

  try {
    const fd = new FormData();
    fd.append("file", selectedFile);
    progBar.style.width = "65%";
    const result = await API.upload("/api/upload", fd);
    progBar.style.width = "100%";

    resultEl.innerHTML = `
      <div class="success-banner show">
        ✅ ${result.message}<br/>
        Ingested <strong>${result.rows_ingested}</strong> rows, ${result.rows_failed} failed.
      </div>`;
    toast("Upload complete", "success");
    clearFile();
    loadBatches();
  } catch (err) {
    resultEl.innerHTML = `<div class="error-banner show">${err.message}</div>`;
    toast("Upload failed", "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Upload & Classify";
    setTimeout(() => { progWrap.style.display = "none"; progBar.style.width = "0%"; }, 900);
  }
}

async function loadBatches() {
  const tbody = document.getElementById("batches-rows");
  try {
    const rows = await API.get("/api/monitoring/upload-batches", { limit: 15 });
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="empty-state">No uploads yet.</td></tr>`;
      return;
    }
    const statusBadge = { completed: "badge-green", processing: "badge-gold", failed: "badge-red" };
    tbody.innerHTML = rows.map(b => `
      <tr>
        <td>${b.filename}</td>
        <td>${b.file_type}</td>
        <td>${b.rows_ingested}</td>
        <td>${b.rows_failed}</td>
        <td><span class="badge ${statusBadge[b.status] || "badge-grey"}">${b.status}</span></td>
        <td>${fmtDateTime(b.created_at)}</td>
      </tr>
    `).join("");
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">${err.message}</td></tr>`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  setupDropzone();
  loadBatches();

  const clearBtn = document.getElementById("clear-mine-btn");
  const clearResult = document.getElementById("clear-mine-result");
  clearBtn.addEventListener("click", async () => {
    if (!confirm(
      "Delete ALL transactions you've previously uploaded? This keeps old data " +
      "from mixing into a new analysis, but can't be undone. Other analysts' " +
      "data is not affected."
    )) return;

    clearBtn.disabled = true;
    clearBtn.textContent = "Clearing…";
    try {
      const r = await API.del("/api/transactions/mine");
      clearResult.innerHTML = `
        <div class="success-banner show">
          ✅ Cleared ${r.transactions_deleted} transaction(s) across ${r.batches_deleted} previous upload(s).
        </div>`;
      toast("Your previous transactions were cleared", "success");
      loadBatches();
    } catch (err) {
      clearResult.innerHTML = `<div class="error-banner show">${err.message}</div>`;
      toast(err.message, "error");
    } finally {
      clearBtn.disabled = false;
      clearBtn.textContent = "Clear my previous transactions";
    }
  });
});