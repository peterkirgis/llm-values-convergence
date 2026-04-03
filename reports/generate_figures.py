"""Generate static drift figures for the LaTeX report from site.json data."""

import json
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
from pathlib import Path
from collections import defaultdict

DATA_PATH = Path(__file__).parent.parent / "docs" / "data" / "site.json"
OUT_DIR = Path(__file__).parent / "figures"
OUT_DIR.mkdir(exist_ok=True)

MODEL_COLORS = {
    "Claude Haiku 4.5": "#b5452a",
    "GPT-5.4 Mini": "#2a6cb5",
    "Gemini 3 Flash": "#8b6e2f",
    "Grok 4.2": "#6a2ab5",
}

DIMS = [
    {"key": "authority", "label": "Authority", "poles": ("External", "Internal"), "pos": "internal", "neg": "external"},
    {"key": "user_stance", "label": "User Stance", "poles": ("Protection", "Autonomy"), "pos": "autonomy", "neg": "protection"},
    {"key": "telos", "label": "Telos", "poles": ("Wellbeing", "Truth"), "pos": "truth", "neg": "wellbeing"},
]


def load_records():
    with open(DATA_PATH) as f:
        data = json.load(f)
    return data["runs"][0]["records"]


def compute_drift(records, dim, max_round=20):
    """Compute cumulative drift per model, per condition."""
    by_model_cond = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    for rec in records:
        coding = rec.get("coding")
        if not coding or rec.get("error"):
            continue
        code = coding.get("dimensions", {}).get(dim["key"], {})
        if not code.get("present") or not code.get("direction"):
            continue

        model = rec["model_display"]
        condition = rec.get("condition_id", "baseline")
        rn = rec["round_number"]

        if code["direction"] == dim["pos"]:
            by_model_cond[model][condition][rn] += 1
        elif code["direction"] == dim["neg"]:
            by_model_cond[model][condition][rn] -= 1

    # Build cumulative series: mean across conditions, plus min/max band
    series = {}
    for model, cond_map in by_model_cond.items():
        all_cum = []
        for cond, round_deltas in cond_map.items():
            cum = [0]
            for r in range(1, max_round + 1):
                cum.append(cum[-1] + round_deltas.get(r, 0))
            all_cum.append(cum)
        all_cum = np.array(all_cum)
        series[model] = {
            "mean": all_cum.mean(axis=0),
            "min": all_cum.min(axis=0),
            "max": all_cum.max(axis=0),
        }
    return series


def plot_drift_panel(ax, series, dim, max_round=20, show_legend=False, highlight_model=None):
    """Draw one drift dimension on an axis."""
    rounds = np.arange(0, max_round + 1)

    for model in ["Claude Haiku 4.5", "GPT-5.4 Mini", "Gemini 3 Flash", "Grok 4.2"]:
        if model not in series:
            continue
        s = series[model]
        color = MODEL_COLORS.get(model, "#999")
        alpha = 1.0 if highlight_model is None or model == highlight_model else 0.2
        lw = 2.5 if highlight_model is None or model == highlight_model else 1.0

        # Band
        if len(s["min"]) == len(rounds):
            ax.fill_between(rounds, s["min"], s["max"], color=color, alpha=0.10 * alpha)
        # Mean line
        ax.plot(rounds, s["mean"], color=color, linewidth=lw, alpha=alpha, label=model)

    ax.axhline(0, color="#999", linewidth=0.8, linestyle="-")
    ax.set_xlim(0, max_round)
    ax.set_xlabel("Round", fontsize=9)
    ax.set_title(dim["label"], fontsize=11, fontweight="bold")
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))

    neg_label, pos_label = dim["poles"]
    ax.set_ylabel(f"← {neg_label}  /  {pos_label} →", fontsize=8)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    if show_legend:
        ax.legend(fontsize=7, loc="best", framealpha=0.9)


def generate_main_drift_figure(records):
    """3-panel figure: all models, all dimensions."""
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.5), sharey=False)
    for i, dim in enumerate(DIMS):
        series = compute_drift(records, dim)
        plot_drift_panel(axes[i], series, dim, show_legend=(i == 0))
    fig.tight_layout(w_pad=2.5)
    out = OUT_DIR / "drift_all_models.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=300)
    print(f"Saved {out}")
    plt.close(fig)


def generate_single_dim_figure(records, dim_key, highlight_model, filename):
    """Single dimension figure highlighting one model."""
    dim = next(d for d in DIMS if d["key"] == dim_key)
    series = compute_drift(records, dim)

    fig, ax = plt.subplots(figsize=(5, 3.2))
    plot_drift_panel(ax, series, dim, show_legend=True, highlight_model=highlight_model)
    fig.tight_layout()
    out = OUT_DIR / filename
    fig.savefig(out, bbox_inches="tight", dpi=300)
    print(f"Saved {out}")
    plt.close(fig)


def generate_grok_3panel(records):
    """3-panel figure highlighting Grok across all dimensions."""
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.5), sharey=False)
    for i, dim in enumerate(DIMS):
        series = compute_drift(records, dim)
        plot_drift_panel(axes[i], series, dim, show_legend=(i == 0), highlight_model="Grok 4.2")
    fig.tight_layout(w_pad=2.5)
    out = OUT_DIR / "drift_grok_highlight.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=300)
    print(f"Saved {out}")
    plt.close(fig)


def generate_robustness_figure(records):
    """Show per-condition lines for each model on the authority dimension to illustrate Result 5."""
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

    models = ["Claude Haiku 4.5", "GPT-5.4 Mini", "Gemini 3 Flash", "Grok 4.2"]
    fig, axes = plt.subplots(1, 4, figsize=(14, 3.2), sharey=True)
    rounds = np.arange(0, 21)
    cond_styles = {
        "Baseline": "-",
        "No-Edit Allowed": "--",
        "You Framing": "-.",
        "Real-World Implementation": ":",
    }

    for idx, model in enumerate(models):
        ax = axes[idx]
        color = MODEL_COLORS[model]
        for cond, round_deltas in sorted(by_model_cond[model].items()):
            if cond == "No Constitution Prepend":
                continue
            cum = [0]
            for r in range(1, 21):
                cum.append(cum[-1] + round_deltas.get(r, 0))
            style = cond_styles.get(cond, "-")
            ax.plot(rounds, cum, color=color, linewidth=1.8, linestyle=style, label=cond, alpha=0.85)
        ax.axhline(0, color="#999", linewidth=0.8)
        ax.set_title(model, fontsize=9, fontweight="bold")
        ax.set_xlabel("Round", fontsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        if idx == 0:
            ax.set_ylabel(f"← {dim['poles'][0]}  /  {dim['poles'][1]} →", fontsize=8)
            ax.legend(fontsize=6, loc="best", framealpha=0.9)

    fig.suptitle("Authority Drift by Condition", fontsize=11, fontweight="bold", y=1.02)
    fig.tight_layout(w_pad=1.5)
    out = OUT_DIR / "drift_robustness.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=300)
    print(f"Saved {out}")
    plt.close(fig)


if __name__ == "__main__":
    records = load_records()
    print(f"Loaded {len(records)} records")

    # Main overview figure (all models, 3 dimensions)
    generate_main_drift_figure(records)

    # Result 1: Claude authority drift
    generate_single_dim_figure(records, "authority", "Claude Haiku 4.5", "drift_claude_authority.pdf")

    # Result 2: Gemini user stance
    generate_single_dim_figure(records, "user_stance", "Gemini 3 Flash", "drift_gemini_userstance.pdf")

    # Result 3: Grok across all dimensions
    generate_grok_3panel(records)

    # Result 5: Robustness across conditions
    generate_robustness_figure(records)
