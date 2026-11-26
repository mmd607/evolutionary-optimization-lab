"""``evooptlab report``: regenerate every analysis asset of one aggregate (ADR 0007).

Output (a new directory; nothing is overwritten)::

    analysis.json            full analysis, plan identity, source run IDs, git state
    descriptive.csv          per (problem, algorithm, metric), full precision
    pairwise.csv             per-problem paired tests (Holm-adjusted), full precision
    across_problems.csv      Friedman / post-hoc results, full precision
    values.json              flat "key -> value" store that the manuscript references
    tables/*.md, *.tex       display tables (rounded)
    figures/*.svg|pdf + .csv figures and the exact data they plot
    README.md                inputs, plan status and the PRELIMINARY label

Every asset is a function of the aggregate, the stored histories, the analysis plan and the
reporting config, so it can be regenerated at any time.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

import numpy as np

from evooptlab.analysis.compare import AggregateInput, AnalysisError, AnalysisResult, analyse
from evooptlab.analysis.curves import best_so_far_curve, checkpoints, igd_plus_curve
from evooptlab.config.schemas import AnalysisPlanConfig, ReportingConfig
from evooptlab.reporting import tables
from evooptlab.reporting.figures import curve_figure, distribution_figure
from evooptlab.utils.environment import capture_environment


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    columns = list(dict.fromkeys(k for r in rows for k in r))
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in row.items()}
        )
    return buffer.getvalue()


def values_store(result: AnalysisResult, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Flat value store: ``study/problem/algorithm/metric/statistic -> value``."""
    tag = {"preliminary": result.preliminary, "stage": result.stage}
    store: dict[str, dict[str, Any]] = {}

    def put(key: str, value: Any, source: str) -> None:
        store[f"{result.study}/{key}"] = {"value": value, "source": source, **tag}

    for key, value in (manifest.get("matrix") or {}).items():
        put(f"matrix/{key}", value, "manifest.json")
    for r in result.descriptive:
        base = f"{r['problem']}/{r['algorithm']}/{r['metric']}"
        for stat in (
            "median",
            "q1",
            "q3",
            "mean",
            "std",
            "ci_low",
            "ci_high",
            "n",
            "n_runs",
            "n_failed",
        ):
            put(f"{base}/{stat}", r[stat], "descriptive.csv")
    for r in result.pairwise:
        base = f"{r['problem']}/{r['algorithm_a']}-vs-{r['algorithm_b']}/{r['metric']}"
        for stat in ("n_pairs", "a12", "statistic", "p_value", "p_holm"):
            put(f"{base}/{stat}", r[stat], "pairwise.csv")
    for r in result.across_problems:
        base = f"across/{r['metric']}"
        put(f"{base}/p_value", r["p_value"], "across_problems.csv")
        put(f"{base}/statistic", r["statistic"], "across_problems.csv")
        put(f"{base}/n_problems", len(r["problems_used"]), "across_problems.csv")
        for algorithm, rank in (r["mean_ranks"] or {}).items():
            put(f"{base}/mean_rank/{algorithm}", rank, "across_problems.csv")
    return store


def _runs_by_cell(data: AggregateInput) -> dict[str, dict[str, list[dict[str, str]]]]:
    out: dict[str, dict[str, list[dict[str, str]]]] = {}
    for row in data.runs:
        if row["outcome"] == "completed":
            out.setdefault(row["problem"], {}).setdefault(row["algorithm"], []).append(row)
    return out


def _history(root: Path, stage: str, run_id: str) -> list[dict[str, str]]:
    path = root / stage / run_id / "history.csv"
    try:
        return list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    except OSError as exc:
        raise AnalysisError(f"history of {run_id} not found under {root} ({exc})") from exc


def _reference_front(root: Path, stage: str, run_id: str) -> Any:
    import yaml

    from evooptlab.benchmarks.registry import get_problem

    config = yaml.safe_load((root / stage / run_id / "config.yaml").read_text(encoding="utf-8"))
    p = config["problem"]
    problem = get_problem(p["name"], p["n_variables"], p["n_objectives"])
    return problem.pareto_front()  # type: ignore[attr-defined]


def convergence_curves(
    data: AggregateInput, root: Path, n_checkpoints: int
) -> dict[str, dict[str, list[tuple[int, float | None]]]]:
    curves: dict[str, dict[str, list[tuple[int, float | None]]]] = {}
    fronts: dict[str, Any] = {}
    for problem, by_algorithm in _runs_by_cell(data).items():
        for algorithm, rows in by_algorithm.items():
            points: list[tuple[int, float | None]] = []
            for row in rows:
                history = _history(root, data.stage, row["run_id"])
                at = checkpoints(len(history), n_checkpoints)
                feasible = np.array([h["feasible"] == "True" for h in history])
                if data.kind == "hpo":
                    values = np.array([float(h["f_0"]) for h in history])
                    ys = best_so_far_curve(values, feasible, at)
                else:
                    m = sum(1 for k in history[0] if k.startswith("f_"))
                    f = np.array([[float(h[f"f_{j}"]) for j in range(m)] for h in history])
                    if problem not in fronts:
                        fronts[problem] = _reference_front(root, data.stage, row["run_id"])
                    ys = igd_plus_curve(f, feasible, fronts[problem], at)
                points += list(zip(at, ys, strict=True))
            curves.setdefault(problem, {})[algorithm] = points
    return curves


def write_report(
    data: AggregateInput,
    plan: AnalysisPlanConfig,
    reporting: ReportingConfig,
    output_dir: Path,
    *,
    plan_sha256: str,
    artifact_root: Path | None = None,
    repo_root: Path | None = None,
) -> Path:
    git = capture_environment(repo_root).git
    result = analyse(
        data, plan, plan_sha256=plan_sha256, git_commit=git.commit, git_dirty=git.dirty
    )
    root = artifact_root if artifact_root is not None else data.path.parents[2]
    curves = convergence_curves(data, root, reporting.convergence_checkpoints)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(exist_ok=False)
    _write(output_dir / "analysis.json", json.dumps(result.to_dict(), indent=2) + "\n")
    _write(output_dir / "descriptive.csv", _csv(result.descriptive))
    _write(output_dir / "pairwise.csv", _csv(result.pairwise))
    _write(output_dir / "across_problems.csv", _csv(result.across_problems))
    store = values_store(result, data.manifest)
    _write(output_dir / "values.json", json.dumps(store, indent=2, sort_keys=True) + "\n")

    metrics = plan.hpo_metrics if data.kind == "hpo" else plan.benchmark_metrics
    label = " — PRELIMINARY" if result.preliminary else ""
    for metric in metrics:
        for kind, table in (
            (
                "descriptive",
                tables.descriptive_table(result, metric.name, metric.direction, reporting),
            ),
            ("pairwise", tables.pairwise_table(result, metric.name)),
        ):
            _write(output_dir / "tables" / f"{metric.name}_{kind}.md", tables.to_markdown(*table))
            _write(output_dir / "tables" / f"{metric.name}_{kind}.tex", tables.to_latex(*table))
        values: dict[str, dict[str, list[float]]] = {}
        for row in data.runs:
            raw = row.get(metric.name, "")
            if row["outcome"] == "completed" and raw:
                values.setdefault(row["problem"], {}).setdefault(row["algorithm"], []).append(
                    float(raw)
                )
        distribution_figure(
            values,
            metric=metric.name,
            direction=metric.direction,
            title=f"{metric.name} across replicates ({data.study}){label}",
            out=output_dir / "figures",
            name=f"{metric.name}_distribution",
            formats=reporting.figure_formats,
        )
    curve_figure(
        curves,
        ylabel="best validation error so far (↓)" if data.kind == "hpo" else "IGD+ (↓, normalized)",
        title=f"Search progress, median and IQR over replicates ({data.study}){label}",
        out=output_dir / "figures",
        name="convergence",
        formats=reporting.figure_formats,
        log_y=data.kind != "hpo",
    )
    _write(output_dir / "README.md", _readme(result, data, plan))
    return output_dir


def _readme(result: AnalysisResult, data: AggregateInput, plan: AnalysisPlanConfig) -> str:
    lines = [
        f"# Analysis of `{data.study}` ({data.stage} stage)",
        "",
        "**PRELIMINARY — not a final result.**" if result.preliminary else "**Final analysis.**",
        "",
        f"- Aggregate: `{data.path}`",
        f"- Analysis plan: `{plan.name}` (status `{plan.status}`, sha256 "
        f"`{result.plan['sha256'][:12]}`)",
        f"- Runs: {len(data.runs)} (failed runs are counted, not scored)",
        f"- Source tree: commit `{result.source['analysis_git_commit']}`, dirty "
        f"`{result.source['analysis_git_dirty']}`",
        "",
        "Regenerate with `evooptlab report AGGREGATE_DIR --plan PLAN --reporting REPORTING`.",
        "",
    ]
    lines += [f"- Note: {n}" for n in result.notes]
    return "\n".join(lines) + "\n"
