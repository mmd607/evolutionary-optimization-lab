# Reproduction guide

This guide lists every command needed to reproduce the stored artifacts, from a fresh clone to
tables, figures, the manuscript audit and the dashboard. Every command below exists in this
version (`evooptlab --help`). Commands are run from the repository root.

> **Status (v0.0.1).** Only *pilot* studies exist, and their results are PRELIMINARY. Final runs
> are blocked on open protocol decisions P3, P4, P5, P8, P9 and P10
> (`docs/decisions/0001-foundation-and-protocol-decisions.md` and the ADRs listed there). Running
> a `final` study needs a frozen analysis plan and a clean, committed source tree.

## 1. Environment

Requires Python 3.11 or 3.12 and pip ≥ 25.1. Dependencies are pinned in
`requirements/constraints-py312.txt`, which was tested locally on Python 3.12 on Windows. CI is
configured for Python 3.11 and 3.12 on Ubuntu and 3.12 on Windows (`.github/workflows/ci.yml`).

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
python -m pip install --upgrade "pip>=25.1"
python -m pip install -c requirements/constraints-py312.txt -e ".[dashboard]" --group dev
python -m evooptlab env          # environment metadata recorded with every run
```

Leave out `.[dashboard]` if you don't need the dashboard. The dashboard tests are then skipped.

## 2. Verify the installation

```bash
python -m ruff check . && python -m ruff format --check .
python -m mypy
python -m pytest --cov                     # offline; no dataset download needed
python -m evooptlab validate-config configs/*.yaml configs/studies/*.yaml
```

## 3. Benchmark studies

```bash
python -m evooptlab plan configs/studies/pilot_core.yaml       # the run matrix; runs nothing
python -m evooptlab run configs/studies/pilot_core.yaml        # artifacts/experiments/pilot/<run_id>/
python -m evooptlab run configs/studies/pilot_core.yaml --resume   # continue after an interruption
python -m evooptlab diagnose configs/studies/pilot_core.yaml   # integrity, fairness, timing checks
python -m evooptlab aggregate configs/studies/pilot_core.yaml  # artifacts/experiments/aggregates/pilot/<name>/
```

`configs/studies/smoke.yaml` runs the same pipeline in seconds (`make smoke` writes it to
`build/smoke`). Seeds are listed in each study file, and every run records its seed, git commit,
source-tree state, package versions and CPU (`run_metadata.json`).

## 4. HPO studies

```bash
python -m evooptlab data info                                     # sources, licences, checksums
python -m evooptlab data fetch bank_marketing california_housing  # verified download into data/raw/
python -m evooptlab run configs/studies/hpo_pilot.yaml
python -m evooptlab test-eval configs/studies/hpo_pilot.yaml      # once per run, after the search
python -m evooptlab diagnose configs/studies/hpo_pilot.yaml
python -m evooptlab aggregate configs/studies/hpo_pilot.yaml
```

Downloads are checked against the SHA-256 and size recorded in `src/evooptlab/hpo/datasets.py`
before they are written. The data are never committed. The search sees cross-validation on the
training rows only. The held-out test score is computed once, by `test-eval`, and stored
write-once (ADR 0006). `make hpo-smoke` runs the pipeline on the bundled breast-cancer data with
no download.

## 5. Analysis, tables and figures

```bash
python -m evooptlab report artifacts/experiments/aggregates/pilot/<aggregate>
# -> artifacts/experiments/reports/<aggregate>__<plan>/ : analysis.json, CSVs, values.json,
#    tables/*.md|.tex, figures/*.svg|.pdf (+ the CSV each figure plots), README.md
```

Reports are regenerated from the aggregate, the stored histories, `configs/analysis_plan.yaml`
and `configs/reporting.yaml`. Two runs on the same inputs produce byte-identical files (checked
in the release review, ADR 0009). The analysis plan is a proposal (P9), so every output is
labelled PRELIMINARY until the plan is frozen.

## 6. Manuscript

```bash
python -m evooptlab audit-claims reports/paper/manuscript.md
python -m evooptlab render-paper reports/paper/manuscript.md --values <report>/values.json --output <file>
```

The manuscript contains no typed result. Numbers come from `values.json` through
`{{value:KEY}}`, and the audit checks citations, claim evidence and wording (ADR 0007).

## 7. Dashboard

```bash
python -m streamlit run dashboard/app.py -- --root artifacts/experiments   # http://localhost:8501
python dashboard/check_launch.py --root artifacts/experiments               # start, health-check, stop
```

The dashboard is read-only and shows only stored artifacts (ADR 0008).

## 8. Artifact layout

```text
<root>/{pilot,development,final}/<run_id>/   run_metadata.json, config.yaml, metrics.json,
                                             history.csv, logs/run.log.jsonl
<root>/test_evaluations/<stage>/<run_id>.json   held-out HPO evaluations (write-once)
<root>/aggregates/<stage>/<name>/            runs.csv, summary.csv, manifest.json
<root>/reports/<name>/                       evooptlab report output
```

Artifacts are never overwritten. The run ID scheme, the stages and the fairness checks are
described in `docs/experimental_protocol.md` and ADR 0005.

## 9. What does not reproduce bit-for-bit

- **Wall-clock and timing columns** depend on the machine and its load.
- **Optimization results** are seeded and deterministic for a fixed environment. Tests cover
  this: `tests/integration/test_runner.py::TestDeterminism::test_same_seed_same_history` and
  `tests/integration/test_study_runner.py::test_histories_are_reproducible_across_roots`. Other
  package versions or platforms (BLAS, CPU) may change floating-point results; the environment
  record of each run lets you check.
- **Dataset downloads** depend on the sources staying available. A changed file is rejected by
  its checksum and never used silently.
