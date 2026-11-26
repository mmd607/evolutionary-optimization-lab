"""Statistical Comparison: the tables of a generated analysis report (``evooptlab report``).

The dashboard never runs a statistical test itself: tests come only from reports generated
under the declared analysis plan (ADR 0007), so their pre-registration guard applies.
"""

from __future__ import annotations

import streamlit as st

from evodash import charts, common
from evooptlab.explorer import transforms
from evooptlab.explorer.catalog import Catalog, ReportEntry


def render() -> None:
    st.title("Statistical Comparison")
    cat = common.catalog()
    if not cat.reports:
        common.empty(
            "No analysis report under this root. Generate one with `evooptlab report "
            "ROOT/aggregates/STAGE/NAME`; it is written to ROOT/reports."
        )
        _aggregates_only(cat)
        return
    reports = sorted(cat.reports, key=lambda r: (r.stage != "final", r.study, r.name))
    report = common.pick(
        "Analysis report",
        reports,
        "stats_report",
        format_func=lambda r: f"{r.study} · {r.stage} · {r.name}",
    )
    if report is None:
        return
    common.stage_banner(report.stage)
    st.caption(
        f"Plan `{report.plan_name}` (status {report.plan_status}); source aggregate "
        f"`{report.aggregate_name}`."
    )
    if report.plan_status != "frozen":
        st.warning("The analysis plan is not frozen: these tests are exploratory (P9).")
    if report.stale:
        st.warning("Stale report: " + "; ".join(report.stale_reasons))
    try:
        analysis = report.analysis()
    except (OSError, ValueError) as exc:
        st.error(f"analysis.json is unreadable: {exc}")
        return
    metrics = transforms.analysis_metrics(analysis)
    if not metrics:
        common.empty("The report has no metric.")
        return
    metric, direction = common.pick(
        "Metric", metrics, "stats_metric", format_func=lambda m: f"{m[0]} ({m[1]})"
    )
    for note in analysis.get("notes", []):
        st.caption(f"Note: {note}")

    st.subheader("Descriptive statistics")
    st.caption("n = complete values used; n_runs = runs in the cell; failed runs are counted.")
    descriptive = transforms.descriptive_rows(analysis, metric)
    common.table(descriptive)
    _distribution(cat, report, metric, direction)

    st.subheader("Per-problem pairwise tests")
    st.caption(f"Test: {transforms.PAIRWISE_TEST}. 'not run' notes give the reason.")
    common.table(transforms.pairwise_rows(analysis, metric))
    st.subheader("Across problems")
    common.table(transforms.across_rows(analysis, metric))


def _distribution(cat: Catalog, report: ReportEntry, metric: str, direction: str) -> None:
    aggregate = next((a for a in cat.aggregates if a.name == report.aggregate_name), None)
    if aggregate is None:
        st.caption("Distribution plot unavailable: the source aggregate is not under this root.")
        return
    rows, _ = transforms.aggregate_tables(aggregate)
    values, missing = transforms.metric_values(rows, metric)
    for problem, by_algorithm in values.items():
        st.plotly_chart(
            charts.distribution_figure(
                by_algorithm,
                metric,
                direction,
                charts.title(f"{problem}: {metric} across replicates", aggregate.preliminary),
            ),
            width="stretch",
            key=f"dist_{problem}_{metric}",
        )
    if missing:
        st.caption(f"{missing} run(s) without a {metric} value are not plotted.")


def _aggregates_only(cat: Catalog) -> None:
    if not cat.aggregates:
        return
    st.subheader("Descriptive summaries of stored aggregates (no tests)")
    entry = common.pick(
        "Aggregate",
        cat.aggregates,
        "stats_aggregate",
        format_func=lambda a: f"{a.study} · {a.name}",
    )
    if entry is None:
        return
    common.stage_banner(entry.stage)
    if entry.stale:
        st.warning("Stale aggregate: " + "; ".join(entry.stale_reasons))
    _, summary = transforms.aggregate_tables(entry)
    common.table(summary)
