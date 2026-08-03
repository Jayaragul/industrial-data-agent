const state = { uploadDataset: null };
const $ = (id) => document.getElementById(id);

function showMessage(text, error = false) {
  const box = $("upload-message");
  box.hidden = false;
  box.textContent = text;
  box.className = `message${error ? " error" : ""}`;
}

function renderDatasets(datasets) {
  const active = datasets.filter((item) => item.active).length;
  $("active-count").textContent = `${active} / ${datasets.length}`;
  $("dataset-list").innerHTML = datasets.map((item) => `
    <div class="dataset-card">
      <div class="dataset-card-head"><span class="dataset-name">${item.label}</span><span class="badge ${item.active ? "active" : ""}">${item.active ? "Active" : "Demo"}</span></div>
      <div class="dataset-meta">${item.records} records - ${item.source}</div>
      <button class="upload-button" data-dataset="${item.name}">Upload file</button>
    </div>`).join("");
  document.querySelectorAll(".upload-button").forEach((button) => button.addEventListener("click", () => {
    state.uploadDataset = button.dataset.dataset;
    $("file-input").click();
  }));
}

async function refreshStatus() {
  const response = await fetch("/api/status");
  const data = await response.json();
  renderDatasets(data.datasets);
}

$("refresh-button").addEventListener("click", refreshStatus);
$("file-input").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file || !state.uploadDataset) return;
  const form = new FormData();
  form.append("file", file);
  showMessage(`Uploading ${file.name}...`);
  try {
    const response = await fetch(`/api/ingest/${state.uploadDataset}`, { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Upload failed.");
    showMessage(data.message);
    renderDatasets(data.status);
  } catch (error) {
    showMessage(error.message, true);
  }
  event.target.value = "";
});

refreshStatus().catch(() => showMessage("The upload service could not connect to the agent.", true));
