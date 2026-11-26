# ADR 0008 — Read-only dashboard over stored artifacts

- **Status:** Accepted
- **Date:** 2026-11-26
- **Phase:** 07 — Dashboard
- **Code:** `src/evooptlab/explorer/` (data layer), `dashboard/` (Streamlit views),
  `.streamlit/config.toml`

## Context

Phase 07 asks for a Streamlit dashboard over existing artifacts (`docs/dashboard_spec.md`) with
six pages: Overview, Benchmark Explorer, Convergence Analysis, HPO Explorer, Statistical
Comparison and Run Details. The rules are:
- no fabricated metrics;
- pilot and final runs are clearly distinguished;
- incomparable budgets get a warning;
- no expensive jobs run on page load;
- empty states are shown honestly;
- the UI is kept separate from the core package.

No final-stage artifacts exist yet (final runs are blocked on P3, P4, P5, P8, P9 and P10). The
dashboard was therefore built and tested against the real pilot artifacts and against small
artifact roots that the real pipeline produces in the tests.

## Decisions

### D1. Two layers: a UI-free data layer in the package and thin views outside it

- **`evooptlab.explorer`** indexes and transforms artifacts. It imports no UI library (tested in a
  fresh interpreter) and is type-checked and covered like the rest of the package.
  - `catalog.scan_artifacts(root)` returns runs, aggregates, analysis reports and held-out test
    evaluations, keeping every entry's stage.
  - `transforms` computes objective-space data, convergence bands, HPO trial tables, test
    results, and the pass-through of report tables.
- **`dashboard/`** holds the Streamlit app.
  - `app.py` is the entry point.
  - `evodash/*.py` holds one view per page and the Plotly figure builders in `charts.py`.
  - `views/page_*.py` are file-based page entry points, which Streamlit's `AppTest` can drive.
- Streamlit and Plotly are an optional extra, `pip install -e ".[dashboard]"`, so running
  experiments does not need them. The pins are in `requirements/constraints-py312.txt`.

### D2. Read-only: it never writes and never starts a computation that changes results

- **Nothing is written.** The dashboard never runs an optimization, an aggregation, a test
  evaluation or a statistical test; those remain explicit CLI commands. A test hashes every file
  of the artifact root before and after all explorer functions and all pages, and checks that the
  two digests are equal.
- **No hidden statistics.** Statistical tests are shown only from `evooptlab report` outputs
  (`<root>/reports/*/analysis.json`), so the pre-registration guard of ADR 0007 applies to
  everything the dashboard displays. Without a report, only the aggregate's descriptive summary is
  shown, labelled "no tests".
- **HPO test results** are shown only if `evooptlab test-eval` stored them. They are never
  computed by the dashboard. A stored record whose `config_hash` differs from the run's is shown
  as a mismatch and not used.
- **Expensive work runs on request.** Convergence curves read every history of the selection, so
  they are computed only when **Compute curves** is pressed, then cached for that selection. A
  run's objective space is read once and cached. Indicators of a run come from its aggregate
  when one holds it. They are computed live, with the same function and default policy as
  `aggregate`, only when no aggregate exists, and that is labelled.

### D3. Integrity labels

- **Stage.** Every page selects one stage, final first when present. Pilot and development pages
  carry a PRELIMINARY banner, and figure titles of non-final data say PRELIMINARY. A selection
  that mixes stages is warned about.
- **Budgets.** A selection with several evaluation budgets is warned about. Convergence curves
  refuse to overlay different budgets or problems (`IncomparableRunsError`), and the explorer
  pages show one budget at a time. Runs that did not complete are counted, not scored.
- **Cached and stale.** The sidebar shows when the catalog snapshot was loaded, and **Reload
  artifacts** rescans the root.
  - An aggregate is stale when a run it lists is missing, or a run of its study started after it
    was written.
  - A report inherits its aggregate's staleness, and is stale when that aggregate is not under
    the root.
- **Empty states.** Every page shows "No results available." with the command that would produce
  the missing artifact, never placeholder numbers. Unreadable entries are listed, never modified.
- **Open plan.** A report whose analysis plan is not `frozen` is marked exploratory (P9).

### D4. Launch and network exposure

```bash
python -m streamlit run dashboard/app.py -- --root artifacts/experiments
```

The root can also be set with `EVOOPTLAB_ARTIFACT_ROOT` or in the sidebar. `make dashboard
ROOT=...` runs the same command. By default Streamlit listens on all network interfaces and sends
usage statistics, so `.streamlit/config.toml` binds the server to `localhost` and disables usage
statistics. `dashboard/check_launch.py` starts the documented command, waits for the health
endpoint and the app page, and stops the server. CI runs it on the HPO smoke root.

## Consequences and limitations

- **First view of a large run.** Opening a run with a very large non-dominated set takes several
  seconds the first time: 4.5 s for a 10 000-evaluation DTLZ2 pilot run, down from 11 s before
  stored indicators were used. The time goes to the quadratic dominance check of the core
  (`evaluation/dominance.py`). It is cached afterwards, and the core was not changed.
- **No per-trial cost.** Per-trial fit time is not recorded (ADR 0006), so "quality vs cost" in
  the HPO Explorer is per run: final quality against the run's wall-clock time.
- **One root at a time.** The benchmark and HPO pilots live under different roots, so the root
  is switched in the sidebar.
- **Not implemented.** Experiment execution from the UI is not implemented. The spec allows it
  only behind an explicit action and confirmation, and keeping the dashboard strictly read-only
  is simpler to verify.
- **Not tested.** Browser rendering itself (Plotly in a real browser) is not tested. The tests
  cover data loading, transformations, figure construction, every page through `AppTest`, and a
  real server start.
