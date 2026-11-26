"""Shared view helpers: artifact root, cached catalog, stage selection and honest empty states.

The catalog is a cached snapshot of the artifact root. The page always shows when it was
loaded, and **Reload artifacts** rescans the root. Loading only reads files.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import streamlit as st

from evooptlab.explorer.catalog import Catalog, RunEntry, scan_artifacts

ROOT_ENV = "EVOOPTLAB_ARTIFACT_ROOT"
DEFAULT_ROOT = "artifacts"
NO_RESULTS = "No results available."


def default_root(argv: Sequence[str] | None = None) -> str:
    """``--root`` after ``streamlit run dashboard/app.py --``, else the environment, else
    ``artifacts``."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--root", default=None)
    args, _ = parser.parse_known_args(list(sys.argv[1:] if argv is None else argv))
    return str(args.root or os.environ.get(ROOT_ENV) or DEFAULT_ROOT)


@st.cache_resource(show_spinner="Scanning artifacts (read-only)...", max_entries=8)
def cached_catalog(root: str, generation: int) -> Catalog:
    del generation  # part of the cache key only
    return scan_artifacts(Path(root))


def snapshot() -> tuple[str, int]:
    """``(root, generation)``: the cache key of the current artifact snapshot."""
    state = st.session_state
    return str(state.get("root", default_root())), int(state.get("generation", 0))


def catalog() -> Catalog:
    """The catalog of the root chosen in the sidebar (cached; see :func:`sidebar`)."""
    return cached_catalog(*snapshot())


def sidebar() -> None:
    state = st.session_state
    if "root" not in state:
        state["root"] = default_root()
    st.sidebar.text_input(
        "Artifact root", key="root", help="Directory that holds pilot/, development/, final/"
    )
    if st.sidebar.button("Reload artifacts", help="Rescan the root; nothing is written"):
        state["generation"] = int(state.get("generation", 0)) + 1
    loaded = catalog().loaded_at_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    st.sidebar.caption(f"Cached snapshot loaded {loaded}. Read-only: nothing is run or written.")


def choose_stage(cat: Catalog, key: str) -> str | None:
    """Stage selector (final first when present) and the PRELIMINARY banner."""
    stages = cat.stages()
    if not stages:
        return None
    ordered = sorted(stages, key=lambda s: s != "final")
    stage = st.selectbox("Stage", ordered, key=key)
    stage_banner(str(stage))
    return str(stage)


def stage_banner(stage: str) -> None:
    if stage == "final":
        st.success("Final stage.")
    else:
        st.warning(
            f"PRELIMINARY: {stage} stage. These runs are not final results and are not "
            "evidence for any claim."
        )


def empty(hint: str = "") -> None:
    st.info(f"{NO_RESULTS} {hint}".strip())


def table(rows: Sequence[dict[str, Any]], hint: str = "", **kwargs: Any) -> None:
    """A table, or the honest empty state. Missing values stay empty, never zero."""
    if not rows:
        empty(hint)
        return
    st.dataframe(list(rows), hide_index=True, width="stretch", **kwargs)


def warnings(messages: Sequence[str]) -> None:
    for message in messages:
        st.warning(message)


def pick(label: str, options: Sequence[Any], key: str, **kwargs: Any) -> Any:
    """Selectbox that shows the empty state instead of an empty widget."""
    if not options:
        empty()
        return None
    return st.selectbox(label, list(options), key=key, **kwargs)


def run_label(run: RunEntry) -> str:
    return f"{run.problem} · {run.algorithm} · seed {run.seed} · {run.budget} evals · {run.outcome}"
