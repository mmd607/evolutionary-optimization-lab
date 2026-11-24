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
| 03 | `phase/03-algorithms` | READY FOR REVIEW | `ec9ea8a` | No | Pending |
| 04 | `phase/04-experiments` | NOT STARTED | — | No | Pending |
| 05 | `phase/05-hyperparameter-optimization` | NOT STARTED | — | No | Pending |
| 06 | `phase/06-analysis-and-paper` | NOT STARTED | — | No | Pending |
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
- **Gate:** owner reviews algorithms before Phase 04 starts.
