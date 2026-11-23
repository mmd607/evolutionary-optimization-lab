# Phase Status

Allowed statuses: `NOT STARTED`, `IN PROGRESS`, `BLOCKED`, `READY FOR REVIEW`, `APPROVED`,
`PUBLISHED`. A phase is `PUBLISHED` only after its branch exists on GitHub and the remote SHA has
been verified against the local HEAD.

**Local HEAD** is the last commit of the phase's implementation. Updating this file adds one more
commit on top of it, so the branch tip is always that SHA plus the status-file commit.

| Phase | Branch | Status | Local HEAD | Remote Published | Review |
|---|---|---|---|---|---|
| 00 | `phase/00-foundation` | PUBLISHED | `49012a0` | Yes (`5c7f7e1` verified 2026-11-23; merged to `main` via PR #1) | Approved |
| 01 | `phase/01-core-interfaces` | PUBLISHED | `ff455aa` | Yes (`f365ef3` verified 2026-11-23) | Pending |
| 02 | `phase/02-benchmarks` | NOT STARTED | — | No | Pending |
| 03 | `phase/03-algorithms` | NOT STARTED | — | No | Pending |
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
