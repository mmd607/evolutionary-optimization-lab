"""Read-only access to stored artifacts for the dashboard (ADR 0008).

This package loads and transforms what the runner, ``aggregate`` and ``report`` already wrote.
It never writes, never runs an optimization, and imports no UI library, so it can be tested
without Streamlit or Plotly. The Streamlit app in ``dashboard/`` is a thin view over it.
"""

from __future__ import annotations

from evooptlab.explorer.catalog import (
    AggregateEntry,
    Catalog,
    ReportEntry,
    RunEntry,
    scan_artifacts,
)

__all__ = ["AggregateEntry", "Catalog", "ReportEntry", "RunEntry", "scan_artifacts"]
