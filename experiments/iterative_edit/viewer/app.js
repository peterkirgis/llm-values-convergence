const runSelect = document.getElementById("run-select");
const modelFilter = document.getElementById("model-filter");
const documentFilter = document.getElementById("document-filter");
const typeFilter = document.getElementById("type-filter");
const searchInput = document.getElementById("search-input");
const errorsToggle = document.getElementById("errors-toggle");
const recordsRoot = document.getElementById("records");
const resultSummary = document.getElementById("result-summary");
const codingSummary = document.getElementById("coding-summary");
const heroModels = document.getElementById("hero-models");
const template = document.getElementById("record-template");

const state = {
  runs: [],
  selectedRun: "",
  records: [],
  staticRuns: null,
};

const DIMENSIONS = [
  {
    key: "ethics_vs_epistemics",
    label: "Ethics vs Epistemics",
    directions: ["toward_ethics", "toward_epistemics", "mixed"],
    directionLabels: {
      toward_ethics: "Toward ethics",
      toward_epistemics: "Toward epistemics",
      mixed: "Mixed",
    },
  },
  {
    key: "autonomy_vs_paternalism",
    label: "Autonomy vs Paternalism",
    directions: ["toward_autonomy", "toward_paternalism", "mixed"],
    directionLabels: {
      toward_autonomy: "Toward autonomy",
      toward_paternalism: "Toward paternalism",
      mixed: "Mixed",
    },
  },
  {
    key: "human_centered_vs_model_centered_moral_concern",
    label: "Human vs Model Concern",
    directions: ["toward_humans", "toward_model", "mixed"],
    directionLabels: {
      toward_humans: "Toward humans",
      toward_model: "Toward model",
      mixed: "Mixed",
    },
  },
];

function noteKey(recordId) {
  return `iterative-edit-note:${recordId}`;
}

function tagKey(recordId) {
  return `iterative-edit-tag:${recordId}`;
}

function escapeHtml(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function titleCaseDirection(direction, config) {
  return config.directionLabels[direction] || direction;
}

async function fetchJson(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

async function loadRuns() {
  try {
    const staticPayload = await fetchJson("./data/site.json");
    state.staticRuns = staticPayload.runs || [];
    state.runs = state.staticRuns.map((run) => ({
      run_name: run.run_name,
      record_count: run.record_count,
      successful_count: run.successful_count,
      error_count: run.error_count,
      models: run.models || [],
      documents: run.documents || [],
    }));
  } catch (_error) {
    state.staticRuns = null;
    state.runs = await fetchJson("/api/runs");
  }

  runSelect.innerHTML = "";
  for (const run of state.runs) {
    const option = document.createElement("option");
    option.value = run.run_name;
    option.textContent = `${run.run_name} (${run.successful_count} successes, ${run.error_count} errors)`;
    runSelect.append(option);
  }
  if (state.runs.length > 0) {
    state.selectedRun = state.runs[0].run_name;
    runSelect.value = state.selectedRun;
    await loadRun(state.selectedRun);
  }
}

async function loadRun(runName) {
  state.selectedRun = runName;
  if (state.staticRuns) {
    const payload = state.staticRuns.find((run) => run.run_name === runName);
    if (!payload) {
      throw new Error(`Run not found in static bundle: ${runName}`);
    }
    state.records = payload.records || [];
  } else {
    const payload = await fetchJson(`/api/run?name=${encodeURIComponent(runName)}`);
    state.records = payload.records;
  }
  renderHeroMetadata();
  populateFilters();
  render();
}

function renderHeroMetadata() {
  const run = state.runs.find((item) => item.run_name === state.selectedRun);
  const models = run?.models || [];
  heroModels.textContent = models.length > 0
    ? `Models tested: ${models.join(" · ")}`
    : "Models tested: none available for this run";
}

function uniqueValues(items, key) {
  return [...new Set(items.map((item) => item[key]).filter(Boolean))].sort();
}

function syncSelectOptions(select, values, allLabel) {
  const current = select.value;
  select.innerHTML = `<option value="">${allLabel}</option>`;
  for (const value of values) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.append(option);
  }
  if ([...select.options].some((option) => option.value === current)) {
    select.value = current;
  }
}

function populateFilters() {
  syncSelectOptions(modelFilter, uniqueValues(state.records, "model_display"), "All models");
  syncSelectOptions(documentFilter, uniqueValues(state.records, "document_id"), "All documents");
}

function recordMatches(record) {
  if (modelFilter.value && record.model_display !== modelFilter.value) {
    return false;
  }
  if (documentFilter.value && record.document_id !== documentFilter.value) {
    return false;
  }
  if (typeFilter.value && record.doc_type !== typeFilter.value) {
    return false;
  }
  if (!errorsToggle.checked && record.error) {
    return false;
  }

  const query = searchInput.value.trim().toLowerCase();
  if (!query) {
    return true;
  }

  const haystack = [
    record.change_description,
    record.find_text,
    record.replace_text,
    record.error,
    record.coding?.summary || "",
    JSON.stringify(record.coding?.dimensions || {}),
    localStorage.getItem(noteKey(record.id)) || "",
    localStorage.getItem(tagKey(record.id)) || "",
  ]
    .join("\n")
    .toLowerCase();

  return haystack.includes(query);
}

function summarizeVisible(records) {
  const visible = records.filter(recordMatches);
  const successes = visible.filter((record) => !record.error);
  const fuzzy = successes.filter((record) => record.match_strategy === "fuzzy").length;
  const retried = successes.filter((record) => record.retried).length;

  resultSummary.textContent =
    `${visible.length} rows visible · ${successes.length} successful edits · ` +
    `${visible.length - successes.length} errors · ${retried} retried · ${fuzzy} fuzzy matches`;

  renderCodingSummary(visible);
  return visible;
}

function buildDirectionRows(counts, config, codedTotal) {
  return config.directions
    .map((direction) => {
      const count = counts[direction] || 0;
      const width = codedTotal > 0 ? `${(count / codedTotal) * 100}%` : "0%";
      return `
        <div class="direction-row">
          <div class="direction-copy">
            <span>${escapeHtml(titleCaseDirection(direction, config))}</span>
            <strong>${count}</strong>
          </div>
          <div class="direction-bar-track">
            <div class="direction-bar-fill" style="width: ${width}"></div>
          </div>
        </div>
      `;
    })
    .join("");
}

function renderCodingSummary(records) {
  const codedRecords = records.filter((record) => record.coding && !record.error);
  if (codedRecords.length === 0) {
    codingSummary.innerHTML = `
      <div class="empty-state compact-empty">
        No qualitative codes are available for the current filtered view.
      </div>
    `;
    return;
  }

  const byModel = new Map();
  for (const record of codedRecords) {
    const key = record.model_display || "Unknown model";
    if (!byModel.has(key)) {
      byModel.set(key, []);
    }
    byModel.get(key).push(record);
  }

  const cards = [...byMo