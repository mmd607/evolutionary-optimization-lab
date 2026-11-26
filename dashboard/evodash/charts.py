"""Plotly figures for the dashboard. Pure functions of explorer data; no Streamlit calls.

Okabe-Ito colours with a distinct marker and dash per algorithm (the same conventions as the
generated report figures). Every axis states the metric and its direction, and the titles of
preliminary data say PRELIMINARY.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import plotly.graph_objects as go

from evooptlab.explorer.transforms import CurveBand, FrontData
from evooptlab.reporting.figures import ARROW, OKABE_ITO

SYMBOLS = ("circle", "square", "triangle-up", "diamond", "triangle-down", "cross", "x", "star")
DASHES = ("solid", "dash", "dashdot", "dot", "longdash", "longdashdot", "solid", "dash")
GREY = "#999999"


def style(index: int) -> dict[str, str]:
    i = index % len(OKABE_ITO)
    return {"color": OKABE_ITO[i], "symbol": SYMBOLS[i], "dash": DASHES[i]}


def title(text: str, preliminary: bool) -> str:
    return f"{text} — PRELIMINARY" if preliminary else text


def _rgba(hex_colour: str, alpha: float) -> str:
    r, g, b = (int(hex_colour[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def front_figure(data: FrontData, heading: str) -> go.Figure:
    """Objective space of one run: dominated, non-dominated and infeasible evaluations, plus
    the reference front. Three objectives are drawn in 3-D; more than three show f_0 vs f_1."""
    m = data.objectives.shape[1]
    fig = go.Figure()
    groups = (
        ("feasible, dominated", data.feasible & ~data.nondominated, GREY, "circle", 4),
        ("non-dominated (approximation set)", data.nondominated, OKABE_ITO[4], "diamond", 7),
        ("infeasible", ~data.feasible, OKABE_ITO[3], "x", 5),
    )
    ref = data.reference_front
    if m == 3:
        for name, mask, colour, symbol, size in groups:
            if mask.any():
                pts = data.objectives[mask]
                fig.add_trace(
                    go.Scatter3d(
                        x=pts[:, 0],
                        y=pts[:, 1],
                        z=pts[:, 2],
                        mode="markers",
                        name=name,
                        marker={"color": colour, "symbol": symbol, "size": size / 2},
                        customdata=data.evaluation_ids[mask],
                        hovertemplate="evaluation %{customdata}<extra></extra>",
                    )
                )
        if ref is not None:
            fig.add_trace(
                go.Scatter3d(
                    x=ref[:, 0],
                    y=ref[:, 1],
                    z=ref[:, 2],
                    mode="markers",
                    name="reference front",
                    marker={"color": "black", "size": 1.5},
                )
            )
        fig.update_layout(
            scene={"xaxis_title": "f_0 (↓)", "yaxis_title": "f_1 (↓)", "zaxis_title": "f_2 (↓)"}
        )
    else:
        for name, mask, colour, symbol, size in groups:
            if mask.any():
                pts = data.objectives[mask]
                fig.add_trace(
                    go.Scattergl(
                        x=pts[:, 0],
                        y=pts[:, 1],
                        mode="markers",
                        name=name,
                        marker={"color": colour, "symbol": symbol, "size": size},
                        customdata=data.evaluation_ids[mask],
                        hovertemplate="evaluation %{customdata}<br>f_0=%{x}<br>f_1=%{y}"
                        "<extra></extra>",
                    )
                )
        if ref is not None:
            order = ref[:, 0].argsort()
            fig.add_trace(
                go.Scatter(
                    x=ref[order, 0],
                    y=ref[order, 1],
                    mode="markers",
                    name="reference front",
                    marker={"color": "black", "size": 3},
                )
            )
        suffix = f" (first two of {m} objectives)" if m > 3 else ""
        fig.update_layout(xaxis_title="f_0 (↓)" + suffix, yaxis_title="f_1 (↓)")
    fig.update_layout(title=heading, legend={"orientation": "h", "y": -0.2})
    return fig


def curve_figure(bands: Sequence[CurveBand], ylabel: str, heading: str, log_y: bool) -> go.Figure:
    """Median curve per algorithm with its interquartile band over replicates."""
    fig = go.Figure()
    for i, band in enumerate(bands):
        s = style(i)
        pts = [
            (x, m, lo, hi)
            for x, m, lo, hi in zip(band.evaluations, band.median, band.q1, band.q3, strict=True)
            if m is not None and lo is not None and hi is not None
        ]
        if not pts:
            continue
        xs, med, low, high = (list(v) for v in zip(*pts, strict=True))
        fig.add_trace(
            go.Scatter(
                x=xs + xs[::-1],
                y=high + low[::-1],
                fill="toself",
                fillcolor=_rgba(s["color"], 0.18),
                line={"width": 0},
                hoverinfo="skip",
                showlegend=False,
                legendgroup=band.algorithm,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=med,
                mode="lines+markers",
                name=f"{band.algorithm} (n={len(band.run_ids)})",
                legendgroup=band.algorithm,
                line={"color": s["color"], "dash": s["dash"]},
                marker={"symbol": s["symbol"], "size": 6},
            )
        )
    fig.update_layout(
        title=heading,
        xaxis_title="objective evaluations",
        yaxis_title=ylabel,
        yaxis_type="log" if log_y else "linear",
    )
    return fig


def distribution_figure(
    values: Mapping[str, Sequence[float]], metric: str, direction: str, heading: str
) -> go.Figure:
    """Box plot per algorithm with every replicate drawn as a point."""
    fig = go.Figure()
    for i, (algorithm, ys) in enumerate(values.items()):
        s = style(i)
        fig.add_trace(
            go.Box(
                y=list(ys),
                name=f"{algorithm} (n={len(ys)})",
                boxpoints="all",
                jitter=0.3,
                pointpos=0,
                marker={"color": s["color"], "symbol": s["symbol"]},
                line={"color": "black", "width": 1},
                fillcolor=_rgba(s["color"], 0.25),
            )
        )
    fig.update_layout(
        title=heading,
        yaxis_title=f"{metric} ({ARROW.get(direction, direction)})",
        showlegend=False,
    )
    return fig


def trials_figure(rows: Sequence[Mapping[str, Any]], heading: str) -> go.Figure:
    """Validation error of every HPO trial, the best so far, and the selected trial."""
    ok = [r for r in rows if r["validation_error"] is not None]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=[r["evaluation_id"] for r in ok],
            y=[r["validation_error"] for r in ok],
            mode="markers",
            name="trial",
            marker={"color": GREY, "size": 7},
        )
    )
    best = [r for r in rows if r["best_so_far"] is not None]
    fig.add_trace(
        go.Scatter(
            x=[r["evaluation_id"] for r in best],
            y=[r["best_so_far"] for r in best],
            mode="lines",
            name="best so far",
            line={"color": OKABE_ITO[4], "shape": "hv"},
        )
    )
    failed = [r["evaluation_id"] for r in rows if not r["feasible"]]
    if failed:
        fig.add_trace(
            go.Scatter(
                x=failed,
                y=[max((r["validation_error"] for r in ok), default=1.0)] * len(failed),
                mode="markers",
                name="failed trial",
                marker={"color": OKABE_ITO[3], "symbol": "x", "size": 9},
            )
        )
    chosen = [r for r in rows if r["selected"]]
    if chosen:
        fig.add_trace(
            go.Scatter(
                x=[chosen[0]["evaluation_id"]],
                y=[chosen[0]["validation_error"]],
                mode="markers",
                name="selected (lowest validation error)",
                marker={"color": OKABE_ITO[0], "symbol": "star", "size": 14},
            )
        )
    fig.update_layout(
        title=heading, xaxis_title="trial (evaluation id)", yaxis_title="validation error (↓)"
    )
    return fig


def quality_cost_figure(rows: Sequence[Mapping[str, Any]], metric: str, heading: str) -> go.Figure:
    """Per-run quality (``metric``) against the run's wall-clock time, one series per
    algorithm. Rows without both values are left out (and counted by the caller)."""
    fig = go.Figure()
    algorithms = list(dict.fromkeys(str(r["algorithm"]) for r in rows))
    for i, algorithm in enumerate(algorithms):
        pts = [
            r
            for r in rows
            if r["algorithm"] == algorithm
            and r.get(metric) is not None
            and r.get("wall_clock_seconds") is not None
        ]
        if not pts:
            continue
        s = style(i)
        fig.add_trace(
            go.Scatter(
                x=[r["wall_clock_seconds"] for r in pts],
                y=[r[metric] for r in pts],
                mode="markers",
                name=algorithm,
                marker={"color": s["color"], "symbol": s["symbol"], "size": 10},
                customdata=[r["seed"] for r in pts],
                hovertemplate="seed %{customdata}<br>%{x:.1f} s<br>%{y}<extra></extra>",
            )
        )
    fig.update_layout(
        title=heading,
        xaxis_title="run wall-clock time, s (↓)",
        yaxis_title=f"{metric.replace('_', ' ')} (↓)",
    )
    return fig
