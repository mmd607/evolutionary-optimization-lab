"""HPO Explorer: trial history, the validation-selected configuration, its stored held-out
test result (only if ``evooptlab test-eval`` was run), and quality against cost."""

from __future__ import annotations

import streamlit as st

from evodash import charts, common
from evooptlab.explorer import transforms


def render() -> None:
    st.title("HPO Explorer")
    cat = common.catalog()
    stage = common.choose_stage(cat, "hpo_stage")
    runs = cat.select(stage=stage, kind="hpo") if stage else []
    if not runs:
        common.empty("No HPO runs at this stage.")
        return
    left, right = st.columns(2)
    with left:
        study = common.pick("Study", sorted({r.study for r in runs}), "hpo_study")
        runs = [r for r in runs if r.study == study]
        problem = common.pick("Dataset / model", sorted({r.problem for r in runs}), "hpo_problem")
        runs = [r for r in runs if r.problem == problem]
    details = ((runs[0].record.config or {}).get("problem") or {}).get("details") or {}
    with right:
        st.markdown(
            f"**Task** `{details.get('task')}` ({details.get('task_type')}) · **model** "
            f"`{details.get('model')}` · **target** `{details.get('target_metric')}`"
        )
        algorithm = common.pick("Optimizer", sorted({r.algorithm for r in runs}), "hpo_alg")
        chosen = [r for r in runs if r.algorithm == algorithm]
        run = common.pick("Run (seed)", chosen, "hpo_run", format_func=common.run_label)
    if run is None:
        return

    rows = transforms.trial_rows(run)
    st.plotly_chart(
        charts.trials_figure(
            rows,
            charts.title(f"{run.problem} · {run.algorithm} · seed {run.seed}", run.preliminary),
        ),
        width="stretch",
    )
    with st.expander(f"Trial history ({len(rows)} trials)"):
        common.table(rows)

    st.subheader("Selected configuration and held-out test result")
    test = transforms.test_result(cat, run)
    selected = next((r for r in rows if r["selected"]), None)
    if selected is None:
        common.empty("No successful trial: nothing was selected.")
    else:
        st.write(
            f"Selected by lowest validation error: trial {selected['evaluation_id']}, "
            f"validation error {selected['validation_error']}."
        )
    if test is None:
        st.info(
            "Test result not shown: no held-out evaluation is stored for this run. It is "
            "computed once, by `evooptlab test-eval`, after the search."
        )
    elif test["status"] != "ok":
        st.error(f"Stored test evaluation not used: {test['status']} {test.get('reason', '')}")
    else:
        if run.preliminary:
            st.warning("PRELIMINARY test result (non-final stage).")
        st.json(test)

    st.subheader(f"Quality against cost: {problem}")
    st.caption(
        "One point per run: final quality against the run's wall-clock time. Per-trial fit time "
        "is not recorded (ADR 0006), and wall-clock time also reflects the configurations an "
        "optimizer proposes."
    )
    common.warnings(transforms.comparability(runs).warnings)
    summary = transforms.hpo_run_rows(cat, runs)
    metric = st.radio(
        "Quality", ["best_validation_error", "test_error"], horizontal=True, key="hpo_metric"
    )
    usable = [r for r in summary if r.get(metric) is not None]
    if usable:
        st.plotly_chart(
            charts.quality_cost_figure(
                summary, str(metric), charts.title("Quality vs cost", run.preliminary)
            ),
            width="stretch",
        )
    if len(usable) < len(summary):
        st.caption(f"{len(summary) - len(usable)} run(s) without a {metric} are not plotted.")
    common.table(summary)
