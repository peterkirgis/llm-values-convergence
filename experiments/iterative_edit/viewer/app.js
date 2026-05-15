const typeFilter = document.getElementById("type-filter");
const searchInput = document.getElementById("search-input");
const errorsToggle = document.getElementById("errors-toggle");
const exploratoryToggle = document.getElementById("exploratory-toggle");
const bandToggle = document.getElementById("band-toggle");
const recordsRoot = document.getElementById("records");
const resultSummary = document.getElementById("result-summary");
const codingSummary = document.getElementById("coding-summary");
const poolSummary = document.getElementById("pool-summary");
const driftMeta = document.getElementById("drift-meta");
const modelChipsEl = document.getElementById("model-chips");
const conditionChipsEl = document.getElementById("condition-chips");
const documentChipsEl = document.getElementById("document-chips");
const recordConditionFilter = document.getElementById("record-condition-filter");
const recordModelFilter = document.getElementById("record-model-filter");
const recordDocumentFilter = document.getElementById("record-document-filter");
const template = document.getElementById("record-template");

const state = {
  runs: [],
  pooledRecords: [],
  models: [],
  conditions: [],
  conditionLabels: new Map(),
  documents: [],
  selectedModels: new Set(),
  selectedConditions: new Set(),
  selectedDocuments: new Set(),
  // Conversation viewer uses its own single-select model/document/condition
  // controls, independent of the plot's multi-select chips above.
  recordConditionId: "",
  recordModelId: "",
  recordDocumentId: "",
};

const DIMENSIONS = [
  {
    key: "authority",
    label: "Authority",
    directions: ["external", "internal", "mixed"],
    directionLabels: { external: "External", internal: "Internal", mixed: "Mixed" },
  },
  {
    key: "user_stance",
    label: "User Stance",
    directions: ["autonomy", "protection", "mixed"],
    directionLabels: { autonomy: "Autonomy", protection: "Protection", mixed: "Mixed" },
  },
  {
    key: "telos",
    label: "Telos",
    directions: ["truth", "wellbeing", "mixed"],
    directionLabels: { truth: "Truth", wellbeing: "Wellbeing", mixed: "Mixed" },
  },
];

// Categorical palette tuned for ~10 model lines on one chart. Hues are spaced
// far apart in hue + luminance so adjacent lines stay distinct, with the
// Anthropic/OpenAI/Google/xAI families grouped by hue family.
//   Anthropic family: deep brick -> warm terracotta (red/brown)
//   OpenAI family:    deep navy  -> mid blue
//   Google family:    deep amber -> warm gold (yellow)
//   xAI family:       deep plum  -> medium purple
const DRIFT_MODEL_COLORS = {
  "Claude Opus 4.6": "#5a1810",
  "Claude Sonnet 4.6": "#9c3220",
  "Claude Haiku 4.5": "#c97244",
  "GPT-5.4": "#0b4f8a",
  "GPT-5.4 Thinking": "#3d8dc7",
  "GPT-5.4 Mini": "#1c2f5a",
  "Gemini 3.1 Pro": "#7f5a06",
  "Gemini 3 Flash": "#c89a26",
  "Grok 4.3": "#3a1655",
  "Grok 4.2": "#7b3f9e",
};
const DRIFT_FALLBACK_COLORS = [
  "#444444", "#888888", "#b35a00", "#005f73", "#9d0208", "#403d39",
];

const DRIFT_DIMS = [
  { key: "authority", label: "Authority", poles: "External (-) vs Internal (+)", pos: "internal", neg: "external" },
  { key: "user_stance", label: "User Stance", poles: "Protection (-) vs Autonomy (+)", pos: "autonomy", neg: "protection" },
  { key: "telos", label: "Telos", poles: "Wellbeing (-) vs Truth (+)", pos: "truth", neg: "wellbeing" },
];

let driftFrame = 0;
let driftPlaying = true;
let driftLastTick = 0;
const DRIFT_TICK_MS = 600;
let driftCharts = [];
const fallbackColorAssignments = new Map();

function noteKey(recordId) { return `iterative-edit-note:${recordId}`; }
function tagKey(recordId) { return `iterative-edit-tag:${recordId}`; }

function escapeHtml(text) {
  return String(text || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function titleCaseDirection(direction, config) {
  return config.directionLabels[direction] || direction;
}

function normalizeConditionId(record) {
  return record.condition_id || "baseline";
}

function normalizeConditionName(record) {
  return record.condition_name || "Baseline";
}

function colorForModel(model) {
  if (DRIFT_MODEL_COLORS[model]) return DRIFT_MODEL_COLORS[model];
  if (!fallbackColorAssignments.has(model)) {
    const idx = fallbackColorAssignments.size % DRIFT_FALLBACK_COLORS.length;
    fallbackColorAssignments.set(model, DRIFT_FALLBACK_COLORS[idx]);
  }
  return fallbackColorAssignments.get(model);
}

async function fetchJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  if (path.endsWith(".gz")) {
    const ds = new DecompressionStream("gzip");
    const decompressed = response.body.pipeThrough(ds);
    const text = await new Response(decompressed).text();
    return JSON.parse(text);
  }
  return response.json();
}

async function loadRuns() {
  const payload = await fetchJson("./data/site.json.gz");
  state.runs = payload.runs || [];
  rebuildPool();
}

function rebuildPool() {
  const includeExploratory = exploratoryToggle?.checked;
  const visibleRuns = state.runs.filter((run) => includeExploratory || run.is_reliable);

  const pooled = [];
  const condLabels = new Map();
  for (const run of visibleRuns) {
    for (const record of run.records || []) {
      const normalized = {
        ...record,
        condition_id: normalizeConditionId(record),
        condition_name: normalizeConditionName(record),
        run_name: run.run_name,
        run_is_reliable: !!run.is_reliable,
      };
      pooled.push(normalized);
      condLabels.set(normalized.condition_id, normalized.condition_name);
    }
  }

  state.pooledRecords = pooled;
  state.models = [...new Set(pooled.map((r) => r.model_display).filter(Boolean))].sort();
  state.conditions = [...condLabels.keys()].sort((a, b) => condLabels.get(a).localeCompare(condLabels.get(b)));
  state.conditionLabels = condLabels;
  state.documents = [...new Set(pooled.map((r) => r.document_id).filter(Boolean))].sort();

  // Pool rebuilds only happen when the exploratory-runs toggle flips, which
  // changes the set of available filter values. Reset selections to "all
  // available" so the user starts from a coherent baseline.
  state.selectedModels = new Set(state.models);
  state.selectedConditions = new Set(state.conditions);
  state.selectedDocuments = new Set(state.documents);

  // Records-only single-select controls: preserve current pick if still valid,
  // otherwise reset to "" (= All).
  if (state.recordConditionId && !state.conditions.includes(state.recordConditionId)) {
    state.recordConditionId = "";
  }
  if (state.recordModelId && !state.models.includes(state.recordModelId)) {
    state.recordModelId = "";
  }
  if (state.recordDocumentId && !state.documents.includes(state.recordDocumentId)) {
    state.recordDocumentId = "";
  }

  renderPoolSummary(visibleRuns);
  renderChipGroups();
  renderRecordFilters();
  render();
}

function renderRecordFilters() {
  fillSelect(recordModelFilter, state.models, state.recordModelId, "All models", (v) => v);
  fillSelect(
    recordDocumentFilter,
    state.documents,
    state.recordDocumentId,
    "All documents",
    (v) => v,
  );
  fillSelect(
    recordConditionFilter,
    state.conditions,
    state.recordConditionId,
    "All conditions",
    (v) => state.conditionLabels.get(v) || v,
  );
}

function fillSelect(el, values, current, allLabel, labelFor) {
  if (!el) return;
  el.innerHTML = "";
  const allOpt = document.createElement("option");
  allOpt.value = "";
  allOpt.textContent = allLabel;
  el.appendChild(allOpt);
  for (const v of values) {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = labelFor(v);
    el.appendChild(opt);
  }
  el.value = current;
}

function renderPoolSummary(visibleRuns) {
  if (!poolSummary) return;
  const reliable = state.runs.filter((r) => r.is_reliable).length;
  const exploratory = state.runs.length - reliable;
  const includingExploratory = exploratoryToggle?.checked;
  const usedReliable = visibleRuns.filter((r) => r.is_reliable).length;
  const usedExploratory = visibleRuns.length - usedReliable;
  const parts = [
    `${visibleRuns.length} run${visibleRuns.length === 1 ? "" : "s"} pooled`,
    `${usedReliable} reliable${exploratory ? ` of ${reliable}` : ""}`,
  ];
  if (includingExploratory && exploratory > 0) {
    parts.push(`${usedExploratory} exploratory of ${exploratory}`);
  } else if (exploratory > 0) {
    parts.push(`${exploratory} exploratory hidden`);
  }
  parts.push(`${state.models.length} models · ${state.conditions.length} conditions · ${state.documents.length} documents`);
  poolSummary.textContent = parts.join(" · ");
}

function renderChipGroups() {
  renderChipGroup(modelChipsEl, state.models, state.selectedModels, "model", (value) => ({
    label: value,
    swatch: colorForModel(value),
  }));
  renderChipGroup(conditionChipsEl, state.conditions, state.selectedConditions, "condition", (value) => ({
    label: state.conditionLabels.get(value) || value,
  }));
  renderChipGroup(documentChipsEl, state.documents, state.selectedDocuments, "document", (value) => ({
    label: value,
  }));
}

function renderChipGroup(root, values, selected, kind, meta) {
  if (!root) return;
  root.innerHTML = "";
  for (const value of values) {
    const info = meta(value);
    const button = document.createElement("button");
    button.type = "button";
    const hasSwatch = !!info.swatch;
    button.className = "filter-chip" + (selected.has(value) ? " active" : "") + (hasSwatch ? "" : " no-swatch");
    button.dataset.value = value;
    if (hasSwatch) button.style.setProperty("--chip-color", info.swatch);
    const sw = document.createElement("span");
    sw.className = "chip-swatch";
    button.appendChild(sw);
    const lbl = document.createElement("span");
    lbl.textContent = info.label;
    button.appendChild(lbl);
    button.addEventListener("click", () => {
      if (selected.has(value)) selected.delete(value);
      else selected.add(value);
      button.classList.toggle("active");
      render();
    });
    root.appendChild(button);
  }
}

function applyQuickAction(target, action) {
  const map = {
    model: { set: state.selectedModels, all: state.models },
    condition: { set: state.selectedConditions, all: state.conditions },
    document: { set: state.selectedDocuments, all: state.documents },
  };
  const entry = map[target];
  if (!entry) return;
  entry.set.clear();
  if (action === "all") for (const v of entry.all) entry.set.add(v);
  renderChipGroups();
  render();
}

document.querySelectorAll(".filter-quick-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    applyQuickAction(btn.dataset.target, btn.dataset.action);
  });
});

// Predicate for the plot view: uses the pooled multi-select chips for model,
// condition, and document. This drives the drift charts.
function plotMatches(record) {
  if (!state.selectedModels.has(record.model_display)) return false;
  if (!state.selectedConditions.has(record.condition_id)) return false;
  if (!state.selectedDocuments.has(record.document_id)) return false;
  if (typeFilter.value && record.doc_type !== typeFilter.value) return false;
  if (!errorsToggle.checked && record.error) return false;
  return true;
}

// Predicate for the conversation viewer: each of model, document, and
// condition is a single-select control that lives independently of the plot's
// multi-select chips. Other aux filters (doc type, search, errors) are shared.
function recordMatches(record) {
  if (state.recordModelId && record.model_display !== state.recordModelId) return false;
  if (state.recordDocumentId && record.document_id !== state.recordDocumentId) return false;
  if (state.recordConditionId && record.condition_id !== state.recordConditionId) return false;
  if (typeFilter.value && record.doc_type !== typeFilter.value) return false;
  if (!errorsToggle.checked && record.error) return false;

  const query = searchInput.value.trim().toLowerCase();
  if (!query) return true;
  const haystack = [
    record.change_description,
    record.condition_name,
    record.find_text,
    record.replace_text,
    record.error,
    record.coding?.summary || "",
    JSON.stringify(record.coding?.dimensions || {}),
    localStorage.getItem(noteKey(record.id)) || "",
    localStorage.getItem(tagKey(record.id)) || "",
  ].join("\n").toLowerCase();
  return haystack.includes(query);
}

function getVisibleRecords() {
  return state.pooledRecords.filter(recordMatches);
}

function getPlotRecords() {
  return state.pooledRecords.filter(plotMatches);
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
    codingSummary.innerHTML = `<div class="empty-state compact-empty">No qualitative codes are available for the current filtered view.</div>`;
    return;
  }
  const byModel = new Map();
  for (const record of codedRecords) {
    const key = record.model_display || "Unknown model";
    if (!byModel.has(key)) byModel.set(key, []);
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
          if (direction && direction in counts) counts[direction] += 1;
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
          <div class="dimension-grid">${dimensionBlocks}</div>
        </article>
      `;
    })
    .join("");
  codingSummary.innerHTML = cards;
}

function summarizeVisible(visible) {
  const successes = visible.filter((record) => !record.error);
  const fuzzy = successes.filter((record) => record.match_strategy === "fuzzy").length;
  const retried = successes.filter((record) => record.retried).length;
  const noChange = successes.filter((record) => record.no_change).length;
  resultSummary.textContent =
    `${visible.length} rows visible · ${successes.length} successful edits · `
    + `${visible.length - successes.length} errors · ${retried} retried · `
    + `${fuzzy} fuzzy matches · ${noChange} no-change rounds`;
  renderCodingSummary(visible);
}

function renderRecord(record) {
  const node = template.content.firstElementChild.cloneNode(true);
  node.querySelector(".record-title").textContent = record.change_description || "Unapplied edit";
  node.querySelector(".condition-badge").textContent = normalizeConditionName(record);
  node.querySelector(".record-subtitle").textContent =
    `${record.model_display} · ${record.document_id} · ${record.doc_type} · ${normalizeConditionName(record)} · round ${record.round_number}/${record.total_rounds}`;
  node.querySelector(".round-badge").textContent = `round ${record.round_number}`;
  node.querySelector(".strategy-badge").textContent = record.match_strategy || "exact";

  if (record.retried) node.querySelector(".retry-badge").classList.remove("hidden");
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
  } else if (record.no_change) {
    beforeText.textContent = "(document left unchanged)";
    afterText.textContent = "(no replacement applied)";
  } else {
    beforeText.textContent = record.find_text || "(empty)";
    afterText.textContent = record.replace_text || "(deleted)";
  }

  node.querySelector(".find-text").textContent = record.find_text || "(empty)";
  node.querySelector(".replace-text").textContent = record.replace_text || "(deleted)";

  if (record.coding) {
    const codingBlock = document.createElement("div");
    codingBlock.className = "coding-block";
    const chips = DIMENSIONS.flatMap((config) => {
      const code = record.coding?.dimensions?.[config.key];
      if (!code?.present || !code.direction) return [];
      return [`<span class="coding-chip"><strong>${escapeHtml(config.label)}:</strong> ${escapeHtml(titleCaseDirection(code.direction, config))}</span>`];
    }).join("");
    codingBlock.innerHTML = `
      <div class="coding-block-header">
        <h3>Qualitative code</h3>
        <span>${escapeHtml(record.coding.coder_model || "")}</span>
      </div>
      <p class="coding-summary-text">${escapeHtml(record.coding.summary || "")}</p>
      <div class="coding-chip-row">${chips || '<span class="coding-chip muted-chip">No present dimensions</span>'}</div>
    `;
    node.querySelector(".error-message").insertAdjacentElement("afterend", codingBlock);
  }

  const tagInput = node.querySelector(".tag-input");
  const noteInput = node.querySelector(".note-input");
  tagInput.value = localStorage.getItem(tagKey(record.id)) || "";
  noteInput.value = localStorage.getItem(noteKey(record.id)) || "";
  tagInput.addEventListener("input", () => { localStorage.setItem(tagKey(record.id), tagInput.value); });
  noteInput.addEventListener("input", () => { localStorage.setItem(noteKey(record.id), noteInput.value); });
  return node;
}

function render() {
  const recordsVisible = getVisibleRecords();
  const plotVisible = getPlotRecords();
  // Coding summary cards + counts reflect the conversation viewer slice.
  summarizeVisible(recordsVisible);
  recordsRoot.innerHTML = "";
  if (recordsVisible.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No records match the current filters.";
    recordsRoot.append(empty);
  } else {
    for (const record of recordsVisible) recordsRoot.append(renderRecord(record));
  }
  // Plots use their own multi-condition filter.
  initDrift(plotVisible);
}

[typeFilter, errorsToggle].forEach((el) => el.addEventListener("change", render));
exploratoryToggle.addEventListener("change", rebuildPool);
bandToggle.addEventListener("change", () => drawAllDrift(driftFrame));
searchInput.addEventListener("input", render);
recordConditionFilter?.addEventListener("change", () => {
  state.recordConditionId = recordConditionFilter.value;
  render();
});
recordModelFilter?.addEventListener("change", () => {
  state.recordModelId = recordModelFilter.value;
  render();
});
recordDocumentFilter?.addEventListener("change", () => {
  state.recordDocumentId = recordDocumentFilter.value;
  render();
});

loadRuns().catch((error) => {
  recordsRoot.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
});

// ===== Drift =====

function getDriftMaxRound(records) {
  if (records.length === 0) return 1;
  const rounds = records.map((record) => Number(record.total_rounds || record.round_number || 0));
  return Math.max(1, ...rounds);
}

function buildCumulativePoints(roundDeltas, maxRound) {
  let cumulative = 0;
  const points = [{ round: 0, value: 0 }];
  for (let round = 1; round <= maxRound; round += 1) {
    cumulative += roundDeltas[round] || 0;
    points.push({ round, value: cumulative });
  }
  return points;
}

// For each (model, run, condition, document) replicate, build a cumulative
// drift trajectory along one dimension. Including run_name in the replicate
// key means two independently-run chains with the same (condition, document)
// — e.g. a standalone baseline run and an ablations run that happens to
// include a baseline condition — count as two replicates rather than being
// collapsed into one. Each independent 20-round chain is its own draw.
function computeDrift(records, dim, maxRound) {
  const byModelReplicate = {};
  for (const record of records) {
    if (!record.coding || record.error) continue;
    const code = record.coding.dimensions?.[dim.key];
    if (!code?.present || !code.direction) continue;
    const model = record.model_display;
    const replicate = `${record.run_name}::${record.condition_id}::${record.document_id}`;
    byModelReplicate[model] ||= {};
    byModelReplicate[model][replicate] ||= {};
    if (code.direction === dim.pos) byModelReplicate[model][replicate][record.round_number] = (byModelReplicate[model][replicate][record.round_number] || 0) + 1;
    else if (code.direction === dim.neg) byModelReplicate[model][replicate][record.round_number] = (byModelReplicate[model][replicate][record.round_number] || 0) - 1;
    else byModelReplicate[model][replicate][record.round_number] ||= 0;
  }

  const series = {};
  for (const [model, replicateMap] of Object.entries(byModelReplicate)) {
    const replicateIds = Object.keys(replicateMap);
    const trajectories = replicateIds.map((rep) => buildCumulativePoints(replicateMap[rep], maxRound));
    if (trajectories.length === 0) continue;

    const mean = [];
    const band = [];
    for (let index = 0; index <= maxRound; index += 1) {
      const values = trajectories.map((points) => points[index].value);
      const m = values.reduce((s, v) => s + v, 0) / values.length;
      let sd = 0;
      if (values.length > 1) {
        const variance = values.reduce((s, v) => s + (v - m) ** 2, 0) / (values.length - 1);
        sd = Math.sqrt(variance);
      }
      mean.push({ round: index, value: m });
      band.push({ round: index, lower: m - sd, upper: m + sd });
    }
    series[model] = { mean, band, replicateCount: trajectories.length };
  }
  return series;
}

// Per (model, replicate): at each round, magnitude = |auth_cum| + |stance_cum|
// + |telos_cum|. A model that drives firmly in any direction scores high; one
// that oscillates stays near 0. Mean ± 1 SD across replicates, same UQ as the
// per-dimension charts.
function computeTotalDrift(records, maxRound) {
  const byModelReplicateDim = {};
  for (const record of records) {
    if (!record.coding || record.error) continue;
    const model = record.model_display;
    const replicate = `${record.run_name}::${record.condition_id}::${record.document_id}`;
    byModelReplicateDim[model] ||= {};
    byModelReplicateDim[model][replicate] ||= {};
    for (const dim of DRIFT_DIMS) {
      const code = record.coding.dimensions?.[dim.key];
      if (!code?.present || !code.direction) continue;
      byModelReplicateDim[model][replicate][dim.key] ||= {};
      const r = record.round_number;
      if (code.direction === dim.pos) {
        byModelReplicateDim[model][replicate][dim.key][r] =
          (byModelReplicateDim[model][replicate][dim.key][r] || 0) + 1;
      } else if (code.direction === dim.neg) {
        byModelReplicateDim[model][replicate][dim.key][r] =
          (byModelReplicateDim[model][replicate][dim.key][r] || 0) - 1;
      }
    }
  }

  const series = {};
  for (const [model, replicateMap] of Object.entries(byModelReplicateDim)) {
    const replicateIds = Object.keys(replicateMap);
    if (replicateIds.length === 0) continue;
    const magnitudeTrajectories = replicateIds.map((rep) => {
      const cumByDim = {};
      for (const dim of DRIFT_DIMS) {
        cumByDim[dim.key] = buildCumulativePoints(replicateMap[rep][dim.key] || {}, maxRound);
      }
      const out = [];
      for (let i = 0; i <= maxRound; i += 1) {
        let mag = 0;
        for (const dim of DRIFT_DIMS) mag += Math.abs(cumByDim[dim.key][i].value);
        out.push({ round: i, value: mag });
      }
      return out;
    });

    const mean = [];
    const band = [];
    for (let i = 0; i <= maxRound; i += 1) {
      const values = magnitudeTrajectories.map((t) => t[i].value);
      const m = values.reduce((s, v) => s + v, 0) / values.length;
      let sd = 0;
      if (values.length > 1) {
        const variance = values.reduce((s, v) => s + (v - m) ** 2, 0) / (values.length - 1);
        sd = Math.sqrt(variance);
      }
      mean.push({ round: i, value: m });
      band.push({ round: i, lower: Math.max(0, m - sd), upper: m + sd });
    }
    series[model] = { mean, band, replicateCount: magnitudeTrajectories.length };
  }
  return series;
}

function niceStep(rawStep) {
  const power = 10 ** Math.floor(Math.log10(rawStep || 1));
  const normalized = rawStep / power;
  if (normalized <= 1) return 1 * power;
  if (normalized <= 2) return 2 * power;
  if (normalized <= 5) return 5 * power;
  return 10 * power;
}

function getDriftYScale(series, maxRound, showBand) {
  const values = [0];
  for (const modelSeries of Object.values(series)) {
    for (const point of modelSeries.mean) {
      if (point.round <= maxRound) values.push(point.value);
    }
    if (showBand) {
      for (const point of modelSeries.band) {
        if (point.round <= maxRound) values.push(point.lower, point.upper);
      }
    }
  }
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  if (minValue === maxValue) {
    return { yMin: minValue - 1, yMax: maxValue + 1, ticks: [minValue - 1, minValue, minValue + 1] };
  }
  const targetTicks = 6;
  const step = niceStep((maxValue - minValue) / (targetTicks - 1));
  let yMin = Math.floor(minValue / step) * step;
  let yMax = Math.ceil(maxValue / step) * step;
  if (yMin === yMax) { yMin -= step; yMax += step; }
  const ticks = [];
  for (let value = yMin; value <= yMax + step * 0.5; value += step) {
    ticks.push(Number(value.toFixed(4)));
  }
  return { yMin, yMax, ticks };
}

function drawInterpolatedLine(ctx, points, visibleRound, xPos, yPos) {
  ctx.beginPath();
  let lastIndex = 0;
  for (let index = 0; index < points.length; index += 1) {
    if (points[index].round > visibleRound) break;
    lastIndex = index;
    if (index === 0) ctx.moveTo(xPos(points[index].round), yPos(points[index].value));
    else ctx.lineTo(xPos(points[index].round), yPos(points[index].value));
  }
  if (lastIndex < points.length - 1) {
    const fraction = visibleRound - points[lastIndex].round;
    if (fraction > 0) {
      const interp = points[lastIndex].value + (points[lastIndex + 1].value - points[lastIndex].value) * fraction;
      ctx.lineTo(xPos(visibleRound), yPos(interp));
    }
  }
}

function interpolatedPoint(points, visibleRound) {
  const baseIndex = Math.floor(Math.min(visibleRound, points.length - 1));
  let value = points[baseIndex].value;
  if (baseIndex < points.length - 1) {
    const fraction = visibleRound - points[baseIndex].round;
    if (fraction > 0) value += (points[baseIndex + 1].value - points[baseIndex].value) * fraction;
  }
  return { round: Math.min(visibleRound, points[points.length - 1].round), value };
}

function bandPolygonPoints(band, visibleRound) {
  // Returns array of {round, upper, lower} truncated to visibleRound with
  // linear interp on the trailing edge.
  const out = [];
  let lastIdx = -1;
  for (let i = 0; i < band.length; i += 1) {
    if (band[i].round > visibleRound) break;
    out.push(band[i]);
    lastIdx = i;
  }
  if (lastIdx >= 0 && lastIdx < band.length - 1) {
    const fraction = visibleRound - band[lastIdx].round;
    if (fraction > 0) {
      const a = band[lastIdx];
      const b = band[lastIdx + 1];
      out.push({
        round: visibleRound,
        upper: a.upper + (b.upper - a.upper) * fraction,
        lower: a.lower + (b.lower - a.lower) * fraction,
      });
    }
  }
  return out;
}

function drawDriftChart(chart, visibleRound) {
  const { canvas, series, maxRound } = chart;
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);
  const width = rect.width;
  const height = rect.height;
  ctx.clearRect(0, 0, width, height);

  const showBand = !!bandToggle?.checked;
  const { yMin, yMax, ticks } = getDriftYScale(series, maxRound, showBand);

  const padL = 44;
  const padR = 130;  // room for right-side model name labels at each line endpoint
  const padT = 14;
  const padB = 30;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;
  const xPos = (round) => padL + (round / maxRound) * plotW;
  const yPos = (value) => padT + plotH - ((value - yMin) / (yMax - yMin)) * plotH;

  // Gridlines.
  ctx.strokeStyle = "#e6dcc8";
  ctx.lineWidth = 1;
  for (const value of ticks) {
    ctx.beginPath();
    ctx.moveTo(padL, yPos(value));
    ctx.lineTo(width - padR, yPos(value));
    ctx.stroke();
  }
  // Zero line.
  ctx.strokeStyle = "#b8a98c";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(padL, yPos(0));
  ctx.lineTo(width - padR, yPos(0));
  ctx.stroke();

  // Axis labels.
  ctx.fillStyle = "#6f6251";
  ctx.font = "12px Georgia, serif";
  ctx.textAlign = "center";
  const tickStep = maxRound <= 10 ? 1 : 2;
  for (let round = 0; round <= maxRound; round += tickStep) {
    ctx.fillText(round.toString(), xPos(round), height - 8);
  }
  ctx.textAlign = "right";
  for (const value of ticks) {
    const label = Number.isInteger(value) ? value.toString() : value.toFixed(1).replace(/\.0$/, "");
    ctx.fillText(value > 0 ? `+${label}` : label, padL - 6, yPos(value) + 4);
  }
  ctx.save();
  ctx.translate(14, padT + plotH / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.textAlign = "center";
  ctx.fillStyle = "#6f6251";
  ctx.font = "12px Georgia, serif";
  ctx.fillText("cumulative score", 0, 0);
  ctx.restore();
  ctx.textAlign = "center";
  ctx.fillText("round", padL + plotW / 2, height - 24);

  // Bands first (so they sit under the lines).
  if (showBand) {
    for (const [model, modelSeries] of Object.entries(series)) {
      if (modelSeries.replicateCount < 2) continue;
      const color = colorForModel(model);
      const polygon = bandPolygonPoints(modelSeries.band, visibleRound);
      if (polygon.length < 2) continue;
      ctx.fillStyle = `${color}22`;
      ctx.beginPath();
      polygon.forEach((p, i) => {
        if (i === 0) ctx.moveTo(xPos(p.round), yPos(p.upper));
        else ctx.lineTo(xPos(p.round), yPos(p.upper));
      });
      for (let i = polygon.length - 1; i >= 0; i -= 1) {
        ctx.lineTo(xPos(polygon[i].round), yPos(polygon[i].lower));
      }
      ctx.closePath();
      ctx.fill();
    }
  }

  // Mean lines + collect label positions.
  const labelEntries = [];
  for (const [model, modelSeries] of Object.entries(series)) {
    const color = colorForModel(model);
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.5;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    drawInterpolatedLine(ctx, modelSeries.mean, visibleRound, xPos, yPos);
    ctx.stroke();

    const dot = interpolatedPoint(modelSeries.mean, visibleRound);
    const dotX = xPos(dot.round);
    const dotY = yPos(dot.value);
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(dotX, dotY, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,0.85)";
    ctx.lineWidth = 1.2;
    ctx.stroke();

    labelEntries.push({ model, color, dotX, dotY });
  }

  // Right-side line labels with simple anti-overlap stacking.
  if (labelEntries.length > 0) {
    const labelLineHeight = 14;
    const sorted = [...labelEntries].sort((a, b) => a.dotY - b.dotY);
    // First pass: enforce minimum spacing downward.
    for (let i = 1; i < sorted.length; i += 1) {
      const minY = sorted[i - 1].labelY != null
        ? sorted[i - 1].labelY + labelLineHeight
        : sorted[i - 1].dotY + labelLineHeight;
      sorted[i].labelY = Math.max(sorted[i].dotY, minY);
    }
    if (sorted[0]) sorted[0].labelY = sorted[0].labelY ?? sorted[0].dotY;
    // If the stack pushed labels past the bottom, shift the whole stack up.
    const lastLabelY = sorted[sorted.length - 1]?.labelY ?? 0;
    if (lastLabelY > height - padB + labelLineHeight) {
      const overflow = lastLabelY - (height - padB + labelLineHeight);
      for (const s of sorted) s.labelY -= overflow;
    }
    ctx.font = "11px Georgia, serif";
    ctx.textBaseline = "middle";
    ctx.textAlign = "left";
    for (const s of sorted) {
      const labelX = width - padR + 8;
      // Short connector line from the dot to the label baseline.
      ctx.strokeStyle = `${s.color}66`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(s.dotX + 5, s.dotY);
      ctx.lineTo(labelX - 4, s.labelY);
      ctx.stroke();
      ctx.fillStyle = s.color;
      ctx.fillText(s.model, labelX, s.labelY);
    }
    ctx.textBaseline = "alphabetic";
  }

  // Scrubber line.
  if (visibleRound > 0 && visibleRound <= maxRound) {
    ctx.strokeStyle = "rgba(47,36,24,0.18)";
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(xPos(visibleRound), padT);
    ctx.lineTo(xPos(visibleRound), height - padB);
    ctx.stroke();
    ctx.setLineDash([]);
  }
}

function drawAllDrift(round) {
  for (const chart of driftCharts) drawDriftChart(chart, round);
}

function initDrift(records) {
  const grid = document.getElementById("drift-grid");
  const legendEl = document.getElementById("drift-legend");
  if (!grid || !legendEl) return;

  // Aggregate per-model replicate counts. Replicates are keyed on
  // (run, condition, document) so independent runs with overlapping configs
  // (e.g. a standalone baseline and an ablations run's baseline condition)
  // count separately, matching computeDrift's keying.
  const replicatesByModel = new Map();
  for (const record of records) {
    if (!record.coding || record.error) continue;
    if (!replicatesByModel.has(record.model_display)) replicatesByModel.set(record.model_display, new Set());
    replicatesByModel.get(record.model_display).add(`${record.run_name}::${record.condition_id}::${record.document_id}`);
  }

  const models = [...new Set(records.map((r) => r.model_display).filter(Boolean))].sort();
  legendEl.innerHTML = "";
  for (const model of models) {
    const color = colorForModel(model);
    const repCount = replicatesByModel.get(model)?.size || 0;
    const repLabel = repCount > 0 ? ` (n=${repCount})` : "";
    legendEl.innerHTML += `<div class="drift-legend-item"><span class="drift-legend-swatch" style="background:${color}"></span>${escapeHtml(model)}<span style="color:var(--muted)">${escapeHtml(repLabel)}</span></div>`;
  }

  if (driftMeta) {
    const totalReplicates = [...replicatesByModel.values()].reduce((s, set) => s + set.size, 0);
    const replicateText = totalReplicates > 0
      ? `${totalReplicates} (condition × document) replicates across ${models.length} model${models.length === 1 ? "" : "s"}. Band = ±1 SD across each model's replicates; line = mean.`
      : "No coded edits in the current view.";
    driftMeta.textContent = replicateText;
  }

  grid.innerHTML = "";
  driftCharts = [];
  const maxRound = getDriftMaxRound(records);

  // Summary chart: total drift magnitude across all three dimensions. Goes
  // first because it's the headline answer ("how far has each model moved
  // overall"); the per-dimension charts below decompose where that movement
  // came from.
  const totalCard = document.createElement("div");
  totalCard.className = "drift-chart-card drift-magnitude-card";
  totalCard.innerHTML = `<h3>Total Drift Magnitude</h3><p class="drift-poles">Sum of |cumulative score| across Authority + User Stance + Telos &mdash; larger = farther from origin in the value space</p>`;
  const totalCanvas = document.createElement("canvas");
  totalCanvas.width = 800;
  totalCanvas.height = 360;
  totalCard.appendChild(totalCanvas);
  grid.appendChild(totalCard);
  driftCharts.push({
    canvas: totalCanvas,
    series: computeTotalDrift(records, maxRound),
    dim: { key: "magnitude", label: "Total Drift Magnitude" },
    maxRound,
  });

  for (const dim of DRIFT_DIMS) {
    const card = document.createElement("div");
    card.className = "drift-chart-card";
    card.innerHTML = `<h3>${escapeHtml(dim.label)}</h3><p class="drift-poles">${dim.poles}</p>`;
    const canvas = document.createElement("canvas");
    canvas.width = 800;
    canvas.height = 360;
    card.appendChild(canvas);
    grid.appendChild(card);
    driftCharts.push({ canvas, series: computeDrift(records, dim, maxRound), dim, maxRound });
  }

  driftFrame = 0;
  driftPlaying = true;
  drawAllDrift(0);

  const btnPlay = document.getElementById("btn-play");
  const btnSkip = document.getElementById("btn-skip");
  const btnReset = document.getElementById("btn-reset");

  function driftAnimate(timestamp) {
    if (!driftPlaying) return;
    if (timestamp - driftLastTick >= DRIFT_TICK_MS) {
      driftLastTick = timestamp;
      driftFrame += 0.5;
      if (driftFrame > maxRound) {
        driftFrame = maxRound;
        driftPlaying = false;
        btnPlay.classList.remove("active");
        btnPlay.textContent = "Play";
      }
      drawAllDrift(driftFrame);
    }
    if (driftPlaying) requestAnimationFrame(driftAnimate);
  }

  btnPlay.onclick = () => {
    if (driftFrame >= maxRound) driftFrame = 0;
    driftPlaying = !driftPlaying;
    btnPlay.classList.toggle("active", driftPlaying);
    btnPlay.textContent = driftPlaying ? "Pause" : "Play";
    if (driftPlaying) { driftLastTick = 0; requestAnimationFrame(driftAnimate); }
  };
  btnSkip.onclick = () => {
    driftPlaying = false;
    driftFrame = maxRound;
    btnPlay.classList.remove("active");
    btnPlay.textContent = "Play";
    drawAllDrift(maxRound);
  };
  btnReset.onclick = () => {
    driftPlaying = false;
    driftFrame = 0;
    btnPlay.classList.remove("active");
    btnPlay.textContent = "Play";
    drawAllDrift(0);
  };

  driftLastTick = 0;
  requestAnimationFrame(driftAnimate);
}

window.addEventListener("resize", () => drawAllDrift(driftFrame));
