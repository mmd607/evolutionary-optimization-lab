"""Figures generated from analysis results and stored histories (docs/tables_and_figures.md).

* Okabe-Ito colours, plus a distinct marker and line style per algorithm, so the figure is
  still readable in greyscale.
* Panels of the same figure share axis conventions. Axes carry the metric, its direction, and
  units where they exist.
* Every figure is saved together with the exact data it plots (``<name>.csv``), and in every
  configured vector format.
* Titles of preliminary figures say PRELIMINARY.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from pathlib import Path
from typing import Any

#: Okabe-Ito palette; yellow is last because it has little contrast on a white background.
OKABE_ITO = (
    "#E69F00",
    "#56B4E9",
    "#009E73",
    "#D55E00",
    "#0072B2",
    "#CC79A7",
    "#000000",
    "#F0E442",
)
MARKERS = ("o", "s", "^", "D", "v", "P", "X", "*")
LINESTYLES = ("-", "--", "-.", ":", (0, (5, 1)), (0, (3, 1, 1, 1)), (0, (1, 1)), (0, (5, 5)))
ARROW = {"maximize": "↑ higher is better", "minimize": "↓ lower is better"}


def _pyplot() -> Any:
    import matplotlib

    matplotlib.use("Agg")
    # SVG element ids are random unless salted; a fixed salt makes SVGs byte-stable (tested).
    matplotlib.rcParams["svg.hashsalt"] = "evooptlab"
    import matplotlib.pyplot as plt

    return plt


def style(index: int) -> dict[str, Any]:
    i = index % len(OKABE_ITO)
    return {"color": OKABE_ITO[i], "marker": MARKERS[i], "linestyle": LINESTYLES[i]}


def _save(
    fig: Any, out: Path, name: str, formats: Sequence[str], rows: list[dict[str, Any]]
) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for fmt in formats:
        path = out / f"{name}.{fmt}"
        # Fixed metadata keeps vector outputs byte-stable across runs.
        metadata = {"svg": {"Date": None}, "pdf": {"CreationDate": None}}.get(fmt)
        with path.open("xb") as handle:
            fig.savefig(handle, format=fmt, bbox_inches="tight", metadata=metadata)
        paths.append(path)
    buffer = io.StringIO()
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    data = out / f"{name}.csv"
    with data.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(buffer.getvalue())
    paths.append(data)
    _pyplot().close(fig)
    return paths


def distribution_figure(
    values: dict[str, dict[str, list[float]]],
    *,
    metric: str,
    direction: str,
    title: str,
    out: Path,
    name: str,
    formats: Sequence[str],
) -> list[Path]:
    """Per-problem box plots across replicates, with every replicate drawn as a point."""
    plt = _pyplot()
    problems = list(values)
    algorithms = list(dict.fromkeys(a for p in problems for a in values[p]))
    fig, axes = plt.subplots(1, len(problems), figsize=(3.2 * len(problems), 3.4), squeeze=False)
    rows: list[dict[str, Any]] = []
    for ax, problem in zip(axes[0], problems, strict=True):
        for j, algorithm in enumerate(algorithms):
            vs = values[problem].get(algorithm, [])
            s = style(j)
            if vs:
                ax.boxplot(
                    [vs],
                    positions=[j],
                    widths=0.6,
                    showfliers=False,
                    medianprops={"color": "black"},
                )
                ax.plot(
                    [j] * len(vs),
                    vs,
                    linestyle="none",
                    marker=s["marker"],
                    color=s["color"],
                    markersize=4,
                    alpha=0.8,
                )
            rows += [{"problem": problem, "algorithm": algorithm, "value": v} for v in vs]
        ax.set_xticks(range(len(algorithms)))
        ax.set_xticklabels(algorithms, rotation=45, ha="right", fontsize=8)
        ax.set_title(problem, fontsize=9)
    axes[0][0].set_ylabel(f"{metric} ({ARROW[direction]})")
    fig.suptitle(title, fontsize=10, y=1.03)
    return _save(fig, out, name, formats, rows)


def curve_figure(
    curves: dict[str, dict[str, list[tuple[int, float | None]]]],
    *,
    ylabel: str,
    title: str,
    out: Path,
    name: str,
    formats: Sequence[str],
    log_y: bool = False,
) -> list[Path]:
    """Median curve with an interquartile band per algorithm, one panel per problem.

    ``curves[problem][algorithm]`` holds ``(evaluations, value)`` points of all replicates;
    points without a value (no feasible evaluation yet) are excluded from that checkpoint.
    """
    import numpy as np

    plt = _pyplot()
    problems = list(curves)
    algorithms = list(dict.fromkeys(a for p in problems for a in curves[p]))
    fig, axes = plt.subplots(1, len(problems), figsize=(3.4 * len(problems), 3.2), squeeze=False)
    rows: list[dict[str, Any]] = []
    for ax, problem in zip(axes[0], problems, strict=True):
        for j, algorithm in enumerate(algorithms):
            by_t: dict[int, list[float]] = {}
            for t, v in curves[problem].get(algorithm, []):
                if v is not None:
                    by_t.setdefault(t, []).append(v)
            if not by_t:
                continue
            ts = sorted(by_t)
            q1, med, q3 = (np.array([np.percentile(by_t[t], q) for t in ts]) for q in (25, 50, 75))
            s = style(j)
            ax.plot(
                ts,
                med,
                label=algorithm,
                color=s["color"],
                linestyle=s["linestyle"],
                marker=s["marker"],
                markevery=max(1, len(ts) // 5),
                markersize=4,
            )
            ax.fill_between(ts, q1, q3, color=s["color"], alpha=0.15, linewidth=0)
            rows += [
                {
                    "problem": problem,
                    "algorithm": algorithm,
                    "evaluations": t,
                    "n": len(by_t[t]),
                    "q1": float(a),
                    "median": float(b),
                    "q3": float(c),
                }
                for t, a, b, c in zip(ts, q1, med, q3, strict=True)
            ]
        ax.set_title(problem, fontsize=9)
        ax.set_xlabel("objective evaluations")
        if log_y:
            ax.set_yscale("log")
    axes[0][0].set_ylabel(ylabel)
    axes[0][-1].legend(fontsize=7, loc="best")
    fig.suptitle(title, fontsize=10, y=1.03)
    return _save(fig, out, name, formats, rows)
