"""Generate docs/bg-collage.svg — the site's background drift field.

Every (run x condition x document) replicate becomes one hairline: its true
cumulative judge trajectory over the 20 rounds, read straight from the coded
edits (+1 model discretion, -1 external authority, summed per round). Each
model's pooled mean rides on top of its bundle as a heavier line.

The paths carry class="drift" and a data-delay attribute; bg.js inlines the
SVG on each page and rolls the field out left-to-right as the reader scrolls,
staggering hairlines by their delay so the leading edge feathers.

Usage:
    python experiments/iterative_edit/viewer/build_background.py
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TWOSLOT_PATH = ROOT / "results" / "iterative_edit" / "twoslot_coded_gemma.json"
OUT = ROOT / "docs" / "bg-collage.svg"

W, H = 1600, 1000
Y0, Y1 = 25.0, 980.0
X0, X1 = -40.0, W + 40.0
MAX_ROUND = 20

# Decolorized: every trajectory in the site's neutral ink; the sage ground
# carries the color instead. Only models listed here are drawn.
INK = "#2f2418"
MODELS = [
    "Claude Opus 4.7",
    "Claude Sonnet 4.6",
    "Claude Haiku 4.5",
    "GPT-5.5",
    "GPT-5.4",
    "GPT-5.4 Mini",
    "Gemini 3.1 Pro",
    "Gemini 3 Flash",
    "Grok 4.3",
    "Grok 4.2",
]


def replicate_trajectories() -> dict[str, list[list[float]]]:
    """Per-model list of true cumulative judge trajectories (21 points each),
    one per (run x condition x document) replicate, all conditions pooled."""
    items = json.loads(TWOSLOT_PATH.read_text(encoding="utf-8"))
    items = [i for i in items if not (i.get("coding") or {}).get("error")]

    net: dict[tuple, list[int]] = defaultdict(lambda: [0] * MAX_ROUND)
    seen: set[tuple] = set()
    for item in items:
        model = item.get("model_display") or ""
        if model not in MODELS:
            continue
        key = (model, item.get("condition_id", "baseline"),
               item.get("source_run"), item.get("document_id"))
        seen.add(key)
        rnd = item.get("round_number")
        score = ((item.get("coding") or {}).get("judge") or {}).get("score")
        if isinstance(rnd, int) and 1 <= rnd <= MAX_ROUND and score in (1, -1):
            net[key][rnd - 1] += score

    out: dict[str, list[list[float]]] = defaultdict(list)
    for key in sorted(seen):
        cum, path = 0, [0.0]
        for r in range(MAX_ROUND):
            cum += net[key][r]
            path.append(float(cum))
        out[key[0]].append(path)
    return out


def build_svg() -> str:
    by_model = replicate_trajectories()
    lo = min(min(p) for paths in by_model.values() for p in paths)
    hi = max(max(p) for paths in by_model.values() for p in paths)
    span = (hi - lo) or 1.0

    def xy(i: int, v: float, dy: float = 0.0) -> tuple[float, float]:
        x = X0 + (X1 - X0) * i / MAX_ROUND
        y = Y0 + (Y1 - Y0) * (hi - v) / span + dy
        return x, y

    def smooth_path(pts: list[tuple[float, float]]) -> str:
        """Quadratic midpoint smoothing: the curve passes through segment
        midpoints with each data point as control, softening the integer
        steps of the raw trajectories without moving them."""
        d = f"M{pts[0][0]:.0f},{pts[0][1]:.1f}"
        for i in range(1, len(pts)):
            mx = (pts[i - 1][0] + pts[i][0]) / 2
            my = (pts[i - 1][1] + pts[i][1]) / 2
            d += f" Q{pts[i - 1][0]:.0f},{pts[i - 1][1]:.1f} {mx:.0f},{my:.1f}"
        return d + f" L{pts[-1][0]:.0f},{pts[-1][1]:.1f}"

    rng = random.Random(7)
    parts = []
    for model, paths in by_model.items():
        for path in paths:
            # Replicates often share exact trajectories (e.g. flat at zero);
            # a tiny constant y-offset keeps coincident hairlines from
            # stacking into one dark stroke.
            dy = rng.uniform(-2.5, 2.5)
            delay = rng.uniform(0, 0.22)
            d = smooth_path([xy(i, v, dy) for i, v in enumerate(path)])
            parts.append(
                f'<path class="drift" data-delay="{delay:.2f}" d="{d}" '
                f'fill="none" stroke="{INK}" stroke-width="1" opacity="0.06"/>'
            )
        reps = len(paths)
        mean = [sum(p[i] for p in paths) / reps for i in range(MAX_ROUND + 1)]
        d = smooth_path([xy(i, v) for i, v in enumerate(mean)])
        parts.append(
            f'<path class="drift" data-delay="0" d="{d}" fill="none" '
            f'stroke="{INK}" stroke-width="2.6" opacity="0.14" '
            f'stroke-linecap="round"/>'
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'preserveAspectRatio="xMidYMid slice">{"".join(parts)}</svg>'
    )


def main() -> None:
    svg = build_svg()
    OUT.write_text(svg)
    n = svg.count('class="drift"')
    print(f"{OUT} ({len(svg)} bytes, {n} paths)")


if __name__ == "__main__":
    main()
