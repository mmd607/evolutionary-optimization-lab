"""Run Details: metadata, config, environment, metrics, log and file paths of one run."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
import yaml

from evodash import common
from evooptlab.explorer import transforms

#: Files above this size are listed with their path but not offered for download.
DOWNLOAD_LIMIT_BYTES = 5_000_000


def render() -> None:
    st.title("Run Details")
    cat = common.catalog()
    stage = common.choose_stage(cat, "details_stage")
    runs = cat.select(stage=stage) if stage else []
    if not runs:
        common.empty()
        return
    study = common.pick("Study", sorted({r.study for r in runs}), "details_study")
    runs = [r for r in runs if r.study == study]
    run = common.pick("Run", runs, "details_run", format_func=lambda r: f"{r.run_id} ({r.outcome})")
    if run is None:
        return
    m = run.record.metadata
    columns = st.columns(4)
    columns[0].metric("Outcome", run.outcome)
    columns[1].metric("Seed", run.seed)
    columns[2].metric("Budget", run.budget)
    columns[3].metric(
        "Wall clock (s)",
        "—" if run.wall_clock_seconds is None else f"{run.wall_clock_seconds:.1f}",
    )
    if run.failure_reason:
        st.error(f"Failure reason: {run.failure_reason}")
    st.markdown(
        f"- Commit `{m.git_commit}` (dirty: `{m.git_dirty}`)\n"
        f"- Config hash `{m.config_hash}`\n"
        f"- Started `{m.started_at_utc.isoformat()}`, finished "
        f"`{m.finished_at_utc.isoformat() if m.finished_at_utc else None}`\n"
        f"- Directory `{run.path}`"
    )
    tabs = st.tabs(["Metadata", "Config", "Metrics", "Test evaluation", "Log", "Files"])
    with tabs[0]:
        st.json(m.model_dump(mode="json"))
    with tabs[1]:
        if run.record.config is None:
            common.empty("config.yaml is missing.")
        else:
            st.code(yaml.safe_dump(run.record.config, sort_keys=False), language="yaml")
    with tabs[2]:
        if run.record.metrics is None:
            common.empty("metrics.json is missing (the run did not finish).")
        else:
            st.json(run.record.metrics)
    with tabs[3]:
        test = transforms.test_result(cat, run) if run.kind == "hpo" else None
        if test is None:
            common.empty(
                "No stored held-out evaluation (HPO runs only, via `evooptlab test-eval`)."
            )
        else:
            st.json(test)
    with tabs[4]:
        common.table(transforms.run_log(run), hint="No log records.")
    with tabs[5]:
        files = transforms.run_files(run)
        common.table(files)
        for i, f in enumerate(files):
            if f["bytes"] <= DOWNLOAD_LIMIT_BYTES:
                st.download_button(
                    f"Download {f['file']}",
                    data=Path(f["path"]).read_bytes(),
                    file_name=f["file"].replace("/", "_"),
                    key=f"download_{i}",
                    on_click="ignore",
                )
