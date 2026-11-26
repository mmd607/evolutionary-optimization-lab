# Phase Status

Allowed statuses: `NOT STARTED`, `IN PROGRESS`, `BLOCKED`, `READY FOR REVIEW`, `APPROVED`,
`PUBLISHED`. A phase is `PUBLISHED` only after its branch exists on GitHub and the remote SHA has
been verified against the local HEAD.

**Local HEAD** is the last commit of the phase's implementation. Updating this file adds one more
commit on top of it, so the branch tip is always that SHA plus the status-file commit.

| Phase | Branch | Status | Local HEAD | Remote Published | Review |
|---|---|---|---|---|---|
| 00 | `phase/00-foundation` | PUBLISHED | `49012a0` | Yes (`5c7f7e1` verified 2026-11-23; merged to `main` via PR #1) | Approved |
| 01 | `phase/01-core-interfaces` | PUBLISHED | `ff455aa` | Yes (`f365ef3` verified 2026-11-23; merged to `main` via PR #2) | Approved |
| 02 | `phase/02-benchmarks` | PUBLISHED | `1ce9e6b` | Yes (`ae172f6` verified 2026-11-24) | Pending |
| 03 | `phase/03-algorithms` | PUBLISHED | `40dcf42` | Yes (`40dcf42` verified 2026-11-25) | Pending |
| 04 | `phase/04-experiments` | PUBLISHED | `76afce4` | Yes (`14cdd7d` verified 2026-11-25) | Pending |
| 05 | `phase/05-hyperparameter-optimization` | PUBLISHED | `28b6d51` | Yes (`2a136eb` verified 2026-11-26) | Pending |
| 06 | `phase/06-analysis-and-paper` | PUBLISHED | `728cd4b` | Yes (`7fd6841` verified 2026-11-26) | Pending |
| 07 | `phase/07-dashboard` | NOT STARTED | — | No | Pending |
| 08 | `phase/08-release-review` | NOT STARTED | — | No | Pending |

## Phase 00 — Foundation

- **Base branch:** `main` @ `1bea708`
- **Validation (local, Windows, Python 3.12.3):** Ruff lint PASS · Ruff format PASS · MyPy strict
  PASS (18 files) · Pytest PASS (75 tests, 98.19 % branch coverage) · config validation PASS ·
  clean-venv install PASS.
- **Not run locally:** Python 3.11 (not installed on the dev machine; covered by the CI matrix),
  GitHub Actions (runs on first push), `actionlint`, remote pre-commit hooks.
- **Open decisions:** P1–P11 in `docs/decisions/0001-foundation-and-protocol-decisions.md`.
- **Published:** pushed to `origin/phase/00-foundation`; remote SHA `5c7f7e1` matched local HEAD.
- **Gate:** owner reviews the foundation and protocol before Phase 01 starts.

## Phase 01 — Core interfaces

- **Base branch:** `origin/main` @ `06d3def` (merge of PR #1; content identical to Phase 00 tip `12d2d3f`)
- **Delivered:** `Problem`/`ProblemSpec`, ask/tell `Algorithm`, budgeted `Evaluator`,
  `ExperimentRunner` + `RunSpec`, deterministic seed derivation, exclusive run-artifact writes,
  synthetic framework-test problems. Contracts: `docs/decisions/0002-core-interface-contracts.md`.
- **Validation (local, Windows, Python 3.12.3, clean venv):** Ruff lint PASS · Ruff format PASS ·
  MyPy strict PASS (34 files) · Pytest PASS (181 tests, 98.97 % branch coverage) · config
  validation PASS.
- **Not run locally:** Python 3.11 (CI matrix), GitHub Actions (runs on push).
- **Still open:** P6 seed policy (both mechanisms implemented); checkpoint writing; parallel runs.
- **Published:** pushed to `origin/phase/01-core-interfaces`; remote SHA `f365ef3` matched local HEAD.
- **Gate:** owner reviews interfaces before Phase 02 starts.

## Phase 02 — Benchmarks and metrics

- **Base branch:** `origin/main` @ `76a54f0` (merge of PR #2)
- **Delivered:** ZDT1-3, DTLZ2, DTLZ7 with analytical reference fronts and provenance metadata;
  config-driven suite registry; Pareto dominance utilities; exact HV, GD, GD+, IGD, IGD+, spacing,
  feasibility rate; proposed normalization / HV reference-point policy (`proposed-v1`).
  Docs: `docs/benchmark_problems.md`, `docs/decisions/0003-metrics-normalization-and-reference-points.md`.
- **References:** analytical fronts and limits, inclusion-exclusion, and pymoo 0.6.2 (test-only).
- **Validation (local, Windows, Python 3.12.3, clean venv):** Ruff lint PASS · Ruff format PASS ·
  MyPy strict PASS (47 files) · Pytest PASS (261 tests, 0 skipped, 99.05 % branch coverage) ·
  config validation PASS.
- **Not run locally:** Python 3.11 (CI matrix; dependency pins chosen from pip's 3.11 resolution).
- **Needs owner decision:** P8 policy in ADR 0003 (incl. the 1.1 reference offset, pending
  literature check); source citations are recorded unverified.
- **Published:** pushed to `origin/phase/02-benchmarks`; remote SHA `ae172f6` matched local HEAD.
- **Gate:** owner reviews benchmarks and metric policy before Phase 03 starts.

## Phase 03 — Algorithms

- **Base branch:** `origin/phase/02-benchmarks` @ `92d49c3` (Phase 02 was not yet merged to `main`)
- **Delivered:** `random_search` (native); pymoo 0.6.2 adapters `ga`, `nsga2`, `de`, `gde3`, `pso`,
  `cmopso` behind the budgeted ask/tell contract with an evaluation guard; name registry;
  invariant and default-drift tests. Docs: `docs/decisions/0004-algorithm-variants-and-tuning-protocol.md`.
- **Finding:** pymoo 0.6.2 `MOPSO_CD` evaluates outside ask/tell during setup; rejected.
- **Deferred:** Optuna sampler to Phase 05 (its valid domain is HPO).
- **Validation (local, Windows, Python 3.12.3, clean venv):** Ruff lint PASS · Ruff format PASS ·
  MyPy strict PASS (54 files) · Pytest PASS (329 tests, 99.19 % branch coverage) · config
  validation PASS.
- **Not run locally:** Python 3.11 (CI matrix).
- **Needs owner decision:** P7 (GDE3 + CMOPSO proposed), P10 (defaults without tuning proposed),
  population-size policy; P8 still pending from Phase 02.
- **Published:** pushed to `origin/phase/03-algorithms`; remote SHA `40dcf42` matched local HEAD.
- **Gate:** owner reviews algorithms before Phase 04 starts.

## Phase 04 — Experiments

- **Base branch:** `origin/phase/03-algorithms` @ `f7c8fdf` (Phase 03 was not yet merged to `main`)
- **Published:** `origin/phase/04-experiments` @ `14cdd7d` (remote SHA verified 2026-11-25)
- **Delivered:** study configs (`configs/studies/`, schema `study`), matrix expansion with
  pre-run validation, paired seeds and interleaved order, a study runner with safe resume
  (config-hash matching, failures are not retried, interrupted runs are rerun under new IDs), a
  final-stage clean-commit guard, diagnostics from disk (9 checks plus timing and a compute
  projection), aggregation (`runs.csv`, `summary.csv`, `manifest.json`), CLI `plan` / `run` /
  `diagnose` / `aggregate`, `make smoke`, and a CI smoke step. Docs:
  `docs/decisions/0005-experiment-runner-and-fairness-checks.md`.
- **Fix found by the pilot:** exact 3-D HV went from O(n³) to a vectorized staircase (272 s ->
  under 1 s for about 2 000 points; exactness tested against pymoo and the previous algorithm).
- **Pilot diagnostics (`pilot_core`, PRELIMINARY, local Windows CPU):** 100/100 runs completed,
  all 9 checks PASS (one commit, clean tree, uniform environment). The run took about 1.6 min
  sequentially and the aggregation about 3 min. The linear projection for 20 replicates at
  10 000 evaluations is about 245 s of run time. Artifacts are kept outside the repository and
  were not committed.
- **Finding for P8:** the 91-point DTLZ2 reference front holds only 92.25 % of the analytical HV,
  so the HV ratio reaches about 1.04 (options in ADR 0005).
- **Validation (local, Windows, Python 3.12, clean venv from a clean worktree):** Ruff lint PASS ·
  Ruff format PASS · MyPy strict PASS (65 files) · Pytest PASS (388 tests, 99.08 % branch
  coverage) · config validation PASS (5 files) · CI smoke steps PASS.
- **Not run locally:** Python 3.11 (CI matrix).
- **Not implemented:** parallel execution (`n_jobs`), pending an owner decision on timing
  comparability. `scripts/` and `notebooks/` (ADR 0001) are not needed; the CLI covers them.
- **Needs owner decision:** P5 (final budgets and seed counts, which the projection informs),
  P6 (seed policy), P7, P8 (plus the reference-front finding), P10; and whether
  `experiments.yaml` placeholders should be replaced.
- **Gate:** owner reviews the pilot diagnostics before Phase 05 starts.

## Phase 05 — Hyperparameter optimization

- **Published:** `origin/phase/05-hyperparameter-optimization` @ `2a136eb` (remote SHA verified
  2026-11-26)
- **Base branch:** `origin/phase/04-experiments` @ `c5abe4d` (Phase 03 and 04 are not yet merged
  to `main`)
- **Delivered:**
  - A dataset catalogue with provenance and licences, and verified downloads (`evooptlab data
    fetch / info`, SHA-256 and size checked before writing; data are never committed).
  - Leakage-safe HPO problems: unit-cube search space, HistGradientBoosting pipeline,
    cross-validation on training rows only, failed trials recorded as infeasible.
  - The Optuna TPE baseline (`optuna_tpe`).
  - A one-time held-out test evaluation (`evooptlab test-eval`, write-once).
  - HPO diagnostics (`failed_trials`, `test_evaluations`) and aggregation.
  - HPO smoke and pilot studies, and an HPO smoke step in CI.
  - Docs: `docs/decisions/0006-hpo-tasks-and-leakage-controls.md`.
- **Gate (leakage tests):** `tests/leakage/test_hpo_leakage.py` PASS. Changing test labels or
  features leaves every search objective bit-identical, encoders never see validation or test
  rows, and the split does not depend on the run seed or algorithm.
- **Core change:** `Problem.describe()` adds `problem.details` to the run config hash. Benchmark
  config hashes are unchanged, pinned by a regression test.
- **Pilot (`hpo_pilot`, PRELIMINARY, local Windows CPU, clean worktree at `3a58ab7`):**
  - 45/45 runs completed, 0 failed trials, 45 test evaluations, all 11 diagnostics PASS.
  - 85 min run time and 52 s of test evaluation.
  - The projection for 100 trials × 10 seeds is about 8.6 h sequential, likely more (ADR 0006).
  - Bank marketing has 644/8 238 test rows that duplicate training feature rows (P4).
  - Artifacts are kept outside the repository and were not committed.
- **Validation (local, Windows, Python 3.12, clean venv from a clean worktree):** Ruff lint PASS
  · Ruff format PASS · MyPy strict PASS (79 files) · Pytest PASS (470 tests, 98.73 % branch
  coverage) · config validation PASS (7 files) · CI smoke and HPO smoke steps PASS · every
  intermediate commit passes MyPy and Pytest on its own.
- **Not run locally:** Python 3.11 (CI matrix).
- **Not implemented:** per-trial timeouts, parallel trials, and multi-objective HPO quality
  indicators (ADR 0006).
- **Needs owner decision:**
  - P3: Wine Quality.
  - P4: split strategies, including the temporal split and deduplication for bank marketing.
  - P5: trial budget and seeds (the protocol asks for at least 10 HPO seeds).
  - P10: model family, search space and population sizes.
  - Whether `fit_seconds` becomes a second objective.
  - P11: branch naming (this branch follows the workflow instructions).
- **Gate:** owner reviews the leakage controls and pilot diagnostics before Phase 06 starts.

## Phase 06 — Analysis and paper

- **Published:** `origin/phase/06-analysis-and-paper` @ `7fd6841` (remote SHA verified
  2026-11-26)
- **Base branch:** `origin/phase/05-hyperparameter-optimization` @ `87fdec5` (Phases 03–05 are not
  yet merged to `main`)
- **Scope note:** no final run artifacts exist (final runs are blocked on P3, P4, P5, P8, P9 and
  P10). This phase therefore delivers the tested pipeline and guards and reports **no result**.
- **Delivered:**
  - The analysis plan config (P9, `status: proposal`), with a pre-registration guard: final-stage
    results are refused unless the plan is frozen and the tree is clean.
  - Statistics tested against scipy and hand-computed values: Wilcoxon, Holm, Friedman, A12,
    bootstrap CIs.
  - `evooptlab report`: analysis, Markdown and LaTeX tables, SVG and PDF figures with their data,
    and `values.json`.
  - `evooptlab audit-claims` and `render-paper`.
  - A manuscript draft with a claim-evidence matrix (16 method claims supported, 4 result claims
    pending) that passes the audit in CI.
  - Docs: `docs/decisions/0007-analysis-reporting-and-claims-audit.md`.
- **Gate ("claims audited"):** the draft passes `audit-claims` (0 citations; literature matrix
  empty). Citation support still needs human review.
- **Fixes:** the Optuna dependency floor is raised to `>= 5.0` (the adapter needs
  `Trial.set_constraint`); scipy and matplotlib are declared directly.
- **Finding (P5/P9):** the smallest paired two-sided Wilcoxon p-value is 2/2^n. Under the proposed
  Holm family of 30 tests per metric, n = 10 replicates can never yield a rejection; n ≥ 11 is
  needed (ADR 0007).
- **Pilot analyses:** `report` on both pilot aggregates gives PRELIMINARY tables and figures, with
  every test "not run" at `min_replicates: 10`. Not committed.
- **Validation (local, Windows, Python 3.12, clean venv from a clean worktree):** Ruff lint PASS
  · Ruff format PASS · MyPy strict PASS (92 files) · Pytest PASS (511 tests, 98.20 % branch
  coverage) · config validation PASS (9 files) · CI smoke, HPO smoke + report, and claims-audit
  steps PASS · every intermediate commit passes MyPy and Pytest on its own.
- **Observation:** the first Pytest run in the fresh venv reported 30 warnings, all tests passing.
  Two later full runs in the same venv reported none, and the cause was not identified (an empty
  matplotlib cache did not reproduce it).
- **Not run locally:** Python 3.11 (CI matrix).
- **Not done / blocked:** the final analysis and result text, freezing the plan (P9), the
  literature review and related work, the ablation and sensitivity study (RQ2), and the technical
  report.
- **Phase 05 acceptance note:** only two non-smoke HPO tasks ran in the pilot; Wine Quality
  waits for P3.
- **Needs owner decision:** P9 (freeze or change the plan, including the Holm family and the
  replicate count), plus the open P3, P4, P5, P8 and P10; also P1 (licence) and P2 (authors) for
  the manuscript.
- **Gate:** owner reviews the analysis plan, the audit rules and the manuscript draft before
  Phase 07 starts.
