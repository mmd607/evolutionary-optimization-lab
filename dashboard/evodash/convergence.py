"""Convergence Analysis: median and interquartile curves over replicates, one budget at a time.

Curves are computed from the stored histories only when **Compute curves** is pressed (it can
take seconds for long runs), and then cached per selection.
"""

from __future__ import annotations

import streamlit as st

from evodash import charts, common
from evooptlab.explorer import transforms


@st.cache_resource(show_spinner="Computing curves from stored histories...", max_entries=32)
def _bands(
    root: str, generation: int, stage: str, run_ids: tuple[str, ...], n_checkpoints: int
) -> list[transforms.CurveBand]:
    cat = common.cached_catalog(root, generation)
    runs = [r for rid in run_ids if (r := cat.run(stage, rid)) is not None]
    return transforms.convergence_bands(runs, n_checkpoints)


def render() -> None:
    st.title("Convergence Analysis")
    cat = common.catalog()
    stage = common.choose_stage(cat, "conv_stage")
    runs = cat.select(stage=stage) if stage else []
    if not runs:
        common.empty()
        return
    study = common.pick("Study", sorted({r.study for r in runs}), "conv_study")
    runs = [r for r in runs if r.study == study]
    problem = common.pick("Problem", sorted({r.problem for r in runs}), "conv_problem")
    runs = [r for r in runs if r.problem == problem]
    budgets = sorted({r.budget for r in runs})
    if len(budgets) > 1:
        st.warning(
            f"Runs of {problem} use different budgets {budgets}. Curves under different budgets "
            "are not comparable, so only one budget can be overlaid."
        )
    budget = common.pick("Evaluation budget", budgets, "conv_budget")
    runs = [r for r in runs if r.budget == budget]
    algorithms = sorted({r.algorithm for r in runs})
    selected = st.multiselect("Algorithms", algorithms, default=algorithms, key="conv_algs")
    runs = [r for r in runs if r.algorithm in selected]
    n_checkpoints = int(
        st.slider("Checkpoints", min_value=5, max_value=50, value=20, key="conv_points")
    )
    common.warnings(transforms.comparability(runs).warnings)
    if not runs:
        common.empty()
        return
    if not st.button("Compute curves", type="primary", key="conv_compute"):
        st.caption(f"{len(runs)} runs selected. Curves are computed only on request.")
        return
    try:
        bands = _bands(*common.snapshot(), str(stage), tuple(r.run_id for r in runs), n_checkpoints)
    except transforms.IncomparableRunsError as exc:
        st.error(str(exc))
        return
    if not bands:
        common.empty("No completed run in this selection.")
        return
    hpo = runs[0].kind == "hpo"
    st.plotly_chart(
        charts.curve_figure(
            bands,
            ylabel="best validation error so far (↓)" if hpo else "IGD+ (↓, normalized)",
            heading=charts.title(f"{problem}: median and IQR over replicates", stage != "final"),
            log_y=not hpo,
        ),
        width="stretch",
    )
    common.table(
        [
            {
                "algorithm": b.algorithm,
                "runs": len(b.run_ids),
                "evaluations": b.evaluations[-1],
                "median at end": b.median[-1],
                "q1": b.q1[-1],
                "q3": b.q3[-1],
                "runs with a value": b.n[-1],
            }
            for b in bands
        ]
    )
