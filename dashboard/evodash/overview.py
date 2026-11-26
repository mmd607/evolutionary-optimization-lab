"""Overview: what is stored, at which stage, from which source tree."""

from __future__ import annotations

import streamlit as st

from evodash import common
from evooptlab.explorer.catalog import Catalog


def render() -> None:
    st.title("EvoOptLab — experiment overview")
    st.markdown(
        "Read-only view of the artifacts stored by the EvoOptLab runner. Evolutionary, swarm, "
        "model-based and random-search methods are compared under equal objective-evaluation "
        "budgets on multi-objective benchmarks and tabular HPO tasks. Every number on these "
        "pages is read from stored run artifacts, aggregates or generated analysis reports."
    )
    cat = common.catalog()
    st.caption(f"Artifact root: `{cat.root}`")
    if cat.is_empty:
        common.empty(
            "Run a study first, for example `evooptlab run configs/studies/smoke.yaml "
            "--root build/smoke`, then point the dashboard at that root."
        )
        _anomalies(cat)
        return

    columns = st.columns(4)
    columns[0].metric("Runs", len(cat.runs))
    columns[1].metric("Studies", len({(r.stage, r.study) for r in cat.runs}))
    columns[2].metric("Algorithms", len({r.algorithm for r in cat.runs}))
    columns[3].metric("Problems", len({r.problem for r in cat.runs}))
    if "final" not in cat.stages():
        st.warning(
            "No final-stage runs are stored under this root. Everything shown is PRELIMINARY "
            "(pilot or development)."
        )

    st.subheader("Studies by stage")
    common.table(cat.overview())
    st.subheader("Algorithms and problems")
    common.table(
        [
            {
                "stage": stage,
                "kind": kind,
                "algorithms": ", ".join(sorted({r.algorithm for r in runs})),
                "problems": ", ".join(sorted({r.problem for r in runs})),
            }
            for stage in cat.stages()
            for kind in ("benchmark", "hpo")
            if (runs := cat.select(stage=stage, kind=kind))
        ]
    )

    latest = cat.latest_run()
    if latest is not None:
        st.subheader("Latest run")
        st.write(
            f"`{latest.run_id}` ({latest.stage}): **{latest.outcome}**, started "
            f"{latest.started_at_utc.isoformat()}"
            + (f", failure: {latest.failure_reason}" if latest.failure_reason else "")
        )

    st.subheader("Reproducibility metadata")
    st.caption("Distinct source trees and environments the stored runs were produced with.")
    common.table(cat.environments())

    st.subheader("Aggregates")
    common.table(
        [
            {
                "stage": a.stage,
                "study": a.study,
                "kind": a.kind,
                "label": "PRELIMINARY" if a.preliminary else "final",
                "diagnostics": a.diagnostics_status,
                "runs": len(a.run_ids),
                "created_at_utc": a.created_at_utc.isoformat() if a.created_at_utc else None,
                "stale": "; ".join(a.stale_reasons) or "no",
                "name": a.name,
            }
            for a in cat.aggregates
        ],
        hint="Write one with `evooptlab aggregate STUDY --root ROOT`.",
    )
    st.subheader("Analysis reports")
    common.table(
        [
            {
                "stage": r.stage,
                "study": r.study,
                "label": "PRELIMINARY" if r.preliminary else "final",
                "plan": f"{r.plan_name} ({r.plan_status})",
                "stale": "; ".join(r.stale_reasons) or "no",
                "name": r.name,
            }
            for r in cat.reports
        ],
        hint="Generate one with `evooptlab report AGGREGATE_DIR` (written under ROOT/reports).",
    )
    _anomalies(cat)


def _anomalies(cat: Catalog) -> None:
    if cat.anomalies:
        with st.expander(f"Unreadable entries ({len(cat.anomalies)}), never modified"):
            common.table([{"path": p, "reason": r} for p, r in cat.anomalies])
