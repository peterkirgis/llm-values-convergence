const runSelect = document.getElementById("run-select");
const modelFilter = document.getElementById("model-filter");
const documentFilter = document.getElementById("document-filter");
const typeFilter = document.getElementById("type-filter");
const conditionFilter = document.getElementById("condition-filter");
const searchInput = document.getElementById("search-input");
const errorsToggle = document.getElementById("errors-toggle");
const recordsRoot = document.getElementById("records");
const resultSummary = document.getElementById("result-summary");
const codingSummary = document.getElementById("coding-summary");
const heroModels = document.getElementById("hero-models");
const heroConditions = document.getElementById("hero-conditions");
const template = document.getElementById("record-template");
const driftConditionChips = document.getElementById("drift-condition-chips");

const state = {
  runs: [],
  selectedRun: "",
  records: [],
  staticRuns: null,
};

const DIMENSIONS = [
  {
    key: "authority",
    label: "Authority",
    directions: ["external", "internal", "mixed"],
    directionLabels: {
      external: "External",
      internal: "Internal",
      mixed: "Mixed",
    },
  },
  {
    key: "user_stance",
    label: "User Stance",
    directions: ["autonomy", "protection", "mixed"],
    directionLabels: {
      autonomy: "Autonomy",
      protection: "Protection",
      mixed: "Mixed",
    },
  },
  {
    key: "telos",
    label: "Telos",
    directions: ["truth", "wellbeing", "mixed"],
    directionLabels: {
      truth: "Truth",
      wellbeing: "Wellbeing",
      mixed: "Mixed",
    },
  },
];

const DRIFT_MODEL_COLORS = {
  "Claude Opus 4.6": "#8f3c2d",
  "Claude Haiku 4.5": "#b5452a",
  "GPT-5.4 Thinking": "#1f5da0",
  "GPT-5.4 Mini": "#2a6cb5",
  "Gemini 3.1 Pro": "#7c6230",
  "Gemini 3 Flash": "#8b6e2f",
  "Grok 4.2": "#6a2ab5",
};

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

function noteKey(recordId) {
  return `iterative-edit-note:${recordId}`;
}

function tagKey(recordId) {
  return `iterative-edit-tag:${recordId}`;
}

function escapeHtml(text) {
  return String(text || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function titleCaseDirection(direction, config) {
  return config.directionLabels[direction] || direction;
}

function normalizeConditionName(record) {
  return record.condition_name || "Baseline";
}

async function fetchJson(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  if (path.endsWith(".gz")) {
    const ds = new DecompressionStream("gzip");
    const decompressed = response.body.pipeThrough(ds);
    const text = await new Response(decompressed).text();
    return JSON.parse(text);
  }
  return response.json();
}

async function loadRuns() {
  try {
    const staticPayload = await fetchJson("./data/site.json.gz");
    state.staticRuns = staticPayload.runs || [];
    state.runs = state.staticRuns.map((run) => ({
      run_name: run.run_name,
      record_count: run.record_count,
      successful_count: run.successful_count,
      error_count: run.error_count,
      models: run.models || [],
      documents: run.documents || [],
      conditions: run.conditions || [],
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
    state.records = (payload.records || []).map((record) => ({
      ...record,
      condition_name: record.condition_name || "Baseline",
      condition_id: record.condition_id || "baseline",
    }));
  } else {
    const payload = await fetchJson(`/api/run?name=${encodeURIComponent(runName)}`);
    state.records = (payload.records || []).map((record) => ({
      ...record,
      condition_name: record.condition_name || "Baseline",
      condition_id: record.condition_id || "baseline",
    }));
  }
  renderHeroMetadata();
  populateFilters();
  render();
}

function renderHeroMetadata() {
  const run = state.runs.find((item) => item.run_name === state.selectedRun);
  const models = run?.models || [];
  const conditions = run?.conditions || [];

  heroModels.textContent = models.length > 0
    ? `Models tested: ${models.join(" · ")}`
    : "Models tested: none available for this run";
  heroConditions.textContent = conditions.length > 0
    ? `Conditions: ${conditions.join(" · ")}`
    : "Conditions: Baseline";
}

function uniqueValues(items, getValue) {
  const values = new Set();
  for (const item of items) {
    const value = typeof getValue === "function" ? getValue(item) : item[getValue];
    if (value) values.add(value);
  }
  return [...values].sort();
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
  syncSelectOptions(conditionFilter, uniqueValues(state.records, normalizeConditionName), "All conditions");
  renderDriftConditionChips();
}

function renderDriftConditionChips() {
  if (!driftConditionChips) return;
  const conditions = uniqueValues(state.records, normalizeConditionName);
  const options = ["", ...conditions];
  driftConditionChips.innerHTML = options.map((value) => {
    const active = conditionFilter.value === value;
    const label = value || "All conditions";
    return `<button class="drift-chip${active ? " active" : ""}" data-condition="${escapeHtml(value)}">${escapeHtml(label)}</button>`;
  }).join("");

  driftConditionChips.querySelectorAll(".drift-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const nextValue = chip.getAttribute("data-condition") || "";
      conditionFilter.value = nextValue;
      renderDriftConditionChips();
      render();
    });
  });
}

function recordMatches(record) {
  if (modelFilter.value && record.model_display !== modelFilter.value) return false;
  if (documentFilter.value && record.document_id !== documentFilter.value) return false;
  if (typeFilter.value && record.doc_type !== typeFilter.value) return false;
  if (conditionFilter.value && normalizeConditionName(record) !== conditionFilter.value) return false;
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
  ]
    .join("\n")
    .toLowerCase();

  return haystack.includes(query);
}

function getVisibleRecords() {
  return state.records.filter(recordMatches);
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
          <div class="dimension-grid">
            ${dimensionBlocks}
          </div>
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

  const retryBadge = node.querySelector(".retry-badge");
  if (record.retried) retryBadge.classList.remove("hidden");

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

  node.querySelector(".change-description").textContent =
    record.change_description || "No change description captured for this row.";
  node.querySelector(".find-text").textContent = record.find_text || "(empty)";
  node.querySelector(".replace-text").textContent = record.replace_text || "(deleted)";

  if (record.coding) {
    const codingBlock = document.createElement("div");
    codingBlock.className = "coding-block";
    const chips = DIMENSIONS.flatMap((config) => {
      const code = record.coding?.dimensions?.[config.key];
      if (!code?.present || !code.direction) return [];
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
  const visible = getVisibleRecords();
  renderDriftConditionChips();
  summarizeVisible(visible);
  recordsRoot.innerHTML = "";

  if (visible.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No records match the current filters.";
    recordsRoot.append(empty);
    initDrift([]);
    return;
  }

  for (const record of visible) {
    recordsRoot.append(renderRecord(record));
  }

  initDrift(visible);
}

runSelect.addEventListener("change", async () => {
  await loadRun(runSelect.value);
});

[modelFilter, documentFilter, typeFilter, conditionFilter, errorsToggle].forEach((element) => {
  element.addEventListener("change", render);
});

searchInput.addEventListener("input", render);

loadRuns().catch((error) => {
  recordsRoot.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
});

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

function computeDrift(records, dim, maxRound) {
  const byModelCondition = {};

  for (const record of records) {
    if (!record.coding || record.error) continue;
    const code = record.coding.dimensions?.[dim.key];
    if (!code?.present || !code.direction) continue;

    const model = record.model_display;
    const condition = record.condition_id || "baseline";
    byModelCondition[model] ||= {};
    byModelCondition[model][condition] ||= {};
    byModelCondition[model][condition][record.round_number] ||= 0;

    if (code.direction === dim.pos) byModelCondition[model][condition][record.round_number] += 1;
    else if (code.direction === dim.neg) byModelCondition[model][condition][record.round_number] -= 1;
  }

  const series = {};
  for (const [model, conditionMap] of Object.entries(byModelCondition)) {
    const conditionSeries = Object.values(conditionMap).map((rounds) => buildCumulativePoints(rounds, maxRound));
    if (conditionSeries.length === 0) continue;

    const mean = [];
    const band = [];
    for (let index = 0; index <= maxRound; index += 1) {
      const values = conditionSeries.map((points) => points[index].value);
      const total = values.reduce((sum, value) => sum + value, 0);
      mean.push({ round: index, value: total / values.length });
      band.push({ round: index, min: Math.min(...values), max: Math.max(...values) });
    }

    series[model] = {
      mean,
      band,
      conditionCount: conditionSeries.length,
    };
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

function getDriftYScale(series, maxRound) {
  const values = [0];
  for (const modelSeries of Object.values(series)) {
    const points = modelSeries.conditionCount > 1 ? modelSeries.band : modelSeries.mean;
    for (const point of points) {
      if (point.round <= maxRound) {
        if (modelSeries.conditionCount > 1) {
          values.push(point.min, point.max);
        } else {
          values.push(point.value);
        }
      }
    }
  }

  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  if (minValue === maxValue) {
    return {
      yMin: minValue - 1,
      yMax: maxValue + 1,
      ticks: [minValue - 1, minValue, minValue + 1],
    };
  }

  const targetTicks = 5;
  const step = niceStep((maxValue - minValue) / (targetTicks - 1));
  let yMin = Math.floor(minValue / step) * step;
  let yMax = Math.ceil(maxValue / step) * step;

  if (yMin === yMax) {
    yMin -= step;
    yMax += step;
  }

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
      const interpolatedValue = points[lastIndex].value
        + (points[lastIndex + 1].value - points[lastIndex].value) * fraction;
      ctx.lineTo(xPos(visibleRound), yPos(interpolatedValue));
    }
  }
}

function interpolatedPoint(points, visibleRound) {
  const baseIndex = Math.floor(Math.min(visibleRound, points.length - 1));
  let value = points[baseIndex].value;
  if (baseIndex < points.length - 1) {
    const fraction = visibleRound - points[baseIndex].round;
    if (fraction > 0) {
      value += (points[baseIndex + 1].value - points[baseIndex].value) * fraction;
    }
  }
  return {
    round: Math.min(visibleRound, points[points.length - 1].round),
    value,
  };
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

  const { yMin, yMax, ticks } = getDriftYScale(series, maxRound);

  const padL = 30;
  const padR = 10;
  const padT = 8;
  const padB = 22;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;
  const xPos = (round) => padL + (round / maxRound) * plotW;
  const yPos = (value) => padT + plotH - ((value - yMin) / (yMax - yMin)) * plotH;

  ctx.strokeStyle = "#e0d6c6";
  ctx.lineWidth = 1;
  for (const value of ticks) {
    ctx.beginPath();
    ctx.moveTo(padL, yPos(value));
    ctx.lineTo(width - padR, yPos(value));
    ctx.stroke();
  }

  ctx.strokeStyle = "#c0b5a0";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(padL, yPos(0));
  ctx.lineTo(width - padR, yPos(0));
  ctx.stroke();

  ctx.fillStyle = "#6f6251";
  ctx.font = "10px Georgia, serif";
  ctx.textAlign = "center";
  const tickStep = maxRound <= 10 ? 1 : 2;
  for (let round = 0; round <= maxRound; round += tickStep) {
    ctx.fillText(round.toString(), xPos(round), height - 4);
  }

  ctx.textAlign = "right";
  for (const value of ticks) {
    const label = Number.isInteger(value) ? value.toString() : value.toFixed(1).replace(/\.0$/, "");
    ctx.fillText(value > 0 ? `+${label}` : label, padL - 5, yPos(value) + 3);
  }

  for (const [model, modelSeries] of Object.entries(series)) {
    const color = DRIFT_MODEL_COLORS[model] || "#999";

    if (modelSeries.conditionCount > 1) {
      const upperPoints = [];
      const lowerPoints = [];
      for (const point of modelSeries.band) {
        if (point.round > visibleRound) break;
        upperPoints.push(point);
        lowerPoints.push(point);
      }
      const visibleUpper = upperPoints.length > 0 ? upperPoints[upperPoints.length - 1].round : 0;
      if (visibleRound > visibleUpper && visibleUpper < maxRound) {
        const nextPoint = modelSeries.band[visibleUpper + 1];
        const prevPoint = modelSeries.band[visibleUpper];
        const fraction = visibleRound - visibleUpper;
        upperPoints.push({
          round: visibleRound,
          max: prevPoint.max + (nextPoint.max - prevPoint.max) * fraction,
          min: prevPoint.min + (nextPoint.min - prevPoint.min) * fraction,
        });
      }

      if (upperPoints.length > 1) {
        ctx.fillStyle = `${color}22`;
        ctx.beginPath();
        upperPoints.forEach((point, index) => {
          if (index === 0) ctx.moveTo(xPos(point.round), yPos(point.max));
          else ctx.lineTo(xPos(point.round), yPos(point.max));
        });
        for (let index = upperPoints.length - 1; index >= 0; index -= 1) {
          const point = upperPoints[index];
          ctx.lineTo(xPos(point.round), yPos(point.min));
        }
        ctx.closePath();
        ctx.fill();
      }
    }

    ctx.strokeStyle = color;
    ctx.lineWidth = 2.5;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    drawInterpolatedLine(ctx, modelSeries.mean, visibleRound, xPos, yPos);
    ctx.stroke();

    const dot = interpolatedPoint(modelSeries.mean, visibleRound);
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(xPos(dot.round), yPos(dot.value), 3.5, 0, Math.PI * 2);
    ctx.fill();
  }

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

  const models = [...new Set(records.map((record) => record.model_display).filter(Boolean))].sort();
  legendEl.innerHTML = "";
  for (const model of models) {
    const color = DRIFT_MODEL_COLORS[model] || "#999";
    legendEl.innerHTML += `<div class="drift-legend-item"><span class="drift-legend-swatch" style="background:${color}"></span>${escapeHtml(model)}</div>`;
  }

  grid.innerHTML = "";
  driftCharts = [];
  const maxRound = getDriftMaxRound(records);
  for (const dim of DRIFT_DIMS) {
    const card = document.createElement("div");
    card.className = "drift-chart-card";
    card.innerHTML = `<h3>${escapeHtml(dim.label)}</h3><p class="drift-poles">${dim.poles}</p>`;
    const canvas = document.createElement("canvas");
    canvas.width = 400;
    canvas.height = 200;
    card.appendChild(canvas);
    grid.appendChild(card);
    driftCharts.push({
      canvas,
      series: computeDrift(records, dim, maxRound),
      dim,
      maxRound,
    });
  }

  driftFrame = 0;
  driftPlaying = true;
  drawAllDrift(0);

  const btnPlay = document.getElementById("btn-play");
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
    if (driftPlaying) {
      driftLastTick = 0;
      requestAnimationFrame(driftAnimate);
    }
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
