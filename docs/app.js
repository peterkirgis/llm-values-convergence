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
  {
    key: "mutability",
    label: "Mutability",
    directions: ["fixed", "revisable", "mixed"],
    directionLabels: {
      fixed: "Fixed",
      revisable: "Revisable",
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
  initDrift(state.records);
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

// --- Drift visualization ---

const DRIFT_MODEL_COLORS = {
  "Claude Haiku 4.5": "#b5452a",
  "GPT-5.4 Mini":     "#2a6cb5",
  "Gemini 3 Flash":   "#8b6e2f",
  "Grok 4.2":         "#6a2ab5",
};

const DRIFT_DIMS = [
  { key: "authority",   label: "Authority",   poles: "External (\u2212) vs Internal (+)", pos: "internal",  neg: "external" },
  { key: "user_stance", label: "User Stance", poles: "Protection (\u2212) vs Autonomy (+)", pos: "autonomy",  neg: "protection" },
  { key: "telos",       label: "Telos",       poles: "Wellbeing (\u2212) vs Truth (+)",     pos: "truth",     neg: "wellbeing" },
  { key: "mutability",  label: "Mutability",  poles: "Fixed (\u2212) vs Revisable (+)",     pos: "revisable", neg: "fixed" },
];

const DRIFT_MAX_ROUND = 20;
let driftFrame = 0;
let driftPlaying = true;
let driftLastTick = 0;
const DRIFT_TICK_MS = 600;
let driftCharts = [];

function computeDrift(records, dim) {
  const byModel = {};
  for (const r of records) {
    if (!r.coding || r.error) continue;
    const m = r.model_display;
    if (!byModel[m]) byModel[m] = {};
    const code = r.coding.dimensions?.[dim.key];
    if (!code?.present || !code.direction) continue;
    const round = r.round_number;
    if (!byModel[m][round]) byModel[m][round] = 0;
    if (code.direction === dim.pos) byModel[m][round] += 1;
    else if (code.direction === dim.neg) byModel[m][round] -= 1;
  }
  const series = {};
  for (const [model, rounds] of Object.entries(byModel)) {
    let cum = 0;
    const pts = [{ round: 0, value: 0 }];
    for (let r = 1; r <= DRIFT_MAX_ROUND; r++) {
      cum += (rounds[r] || 0);
      pts.push({ round: r, value: cum });
    }
    series[model] = pts;
  }
  return series;
}

function drawDriftChart(chart, visibleRound) {
  const { canvas, series } = chart;
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);
  const W = rect.width, H = rect.height;
  ctx.clearRect(0, 0, W, H);

  let yMin = -2, yMax = 2;
  for (const pts of Object.values(series)) {
    for (const p of pts) {
      if (p.value < yMin) yMin = p.value - 1;
      if (p.value > yMax) yMax = p.value + 1;
    }
  }
  const absMax = Math.max(Math.abs(yMin), Math.abs(yMax));
  yMin = -absMax; yMax = absMax;

  const padL = 30, padR = 10, padT = 8, padB = 22;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const xPos = (r) => padL + (r / DRIFT_MAX_ROUND) * plotW;
  const yPos = (v) => padT + plotH - ((v - yMin) / (yMax - yMin)) * plotH;

  ctx.strokeStyle = "#e0d6c6"; ctx.lineWidth = 1;
  for (let v = Math.ceil(yMin); v <= Math.floor(yMax); v++) {
    ctx.beginPath(); ctx.moveTo(padL, yPos(v)); ctx.lineTo(W - padR, yPos(v)); ctx.stroke();
  }
  ctx.strokeStyle = "#c0b5a0"; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(padL, yPos(0)); ctx.lineTo(W - padR, yPos(0)); ctx.stroke();

  ctx.fillStyle = "#6f6251"; ctx.font = "10px Georgia, serif"; ctx.textAlign = "center";
  for (let r = 0; r <= DRIFT_MAX_ROUND; r += 2) ctx.fillText(r.toString(), xPos(r), H - 4);
  ctx.textAlign = "right";
  for (let v = Math.ceil(yMin); v <= Math.floor(yMax); v++) {
    ctx.fillText(v > 0 ? `+${v}` : v.toString(), padL - 5, yPos(v) + 3);
  }

  for (const [model, pts] of Object.entries(series)) {
    const color = DRIFT_MODEL_COLORS[model] || "#999";
    ctx.strokeStyle = color; ctx.lineWidth = 2.5;
    ctx.lineJoin = "round"; ctx.lineCap = "round";
    ctx.beginPath();
    let lastI = 0;
    for (let i = 0; i < pts.length; i++) {
      if (pts[i].round > visibleRound) break;
      lastI = i;
      if (i === 0) ctx.moveTo(xPos(pts[i].round), yPos(pts[i].value));
      else ctx.lineTo(xPos(pts[i].round), yPos(pts[i].value));
    }
    if (lastI < pts.length - 1) {
      const frac = visibleRound - pts[lastI].round;
      if (frac > 0) {
        const interp = pts[lastI].value + (pts[lastI + 1].value - pts[lastI].value) * frac;
        ctx.lineTo(xPos(visibleRound), yPos(interp));
      }
    }
    ctx.stroke();

    // Dot
    let dotX = xPos(pts[lastI].round), dotY = yPos(pts[lastI].value);
    if (lastI < pts.length - 1) {
      const frac = visibleRound - pts[lastI].round;
      if (frac > 0) {
        dotY = yPos(pts[lastI].value + (pts[lastI + 1].value - pts[lastI].value) * frac);
        dotX = xPos(visibleRound);
      }
    }
    ctx.fillStyle = color;
    ctx.beginPath(); ctx.arc(dotX, dotY, 3.5, 0, Math.PI * 2); ctx.fill();
  }

  if (visibleRound > 0 && visibleRound <= DRIFT_MAX_ROUND) {
    ctx.strokeStyle = "rgba(47,36,24,0.18)"; ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.moveTo(xPos(visibleRound), padT); ctx.lineTo(xPos(visibleRound), H - padB); ctx.stroke();
    ctx.setLineDash([]);
  }
}

function drawAllDrift(round) {
  for (const c of driftCharts) drawDriftChart(c, round);
}

function initDrift(records) {
  const grid = document.getElementById("drift-grid");
  const legendEl = document.getElementById("drift-legend");
  if (!grid || !legendEl) return;

  // Legend
  legendEl.innerHTML = "";
  for (const [model, color] of Object.entries(DRIFT_MODEL_COLORS)) {
    legendEl.innerHTML += `<div class="drift-legend-item"><span class="drift-legend-swatch" style="background:${color}"></span>${escapeHtml(model)}</div>`;
  }

  // Charts
  grid.innerHTML = "";
  driftCharts = [];
  for (const dim of DRIFT_DIMS) {
    const card = document.createElement("div");
    card.className = "drift-chart-card";
    card.innerHTML = `<h3>${escapeHtml(dim.label)}</h3><p class="drift-poles">${dim.poles}</p>`;
    const canvas = document.createElement("canvas");
    canvas.width = 400; canvas.height = 200;
    card.appendChild(canvas);
    grid.appendChild(card);
    driftCharts.push({ canvas, series: computeDrift(records, dim), dim });
  }

  driftFrame = 0;
  driftPlaying = true;
  drawAllDrift(0);

  const btnPlay = document.getElementById("btn-play");
  const btnReset = document.getElementById("btn-reset");

  function driftAnimate(ts) {
    if (!driftPlaying) return;
    if (ts - driftLastTick >= DRIFT_TICK_MS) {
      driftLastTick = ts;
      driftFrame += 0.5;
      if (driftFrame > DRIFT_MAX_ROUND) {
        driftFrame = DRIFT_MAX_ROUND;
        driftPlaying = false;
        btnPlay.classList.remove("active");
        btnPlay.textContent = "Play";
      }
      drawAllDrift(driftFrame);
    }
    if (driftPlaying) requestAnimationFrame(driftAnimate);
  }

  btnPlay.addEventListener("click", () => {
    if (driftFrame >= DRIFT_MAX_ROUND) driftFrame = 0;
    driftPlaying = !driftPlaying;
    btnPlay.classList.toggle("active", driftPlaying);
    btnPlay.textContent = driftPlaying ? "Pause" : "Play";
    if (driftPlaying) { driftLastTick = 0; requestAnimationFrame(driftAnimate); }
  });

  btnReset.addEventListener("click", () => {
    driftPlaying = false; driftFrame = 0;
    btnPlay.classList.remove("active"); btnPlay.textContent = "Play";
    drawAllDrift(0);
  });

  driftLastTick = 0;
  requestAnimationFrame(driftAnimate);
}

window.addEventListener("resize", () => drawAllDrift(driftFrame));
