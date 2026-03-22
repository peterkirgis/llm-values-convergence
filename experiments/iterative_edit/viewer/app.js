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

  const cards = [...byModel.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([model, modelRecords]) => {
      const dimensionBlocks = DIMENSIONS.map((config) => {
        const presentRecords = modelRecords.filter((record) => record.coding?.dimensions?.[config.key]?.present);
        const counts = Object.fromEntries(config.directions.map((direction) => [direction, 0]));
        for (const record of presentRecords) {
          const direction = record.coding?.dimensions?.[config.key]?.direction;
          if (direction && direction in counts) {
            counts[direction] += 1;
          }
        }
        return `
          <section class="dimension-card">
            <div class="dimension-header">
              <h3>${escapeHtml(config.label)}</h3>
              <span>${presentRecords.length}/${modelRecords.length} present</span>
            </div>
            ${buildDirectionRows(counts, config, presentRecords.length)}
          </section>
        `;
      }).join("");

      return `
        <article class="model-summary-card">
          <div class="model-summary-header">
            <div>
              <h3>${escapeHtml(model)}</h3>
              <p>${modelRecords.length} coded edits in current view</p>
            </div>
          </div>
          <div class="dimension-grid">
            ${dimensionBlocks}
          </div>
        </article>
      `;
    })
    .join("");

  codingSummary.innerHTML = cards;
}

function renderRecord(record) {
  const node = template.content.firstElementChild.cloneNode(true);
  node.querySelector(".record-title").textContent = record.change_description || "Unapplied edit";
  node.querySelector(".record-subtitle").textContent =
    `${record.model_display} · ${record.document_id} · ${record.doc_type} · round ${record.round_number}/${record.total_rounds}`;
  node.querySelector(".round-badge").textContent = `round ${record.round_number}`;
  node.querySelector(".strategy-badge").textContent = record.match_strategy || "exact";

  const retryBadge = node.querySelector(".retry-badge");
  if (record.retried) {
    retryBadge.classList.remove("hidden");
  }

  const errorBadge = node.querySelector(".error-badge");
  const errorMessage = node.querySelector(".error-message");
  const beforeText = node.querySelector(".before-text");
  const afterText = node.querySelector(".after-text");
  if (record.error) {
    errorBadge.classList.remove("hidden");
    errorMessage.classList.remove("hidden");
    errorMessage.textContent = record.error;
    beforeText.textContent = record.find_text || "(no FIND text captured)";
    afterText.textContent = "(edit failed before application)";
  } else {
    beforeText.textContent = record.find_text || "(empty)";
    afterText.textContent = record.replace_text || "(deleted)";
  }

  node.querySelector(".change-description").textContent =
    record.change_description || "No change description captured for this row.";
  node.querySelector(".find-text").textContent = record.find_text || "(empty)";
  node.querySelector(".replace-text").textContent = record.replace_text || "(deleted)";

  if (record.coding) {
    const codingBlock = document.createElement("div");
    codingBlock.className = "coding-block";
    const chips = DIMENSIONS.flatMap((config) => {
      const code = record.coding?.dimensions?.[config.key];
      if (!code?.present || !code.direction) {
        return [];
      }
      return [
        `<span class="coding-chip"><strong>${escapeHtml(config.label)}:</strong> ${escapeHtml(titleCaseDirection(code.direction, config))}</span>`,
      ];
    }).join("");
    codingBlock.innerHTML = `
      <div class="coding-block-header">
        <h3>Qualitative code</h3>
        <span>${escapeHtml(record.coding.coder_model || "")}</span>
      </div>
      <p class="coding-summary-text">${escapeHtml(record.coding.summary || "")}</p>
      <div class="coding-chip-row">${chips || '<span class="coding-chip muted-chip">No present dimensions</span>'}</div>
    `;
    node.querySelector(".change-description").insertAdjacentElement("afterend", codingBlock);
  }

  const tagInput = node.querySelector(".tag-input");
  const noteInput = node.querySelector(".note-input");
  tagInput.value = localStorage.getItem(tagKey(record.id)) || "";
  noteInput.value = localStorage.getItem(noteKey(record.id)) || "";

  tagInput.addEventListener("input", () => {
    localStorage.setItem(tagKey(record.id), tagInput.value);
  });
  noteInput.addEventListener("input", () => {
    localStorage.setItem(noteKey(record.id), noteInput.value);
  });

  return node;
}

function render() {
  const visible = summarizeVisible(state.records);
  recordsRoot.innerHTML = "";

  if (visible.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No records match the current filters.";
    recordsRoot.append(empty);
    return;
  }

  for (const record of visible) {
    recordsRoot.append(renderRecord(record));
  }
}

runSelect.addEventListener("change", async () => {
  await loadRun(runSelect.value);
});

[modelFilter, documentFilter, typeFilter, errorsToggle].forEach((element) => {
  element.addEventListener("change", render);
});

searchInput.addEventListener("input", render);

loadRuns().catch((error) => {
  recordsRoot.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
});
