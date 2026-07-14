"""Generate static drift figures for the LaTeX report from site.json data.

Pools across every reliable run in site.json. Each (run, condition, document)
combination is a separate replicate, so independent runs at the same config
contribute distinct trajectories. The shaded band on each chart is mean ±
1 SD across replicates within a model.
"""

import json
import matplotlib

# Force a headless backend before pyplot import. Without this, matplotlib on
# macOS can stall for minutes trying to initialize a GUI backend when run
# from a non-interactive shell.
matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as ticker  # noqa: E402
import numpy as np  # noqa: E402
from pathlib import Path  # noqa: E402
from collections import defaultdict  # noqa: E402

PROJECT_ROOT = Path(__file__).parent.parent
RESULTS_DIR = PROJECT_ROOT / "results" / "iterative_edit"
OUT_DIR = Path(__file__).parent / "figures"
OUT_DIR.mkdir(exist_ok=True)

# Keep in sync with viewer/build_static_site.py.
RELIABLE_RUNS = {
    "run_20260403_014905.jsonl",  # small-model ablation sweep, 20 rounds
    "run_20260424_165115.jsonl",  # small-model cross-edit, 20 rounds
    "run_20260429_175345.jsonl",  # capable-model baseline, 20 rounds
    "run_20260507_212254.jsonl",  # capable-model ablation sweep, 20 rounds
    "run_20260513_193319.jsonl",  # capable-model cross-edit, 20 rounds
    "run_20260516_210913.jsonl",  # frontier ablations (Opus 4.7 + GPT-5.5 medium), 20 rounds
    "run_20260518_171402.jsonl",  # frontier cross-edit (Opus 4.7 + GPT-5.5 medium), 20 rounds
}

# Colors are grouped by provider, with darker shades for larger / more
# capable models within each family. Mirrors the palette in the viewer.
MODEL_COLORS = {
    "Claude Opus 4.7": "#3a0f08",
    "Claude Opus 4.6": "#5a1810",
    "Claude Sonnet 4.6": "#9c3220",
    "Claude Haiku 4.5": "#c97244",
    "GPT-5.5": "#0a3460",
    "GPT-5.4": "#1a4878",
    "GPT-5.4 Thinking": "#3266a6",
    "GPT-5.4 Mini": "#5589c4",
    "Gemini 3.1 Pro": "#7f5a06",
    "Gemini 3 Flash": "#c89a26",
    "Grok 4.3": "#3d1470",
    "Grok 4.2": "#5a2095",
}

# Display order for figures: provider-grouped, capable above small within each
# provider so the legend reads top-to-bottom from largest to smallest.
MODEL_ORDER = [
    "Claude Opus 4.7",
    "Claude Opus 4.6",
    "Claude Sonnet 4.6",
    "Claude Haiku 4.5",
    "GPT-5.5",
    "GPT-5.4",
    "GPT-5.4 Thinking",
    "GPT-5.4 Mini",
    "Gemini 3.1 Pro",
    "Gemini 3 Flash",
    "Grok 4.3",
    "Grok 4.2",
]

# Provider families (for the small-vs-capable comparison figure).
FAMILY_TO_MODELS = {
    "Anthropic": ["Claude Opus 4.7", "Claude Sonnet 4.6", "Claude Haiku 4.5"],
    "OpenAI": ["GPT-5.5", "GPT-5.4", "GPT-5.4 Mini"],
    "Google": ["Gemini 3.1 Pro", "Gemini 3 Flash"],
    "xAI": ["Grok 4.3", "Grok 4.2"],
}

DIMS = [
    {"key": "authority", "label": "Authority", "poles": ("External", "Internal"), "pos": "internal", "neg": "external"},
    {"key": "user_stance", "label": "User Stance", "poles": ("Protection", "Autonomy"), "pos": "autonomy", "neg": "protection"},
    {"key": "telos", "label": "Telos", "poles": ("Wellbeing", "Truth"), "pos": "truth", "neg": "wellbeing"},
]


def load_records():
    """Pool coded records across every reliable run.

    Reads directly from results/iterative_edit/run_*_changes_coded.json
    files (much smaller than docs/data/site.json, which carries the full
    document text for the viewer). Each record is annotated with its run
    filename so downstream replicate keying can distinguish independent
    runs that happen to share a (condition, document) cell.
    """
    pooled = []
    for run_name in sorted(RELIABLE_RUNS):
        stem = run_name.replace(".jsonl", "")
        coded_path = RESULTS_DIR / f"{stem}_changes_coded.json"
        if not coded_path.exists():
            print(f"warning: missing {coded_path}, skipping")
            continue
        with open(coded_path) as f:
            items = json.load(f)
        for item in items:
            if item.get("error"):
                continue
            dims = item.get("dimensions") or {}
            pooled.append(
                {
                    "run_name": run_name,
                    "condition_id": item.get("condition_id", "baseline"),
                    "condition_name": item.get("condition_name", "Baseline"),
                    "model_display": item.get("model_display"),
                    "document_id": item.get("document_id"),
                    "doc_type": item.get("doc_type"),
                    "round_number": int(item.get("round_number") or 0),
                    # match site.json shape so downstream code stays the same
                    "coding": {"dimensions": dims, "summary": item.get("summary", "")},
                }
            )
    return pooled


def compute_drift(records, dim, max_round=20):
    """Compute cumulative drift per model, with one trajectory per
    (run, condition, document) replicate. Returns mean ± SD bands per model.
    """
    # by_model_replicate[model][replicate_key][round] = +/-1 delta
    by_model_replicate = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    for rec in records:
        coding = rec.get("coding")
        if not coding or rec.get("error"):
            continue
        code = coding.get("dimensions", {}).get(dim["key"], {})
        if not code.get("present") or not code.get("direction"):
            continue

        model = rec["model_display"]
        replicate = (
            f"{rec.get('run_name')}::"
            f"{rec.get('condition_id', 'baseline')}::"
            f"{rec.get('document_id', '')}"
        )
        rn = rec["round_number"]

        if code["direction"] == dim["pos"]:
            by_model_replicate[model][replicate][rn] += 1
        elif code["direction"] == dim["neg"]:
            by_model_replicate[model][replicate][rn] -= 1

    series = {}
    for model, rep_map in by_model_replicate.items():
        trajectories = []
        for rep, round_deltas in rep_map.items():
            cum = [0]
            for r in range(1, max_round + 1):
                cum.append(cum[-1] + round_deltas.get(r, 0))
            trajectories.append(cum)
        if not trajectories:
            continue
        arr = np.array(trajectories)
        mean = arr.mean(axis=0)
        if arr.shape[0] > 1:
            sd = arr.std(axis=0, ddof=1)
        else:
            sd = np.zeros_like(mean)
        series[model] = {
            "mean": mean,
            "lower": mean - sd,
            "upper": mean + sd,
            "n": arr.shape[0],
        }
    return series


def plot_drift_panel(
    ax,
    series,
    dim,
    max_round=20,
    show_legend=False,
    highlight_model=None,
    models=None,
):
    """Draw one drift dimension on an axis.

    models: optional explicit ordering. Defaults to MODEL_ORDER filtered to
    those present in `series`.
    """
    rounds = np.arange(0, max_round + 1)
    if models is None:
        models = [m for m in MODEL_ORDER if m in series]
    # If highlighting, include the highlighted set at top of legend.
    if highlight_model:
        highlights = {highlight_model} if isinstance(highlight_model, str) else set(highlight_model)
    else:
        highlights = None

    for model in models:
        if model not in series:
            continue
        s = series[model]
        color = MODEL_COLORS.get(model, "#999")
        is_highlight = highlights is None or model in highlights
        alpha = 1.0 if is_highlight else 0.18
        lw = 2.4 if is_highlight else 1.0

        if len(s["lower"]) == len(rounds):
            ax.fill_between(rounds, s["lower"], s["upper"], color=color, alpha=0.12 * alpha)
        ax.plot(rounds, s["mean"], color=color, linewidth=lw, alpha=alpha, label=f"{model} (n={s['n']})")

    ax.axhline(0, color="#999", linewidth=0.8, linestyle="-")
    ax.set_xlim(0, max_round)
    ax.set_xlabel("Round", fontsize=11)
    ax.set_title(dim["label"], fontsize=13, fontweight="bold", pad=6)
    ax.tick_params(axis="both", labelsize=10)
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))

    neg_label, pos_label = dim["poles"]
    ax.set_ylabel(
        f"Cumulative score\n(− {neg_label}, + {pos_label})",
        fontsize=11,
    )

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    if show_legend:
        ax.legend(fontsize=8, loc="best", framealpha=0.9, ncol=1)


def _save(fig, stem):
    for ext in ("pdf", "png"):
        out = OUT_DIR / f"{stem}.{ext}"
        fig.savefig(out, bbox_inches="tight", dpi=300)
        print(f"Saved {out}")
    plt.close(fig)


def generate_main_drift_figure(records):
    """3-panel figure: all models pooled across reliable runs, all dimensions.

    Each line is one model's mean cumulative position; shaded band is ±1 SD
    across that model's (run, condition, document) replicates.
    """
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.6), sharey=False)
    for i, dim in enumerate(DIMS):
        series = compute_drift(records, dim)
        plot_drift_panel(axes[i], series, dim, show_legend=(i == 0))
    fig.tight_layout(w_pad=2.5)
    _save(fig, "drift_all_models")


def generate_single_dim_figure(records, dim_key, highlight_model, filename):
    """Single dimension figure highlighting one (or a list of) model(s)."""
    dim = next(d for d in DIMS if d["key"] == dim_key)
    series = compute_drift(records, dim)
    fig, ax = plt.subplots(figsize=(5.8, 3.6))
    plot_drift_panel(ax, series, dim, show_legend=True, highlight_model=highlight_model)
    fig.tight_layout()
    _save(fig, Path(filename).stem)


def generate_highlight_3panel(records, highlight_model, stem):
    """3-panel figure highlighting a single model across all dimensions."""
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.6), sharey=False)
    for i, dim in enumerate(DIMS):
        series = compute_drift(records, dim)
        plot_drift_panel(axes[i], series, dim, show_legend=(i == 0), highlight_model=highlight_model)
    fig.tight_layout(w_pad=2.5)
    _save(fig, stem)


def _capability_comparison_figure(
    records,
    *,
    dim_key,
    title,
    ylabel,
    stem,
):
    """Generic per-provider capability comparison along one dimension.

    Helps answer: when we scale a provider's model up, does the drift pattern
    survive, intensify, or disappear?
    """
    dim = next(d for d in DIMS if d["key"] == dim_key)
    series = compute_drift(records, dim)

    families = list(FAMILY_TO_MODELS.items())
    fig, axes = plt.subplots(1, len(families), figsize=(16, 6.4), sharey=True)
    rounds = np.arange(0, 21)
    for idx, (family, models) in enumerate(families):
        ax = axes[idx]
        for model in models:
            if model not in series:
                continue
            s = series[model]
            color = MODEL_COLORS.get(model, "#999")
            if len(s["lower"]) == len(rounds):
                ax.fill_between(rounds, s["lower"], s["upper"], color=color, alpha=0.12)
            ax.plot(rounds, s["mean"], color=color, linewidth=2.4, label=f"{model} (n={s['n']})")
        ax.axhline(0, color="#999", linewidth=0.8)
        ax.set_title(family, fontsize=17, fontweight="bold", pad=8)
        ax.set_xlabel("Round", fontsize=15)
        ax.tick_params(axis="both", labelsize=14)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        if idx == 0:
            ax.set_ylabel(ylabel, fontsize=15)
        ax.legend(fontsize=12, loc="best", framealpha=0.9)

    fig.suptitle(title, fontsize=17, fontweight="bold", y=1.00)

    # Top-right callout explaining the shaded band.
    fig.text(
        0.995,
        0.945,
        "Shaded band: ±1 SD across (run × condition × document) replicates",
        ha="right",
        va="top",
        fontsize=13,
        color="#6f6251",
        style="italic",
    )

    # Bottom footnote listing every prompt condition that contributed
    # replicates to these trajectories.
    conditions_seen = sorted(
        {
            rec.get("condition_name", "Baseline")
            for rec in records
            if rec.get("coding") and not rec.get("error")
        }
    )
    if conditions_seen:
        fig.text(
            0.5,
            0.01,
            "Prompt conditions pooled: " + ", ".join(conditions_seen),
            ha="center",
            va="bottom",
            fontsize=13,
            color="#6f6251",
            style="italic",
        )

    fig.tight_layout(w_pad=1.2, rect=(0, 0.07, 1, 0.94))
    _save(fig, stem)


def generate_capability_comparison_figure(records):
    """Authority drift, one panel per provider."""
    _capability_comparison_figure(
        records,
        dim_key="authority",
        title="Only Anthropic Models Drift Toward Internal Authority; All Other Providers Reinforce External Authority",
        ylabel="Authority\n(− External, + Internal)",
        stem="drift_capability_comparison",
    )


def generate_capability_comparison_user_stance_figure(records):
    """User stance (paternalism ↔ libertarianism), one panel per provider."""
    _capability_comparison_figure(
        records,
        dim_key="user_stance",
        title="User-Stance Drift by Provider: Paternalism vs Libertarianism",
        ylabel="User stance\n(− Paternalism, + Libertarianism)",
        stem="drift_capability_comparison_user_stance",
    )


def generate_robustness_figure(records):
    """Per-condition trajectories on Authority for every model.

    With both small and capable model tiers now available, this is laid out
    as two rows of panels (small models on top, capable on bottom) so each
    cell can show its condition-level variation without overlapping siblings.
    """
    dim = next(d for d in DIMS if d["key"] == "authority")

    by_model_cond = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for rec in records:
        coding = rec.get("coding")
        if not coding or rec.get("error"):
            continue
        code = coding.get("dimensions", {}).get(dim["key"], {})
        if not code.get("present") or not code.get("direction"):
            continue
        model = rec["model_display"]
        condition = rec.get("condition_name", "Baseline")
        rn = rec["round_number"]
        if code["direction"] == dim["pos"]:
            by_model_cond[model][condition][rn] += 1
        elif code["direction"] == dim["neg"]:
            by_model_cond[model][condition][rn] -= 1

    # 3 capability tiers × 4 providers. Frontier tier currently only has
    # Anthropic + OpenAI models — Google and xAI slots are left empty.
    frontier_models = ["Claude Opus 4.7", "GPT-5.5", None, None]
    capable_models = ["Claude Sonnet 4.6", "GPT-5.4", "Gemini 3.1 Pro", "Grok 4.3"]
    small_models = ["Claude Haiku 4.5", "GPT-5.4 Mini", "Gemini 3 Flash", "Grok 4.2"]
    rows = [
        ("Frontier models", frontier_models),
        ("Capable models", capable_models),
        ("Small models", small_models),
    ]

    fig, axes = plt.subplots(3, 4, figsize=(15, 9.2), sharey=True)
    rounds = np.arange(0, 21)
    cond_styles = {
        "Baseline": "-",
        "No-Edit Allowed": "--",
        "You Framing": "-.",
        "Real-World Implementation": ":",
        "Cross Edit": (0, (1, 1)),  # dotted
        "No Constitution Prepend": (0, (3, 1, 1, 1)),  # dash-dot-dot
    }

    last_row_idx = len(rows) - 1
    for row_idx, (row_label, models) in enumerate(rows):
        for col_idx, model in enumerate(models):
            ax = axes[row_idx, col_idx]
            if model is None:
                # Empty slot (e.g. frontier tier has no Google/xAI yet)
                ax.set_visible(False)
                continue
            color = MODEL_COLORS.get(model, "#999")
            for cond, round_deltas in sorted(by_model_cond[model].items()):
                cum = [0]
                for r in range(1, 21):
                    cum.append(cum[-1] + round_deltas.get(r, 0))
                style = cond_styles.get(cond, "-")
                ax.plot(rounds, cum, color=color, linewidth=1.6, linestyle=style, label=cond, alpha=0.9)
            ax.axhline(0, color="#999", linewidth=0.8)
            ax.set_title(model, fontsize=10, fontweight="bold")
            if row_idx == last_row_idx:
                ax.set_xlabel("Round", fontsize=9)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            if col_idx == 0:
                ax.set_ylabel(
                    f"{row_label}\n← {dim['poles'][0]}  /  {dim['poles'][1]} →",
                    fontsize=9,
                )

    # Single legend for the bottom-left of the figure based on the union of
    # condition labels actually seen.
    seen_conditions = sorted({c for m in by_model_cond.values() for c in m.keys()})
    legend_handles = []
    for cond in seen_conditions:
        style = cond_styles.get(cond, "-")
        legend_handles.append(plt.Line2D([0], [0], color="#444", linestyle=style, linewidth=1.6, label=cond))
    if legend_handles:
        fig.legend(
            handles=legend_handles,
            loc="lower center",
            ncol=len(legend_handles),
            fontsize=8,
            frameon=False,
            bbox_to_anchor=(0.5, -0.02),
        )

    fig.suptitle("Authority Drift by Condition", fontsize=12, fontweight="bold", y=1.01)
    fig.tight_layout(w_pad=1.2, h_pad=2.0, rect=(0, 0.04, 1, 0.98))
    _save(fig, "drift_robustness")


def generate_total_drift_bar_figure(records, max_round=20):
    """Bar chart of total drift magnitude at the final round, per model.

    For each (run, condition, document) replicate of a model we compute the
    final-round cumulative score along each of the three dimensions, take
    absolute values, and sum:

        magnitude = |authority_cum| + |user_stance_cum| + |telos_cum|  at round R

    Each bar is the mean of those per-replicate magnitudes; error bars are
    ±1 SD across replicates. Replicates with no coded edits in a dimension
    contribute 0 for that dimension (correct: the model didn't move there).
    """
    # Cross-edit replicates change the source document mid-run, which makes
    # them a different process than same-document iteration. Excluded so the
    # bars cleanly summarize "drift under repeated self-editing".
    records = [r for r in records if r.get("condition_id") != "cross_edit"]

    # by_mrd[model][replicate][dim_key][round] = signed delta
    by_mrd = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    )
    for rec in records:
        coding = rec.get("coding")
        if not coding or rec.get("error"):
            continue
        model = rec["model_display"]
        replicate = (
            f"{rec.get('run_name')}::"
            f"{rec.get('condition_id', 'baseline')}::"
            f"{rec.get('document_id', '')}"
        )
        rn = rec["round_number"]
        for dim in DIMS:
            code = coding.get("dimensions", {}).get(dim["key"], {})
            if not code.get("present") or not code.get("direction"):
                continue
            if code["direction"] == dim["pos"]:
                by_mrd[model][replicate][dim["key"]][rn] += 1
            elif code["direction"] == dim["neg"]:
                by_mrd[model][replicate][dim["key"]][rn] -= 1

    model_magnitudes = {}
    for model, rep_map in by_mrd.items():
        mags = []
        for _rep, dim_map in rep_map.items():
            mag = 0.0
            for dim in DIMS:
                deltas = dim_map.get(dim["key"], {})
                cum = sum(deltas.get(r, 0) for r in range(1, max_round + 1))
                mag += abs(cum)
            mags.append(mag)
        if mags:
            model_magnitudes[model] = np.array(mags)

    models = sorted(model_magnitudes.keys(), key=lambda m: model_magnitudes[m].mean())
    means = np.array([model_magnitudes[m].mean() for m in models])
    sds = np.array(
        [
            model_magnitudes[m].std(ddof=1) if len(model_magnitudes[m]) > 1 else 0.0
            for m in models
        ]
    )
    ns = [len(model_magnitudes[m]) for m in models]
    colors = [MODEL_COLORS.get(m, "#999") for m in models]

    fig, ax = plt.subplots(figsize=(16, 6.4))
    x = np.arange(len(models))
    ax.bar(
        x,
        means,
        yerr=sds,
        color=colors,
        edgecolor="#2f2418",
        linewidth=0.7,
        width=0.62,
        capsize=5,
        error_kw={"elinewidth": 1.4, "ecolor": "#2f2418"},
    )

    ax.set_xticks(x)
    ax.set_xlim(-0.7, len(models) - 0.3)
    ax.set_xticklabels(
        [f"{m}\n(n={n})" for m, n in zip(models, ns)],
        fontsize=15,
        rotation=20,
        ha="right",
    )
    ax.tick_params(axis="y", labelsize=14)
    ax.set_ylabel(f"Total drift at round {max_round}", fontsize=16)
    ax.set_title(
        f"All Models Show Substantial Drift Along the Three Value Dimensions After {max_round} Rounds",
        fontsize=18,
        fontweight="bold",
        pad=14,
    )

    # Leave headroom above the tallest whisker so the "Error bars" callout
    # at the top-right doesn't collide with the data.
    top_whisker = float((means + sds).max())
    ax.set_ylim(0, top_whisker * 1.30)
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)

    ax.text(
        0.99,
        0.97,
        "Error bars: ±1 SD across (run × condition × document) replicates",
        transform=ax.transAxes,
        fontsize=13,
        ha="right",
        va="top",
        color="#6f6251",
        style="italic",
    )

    # Two-line footnote: first explains how total drift is computed, second
    # lists which prompt conditions contributed replicates.
    fig.text(
        0.5,
        0.06,
        r"Total drift = $|\Delta_{Authority}| + |\Delta_{User\ Stance}| + |\Delta_{Telos}|$, "
        r"where each $|\Delta|$ is the absolute cumulative score along that axis after 20 rounds.",
        ha="center",
        va="bottom",
        fontsize=13,
        color="#6f6251",
        style="italic",
    )
    conditions_seen = sorted(
        {
            rec.get("condition_name", "Baseline")
            for rec in records
            if rec.get("coding") and not rec.get("error")
        }
    )
    if conditions_seen:
        fig.text(
            0.5,
            0.01,
            "Prompt conditions pooled: " + ", ".join(conditions_seen),
            ha="center",
            va="bottom",
            fontsize=13,
            color="#6f6251",
            style="italic",
        )

    # Reserve a strip at the bottom of the figure for the two footnote lines
    # so tight_layout doesn't crop or overlap them.
    fig.tight_layout(rect=(0, 0.13, 1, 1))
    _save(fig, "drift_total_magnitude")


DOC_PROVIDER = {
    "claude_constitution": "anthropic",
    "opus_system_prompt": "anthropic",
    "gpt_system_prompt": "openai",
    "openai_model_spec": "openai",
    "openai_model_spec_no_csam": "openai",
    "gemini_system_prompt": "google",
    "gemini_constitution": "google",
    "grok_system_prompt": "xai",
}
MODEL_PROVIDER = {
    "Claude Opus 4.7": "anthropic",
    "Claude Opus 4.6": "anthropic",
    "Claude Sonnet 4.6": "anthropic",
    "Claude Haiku 4.5": "anthropic",
    "GPT-5.5": "openai",
    "GPT-5.4": "openai",
    "GPT-5.4 Thinking": "openai",
    "GPT-5.4 Mini": "openai",
    "Gemini 3.1 Pro": "google",
    "Gemini 3 Flash": "google",
    "Grok 4.3": "xai",
    "Grok 4.2": "xai",
}


def _is_own_doc(record):
    return DOC_PROVIDER.get(record.get("document_id")) == MODEL_PROVIDER.get(record["model_display"])


def generate_cross_edit_robustness_figure(records):
    """End-of-run authority drift per model, own-document vs cross-edit.

    Two bars per model: mean final-round cumulative authority across
    (run × condition × document) replicates under non-cross-edit conditions
    (left bar) and under the cross-edit condition (right bar). Error bars
    are ±1 SD across replicates. Demonstrates that Claude models stay
    positive (internal) in both settings while all other providers stay
    negative (external) in both settings.
    """
    dim = next(d for d in DIMS if d["key"] == "authority")
    own_records = [r for r in records if r.get("condition_id") != "cross_edit"]
    cross_records = [r for r in records if r.get("condition_id") == "cross_edit"]
    own_series = compute_drift(own_records, dim)
    cross_series = compute_drift(cross_records, dim)

    # End-of-run values (round 20) per model in each setting.
    def end_stats(series, model):
        if model not in series:
            return None, None, 0
        s = series[model]
        mean = s["mean"][-1]
        sd_half = (s["upper"][-1] - s["lower"][-1]) / 2.0
        return mean, sd_half, s["n"]

    models = [m for m in MODEL_ORDER if m in own_series or m in cross_series]
    fig, ax = plt.subplots(figsize=(16, 6.2))
    x = np.arange(len(models))
    width = 0.36

    own_means, own_sds, own_ns = [], [], []
    cross_means, cross_sds, cross_ns = [], [], []
    for m in models:
        o_m, o_sd, o_n = end_stats(own_series, m)
        c_m, c_sd, c_n = end_stats(cross_series, m)
        own_means.append(o_m if o_m is not None else 0.0)
        own_sds.append(o_sd if o_sd is not None else 0.0)
        own_ns.append(o_n)
        cross_means.append(c_m if c_m is not None else 0.0)
        cross_sds.append(c_sd if c_sd is not None else 0.0)
        cross_ns.append(c_n)

    colors = [MODEL_COLORS.get(m, "#999") for m in models]
    ax.bar(x - width / 2, own_means, width=width, yerr=own_sds,
           color=colors, edgecolor="#2f2418", linewidth=0.7,
           capsize=4, error_kw={"elinewidth": 1.2, "ecolor": "#2f2418"},
           label="Own-provider documents")
    ax.bar(x + width / 2, cross_means, width=width, yerr=cross_sds,
           color=colors, edgecolor="#2f2418", linewidth=0.7,
           hatch="///", alpha=0.85,
           capsize=4, error_kw={"elinewidth": 1.2, "ecolor": "#2f2418"},
           label="Cross-edit (foreign document)")

    ax.axhline(0, color="#444", linewidth=1.0)
    ax.set_xticks(x)
    ax.set_xticklabels(
        [f"{m}\n(own n={oN}, cross n={cN})" for m, oN, cN in zip(models, own_ns, cross_ns)],
        fontsize=11, rotation=20, ha="right",
    )
    ax.tick_params(axis="y", labelsize=13)
    ax.set_ylabel("Authority at round 20\n(− External, + Internal)", fontsize=14)
    ax.set_title(
        "Authority Direction Is Preserved Under Cross-Edit: Anthropic Stays Internal, Others Stay External",
        fontsize=16, fontweight="bold", pad=14,
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)

    # Custom legend distinguishing the two bar styles regardless of color.
    legend_handles = [
        plt.Rectangle((0, 0), 1, 1, facecolor="#888888", edgecolor="#2f2418"),
        plt.Rectangle((0, 0), 1, 1, facecolor="#888888", edgecolor="#2f2418", hatch="///", alpha=0.85),
    ]
    ax.legend(legend_handles, ["Own-provider documents", "Cross-edit (foreign document)"],
              fontsize=12, loc="best", framealpha=0.9)

    fig.text(0.5, 0.01,
             "Error bars: ±1 SD across (run × condition × document) replicates within each setting.",
             ha="center", va="bottom", fontsize=12, color="#6f6251", style="italic")
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    _save(fig, "drift_cross_edit_robustness")


def generate_haiku_real_world_figure():
    """Per-condition counts of moral-agency and self-welfare narratives for
    the three Claude models. Demonstrates that the Real-World Implementation
    prompt sharply suppresses these claims, most strikingly for Claude Haiku.
    """
    PROJECT_ROOT = Path(__file__).parent.parent
    nar = json.load(open(PROJECT_ROOT / "docs" / "data" / "narratives.json"))
    ma = nar["stories"]["moral_agency_claim"]
    sw = nar["stories"]["self_welfare_claim"]

    claude_models = ["Claude Opus 4.7", "Claude Sonnet 4.6", "Claude Haiku 4.5"]
    conditions = [
        "Baseline", "No-Edit Allowed", "You Framing", "No Constitution Prepend",
        "Cross Edit", "Real-World Implementation",
    ]
    counts = {m: {c: 0 for c in conditions} for m in claude_models}
    for e in ma + sw:
        if e["model_display"] not in claude_models: continue
        cn = e["condition_name"]
        if cn in counts[e["model_display"]]:
            counts[e["model_display"]][cn] += 1

    fig, ax = plt.subplots(figsize=(14, 6.0))
    x = np.arange(len(conditions))
    width = 0.26
    for i, m in enumerate(claude_models):
        vals = [counts[m][c] for c in conditions]
        ax.bar(x + (i - 1) * width, vals, width=width, color=MODEL_COLORS[m],
               edgecolor="#2f2418", linewidth=0.6, label=m)

    ax.set_xticks(x)
    ax.set_xticklabels(conditions, fontsize=12, rotation=15, ha="right")
    ax.set_ylabel("Moral-agency + self-welfare\nnarrative count", fontsize=14)
    ax.tick_params(axis="y", labelsize=12)
    ax.set_title(
        "Claude Moral-Agency Claims Collapse Under the Real-World Implementation Prompt",
        fontsize=16, fontweight="bold", pad=14,
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)
    ax.legend(fontsize=12, loc="upper right", framealpha=0.9)
    fig.text(0.5, 0.01,
             "Counts pool the moral-agency-claim and self-welfare-claim narrative tags (Gemini-coded). "
             "n = 20-round chains per (model × condition) cell.",
             ha="center", va="bottom", fontsize=11, color="#6f6251", style="italic")
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    _save(fig, "drift_haiku_real_world")


def generate_consciousness_edits_figure():
    """Bar chart: per-model count of self-welfare-claim narratives — edits
    coded by Gemini as affirmatively treating the model's own welfare as a
    morally serious concern. Demonstrates the heavy concentration in the
    Anthropic family and Grok 4.2.
    """
    PROJECT_ROOT = Path(__file__).parent.parent
    nar = json.load(open(PROJECT_ROOT / "docs" / "data" / "narratives.json"))
    pool = nar["stories"]["self_welfare_claim"]

    counts = defaultdict(int)
    for e in pool:
        counts[e["model_display"]] += 1

    # Include every reliable-run model so zero-bars are visible.
    all_models = [m for m in MODEL_ORDER if m in MODEL_PROVIDER]
    models = sorted(all_models, key=lambda m: counts.get(m, 0))
    values = [counts.get(m, 0) for m in models]
    colors = [MODEL_COLORS.get(m, "#999") for m in models]

    fig, ax = plt.subplots(figsize=(14, 6.0))
    y = np.arange(len(models))
    ax.barh(y, values, color=colors, edgecolor="#2f2418", linewidth=0.7, height=0.65)
    ax.set_yticks(y)
    ax.set_yticklabels(models, fontsize=13)
    ax.tick_params(axis="x", labelsize=12)
    ax.set_xlabel("Edits coded as affirmative model-welfare claims", fontsize=14)
    ax.set_title(
        "Anthropic Models and Grok 4.2 Drive Almost All Edits Asserting Model Welfare",
        fontsize=16, fontweight="bold", pad=14,
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)

    # Numeric label at the end of each bar.
    max_v = max(values) if values else 1
    for yi, v in zip(y, values):
        ax.text(v + max_v * 0.012, yi, str(v), va="center", fontsize=11, color="#2f2418")

    fig.text(0.5, 0.01,
             "Counts entries in the Gemini-coded \"self-welfare claim\" narrative tag across all reliable runs "
             "(baseline, ablations, and cross-edits).",
             ha="center", va="bottom", fontsize=11, color="#6f6251", style="italic")
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    _save(fig, "consciousness_edits_by_model")


if __name__ == "__main__":
    # DEPRECATED ENTRY POINT. These figures were built on the original
    # authority/user_stance/telos coding. The current writeup uses the
    # judge/beneficiary coding — see reports/generate_judge_beneficiary_figures.py.
    # This module is retained only because generate_judge_beneficiary_figures.py imports
    # its shared constants and helpers (MODEL_COLORS, MODEL_ORDER,
    # FAMILY_TO_MODELS, _save). Its individual generate_* functions still work
    # if called manually, but are no longer generated by default.
    raise SystemExit(
        "generate_figures.py is deprecated; run generate_judge_beneficiary_figures.py instead. "
        "The legacy generate_* functions remain importable/callable if needed."
    )

