"""Benchmark Explorer: objective space of one run, and the stored indicators of its problem."""

from __future__ import annotations

import streamlit as st

from evodash import charts, common
from evooptlab.explorer import transforms

COMPARE_COLUMNS = (
    "algorithm",
    "seed",
    "outcome",
    "hypervolume_ratio",
    "igd_plus",
    "igd",
    "feasibility_rate",
    "n_nondominated",
    "wall_clock_seconds",
    "missing_reason",
)


def render() -> None:
    st.title("Benchmark Explorer")
    cat = common.catalog()
    stage = common.choose_stage(cat, "bench_stage")
    runs = cat.select(stage=stage, kind="benchmark") if stage else []
    if not runs:
        common.empty("No benchmark runs at this stage.")
        return
    left, right = st.columns(2)
    with left:
        study = common.pick("Study", sorted({r.study for r in runs}), "bench_study")
        runs = [r for r in runs if r.study == study]
        problem = common.pick("Problem", sorted({r.problem for r in runs}), "bench_problem")
        runs = [r for r in runs if r.problem == problem]
    with right:
        budgets = sorted({r.budget for r in runs})
        budget = common.pick("Evaluation budget", budgets, "bench_budget")
        if len(budgets) > 1:
            st.warning("This problem has runs under several budgets; only one is shown at a time.")
        runs = [r for r in runs if r.budget == budget]
        algorithm = common.pick("Algorithm", sorted({r.algorithm for r in runs}), "bench_alg")
    chosen = [r for r in runs if r.algorithm == algorithm]
    run = common.pick("Run (seed)", chosen, "bench_run", format_func=common.run_label)
    if run is None:
        return

    aggregates = [
        a for a in cat.aggregates if a.stage == stage and a.study == study and a.kind == "benchmark"
    ]
    entry = max(aggregates, key=lambda a: a.created_at_utc or run.started_at_utc, default=None)
    stored = {r["run_id"]: r for r in transforms.aggregate_tables(entry)[0]} if entry else {}
    in_aggregate = run.run_id in stored

    data = _front(run.stage, run.run_id, with_quality=not in_aggregate)
    st.plotly_chart(
        charts.front_figure(
            data,
            charts.title(f"{run.problem} · {run.algorithm} · seed {run.seed}", run.preliminary),
        ),
        width="stretch",
    )
    st.caption(
        f"{int(data.feasible.sum())} feasible of {len(data.feasible)} evaluations; "
        f"{int(data.nondominated.sum())} non-dominated. Run `{run.run_id}`."
    )
    keys = ("hypervolume_ratio", "igd_plus", "igd", "gd_plus", "spacing", "feasibility_rate")
    if run.outcome != "completed":
        st.warning(f"Run {run.outcome}: not scored ({run.failure_reason}).")
    elif entry is not None and in_aggregate:
        st.markdown(f"**Quality of this run** (stored in aggregate `{entry.name}`)")
        common.table([{k: stored[run.run_id].get(k) or None for k in (*keys, "missing_reason")}])
    elif data.quality is not None:
        st.markdown(
            "**Quality of this run** (no aggregate holds it, so it is computed now from its "
            "history with the default quality policy of ADR 0003, still proposal P8)"
        )
        common.table([{k: data.quality.get(k) for k in (*keys, "missing_reason")}])

    st.subheader(f"All runs of {problem} at {budget} evaluations")
    common.warnings(transforms.comparability(runs).warnings)
    if entry is None:
        common.empty("No aggregate for this study yet: run `evooptlab aggregate` for indicators.")
        common.table([r.row() for r in runs])
        return
    st.caption(f"From aggregate `{entry.name}` (diagnostics {entry.diagnostics_status}).")
    if entry.stale:
        st.warning("Stale aggregate: " + "; ".join(entry.stale_reasons))
    budget_ids = {r.run_id for r in runs}
    common.table(
        [
            {c: row.get(c) or None for c in COMPARE_COLUMNS}
            for row in stored.values()
            if row["problem"] == problem and row["run_id"] in budget_ids
        ],
        hint="The aggregate holds no run of this selection.",
    )


@st.cache_resource(show_spinner="Reading the run's evaluations...", max_entries=64)
def _cached_front(
    root: str, generation: int, stage: str, run_id: str, with_quality: bool
) -> transforms.FrontData | None:
    run = common.cached_catalog(root, generation).run(stage, run_id)
    return None if run is None else transforms.run_front(run, with_quality=with_quality)


def _front(stage: str, run_id: str, *, with_quality: bool) -> transforms.FrontData:
    data = _cached_front(*common.snapshot(), stage, run_id, with_quality)
    assert data is not None  # the run was just selected from the same catalog
    return data
