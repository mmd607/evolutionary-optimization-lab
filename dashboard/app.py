"""EvoOptLab dashboard: a read-only view of stored experiment artifacts (ADR 0008).

Launch from the repository root::

    python -m streamlit run dashboard/app.py -- --root artifacts/experiments

The root can also be set with ``EVOOPTLAB_ARTIFACT_ROOT`` or in the sidebar. The dashboard
only reads files. It never runs an optimization, an aggregation, a test evaluation or a
statistical test; those stay explicit CLI commands.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evodash import common

#: (file under views/, title, url path); file-based pages can be driven by AppTest.
PAGES: tuple[tuple[str, str, str], ...] = (
    ("page_overview.py", "Overview", "overview"),
    ("page_benchmarks.py", "Benchmark Explorer", "benchmarks"),
    ("page_convergence.py", "Convergence Analysis", "convergence"),
    ("page_hpo.py", "HPO Explorer", "hpo"),
    ("page_statistics.py", "Statistical Comparison", "statistics"),
    ("page_runs.py", "Run Details", "runs"),
)


def main() -> None:
    st.set_page_config(page_title="EvoOptLab dashboard", layout="wide")
    common.sidebar()
    views = Path(__file__).resolve().parent / "views"
    pages = [
        st.Page(views / file, title=title, url_path=url, default=i == 0)
        for i, (file, title, url) in enumerate(PAGES)
    ]
    st.navigation(pages).run()


main()
