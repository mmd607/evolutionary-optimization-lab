"""Result tables generated from an :class:`~evooptlab.analysis.compare.AnalysisResult`.

Follows docs/tables_and_figures.md:
- every metric header states its direction (↑ higher is better, ↓ lower is better);
- every row shows ``n``, and failed runs are counted in their own column;
- decimals are consistent within a column;
- a missing value is an em dash with a note, never zero;
- nothing is bolded, because "best" is a claim that needs the test results next to it.

Preliminary analyses carry PRELIMINARY in every table title.
Machine-readable CSVs keep full precision; only these display tables round.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from evooptlab.analysis.compare import AnalysisResult
from evooptlab.config.schemas import ReportingConfig

DASH = "—"
ARROW = {"maximize": "↑", "minimize": "↓"}
MISSING_NOTE = (
    f"{DASH}: no value (no completed run with this metric, or the statistic needs n ≥ 2)."
)


def _fmt(value: Any, decimals: int) -> str:
    if value is None:
        return DASH
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return f"{float(value):.{decimals}f}"


def _p(value: float | None) -> str:
    if value is None:
        return DASH
    return "< 0.0001" if value < 1e-4 else f"{value:.4f}"


def _decimals(config: ReportingConfig, metric: str) -> int:
    return config.decimals.get(metric, config.default_decimals)


def _title(result: AnalysisResult, text: str) -> str:
    label = " — PRELIMINARY (not a final result)" if result.preliminary else ""
    return f"{text} ({result.study}, {result.stage} stage){label}"


def descriptive_rows(
    result: AnalysisResult, metric: str, config: ReportingConfig
) -> list[list[str]]:
    d = _decimals(config, metric)
    rows = []
    for r in result.descriptive:
        if r["metric"] != metric:
            continue
        ci = DASH if r["ci_low"] is None else f"[{_fmt(r['ci_low'], d)}, {_fmt(r['ci_high'], d)}]"
        rows.append(
            [
                r["problem"],
                r["algorithm"],
                f"{_fmt(r['median'], d)} [{_fmt(r['q1'], d)}, {_fmt(r['q3'], d)}]"
                if r["median"] is not None
                else DASH,
                f"{_fmt(r['mean'], d)} ± {_fmt(r['std'], d)}" if r["mean"] is not None else DASH,
                ci,
                f"{r['n']}/{r['n_runs']}",
                str(r["n_failed"]),
            ]
        )
    return rows


def descriptive_table(
    result: AnalysisResult, metric: str, direction: str, config: ReportingConfig
) -> tuple[str, list[str], list[list[str]], list[str]]:
    ci = result.plan
    header = [
        "Problem",
        "Algorithm",
        f"{metric} {ARROW[direction]} median [Q1, Q3]",
        "mean ± SD",
        "bootstrap CI of the median",
        "n / runs",
        "failed runs",
    ]
    notes = [
        MISSING_NOTE,
        "n counts completed runs with a value; failed runs are counted but not scored.",
        f"Analysis plan {ci['name']} ({ci['status']}).",
    ]
    return (
        _title(result, f"Descriptive statistics of {metric}"),
        header,
        descriptive_rows(result, metric, config),
        notes,
    )


def pairwise_table(
    result: AnalysisResult, metric: str
) -> tuple[str, list[str], list[list[str]], list[str]]:
    header = ["Problem", "A", "B", "n pairs", "A12 (A better)", "W", "p", "p (Holm)", "note"]
    rows = [
        [
            r["problem"],
            r["algorithm_a"],
            r["algorithm_b"],
            str(r["n_pairs"]),
            _fmt(r["a12"], 3),
            _fmt(r["statistic"], 1),
            _p(r["p_value"]),
            _p(r["p_holm"]),
            r["note"] or "",
        ]
        for r in result.pairwise
        if r["metric"] == metric
    ]
    notes = [
        "Two-sided Wilcoxon signed-rank tests on replicates paired by seed; Holm-adjusted.",
        "A12 = P(A better than B) + 0.5 P(tie), following the metric's direction; 0.5 = no "
        "difference.",
        MISSING_NOTE,
    ]
    return _title(result, f"Pairwise comparisons of {metric}"), header, rows, notes


def to_markdown(
    title: str, header: Sequence[str], rows: Sequence[Sequence[str]], notes: Sequence[str]
) -> str:
    lines = [f"**{title}**", "", "| " + " | ".join(header) + " |"]
    lines.append("|" + "|".join("---" for _ in header) + "|")
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    if not rows:
        lines.append("| " + " | ".join([DASH] * len(header)) + " |")
    lines += ["", *[f"*Note.* {n}" for n in notes], ""]
    return "\n".join(lines)


_LATEX_ESCAPE = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "—": "---",
    "±": r"$\pm$",
    "↑": r"$\uparrow$",
    "↓": r"$\downarrow$",
    "≥": r"$\geq$",
    "<": r"$<$",
}


def latex_escape(text: str) -> str:
    return "".join(_LATEX_ESCAPE.get(ch, ch) for ch in text)


def to_latex(
    title: str, header: Sequence[str], rows: Sequence[Sequence[str]], notes: Sequence[str]
) -> str:
    spec = "l" * 3 + "r" * (len(header) - 3)
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        rf"\caption{{{latex_escape(title)}}}",
        rf"\begin{{tabular}}{{{spec}}}",
        r"\hline",
        " & ".join(latex_escape(h) for h in header) + r" \\",
        r"\hline",
    ]
    lines += [" & ".join(latex_escape(c) for c in row) + r" \\" for row in rows]
    lines += [r"\hline", r"\end{tabular}"]
    lines += [rf"\par\footnotesize {latex_escape(n)}" for n in notes]
    lines += [r"\end{table}", ""]
    return "\n".join(lines)
