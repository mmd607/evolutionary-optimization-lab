# Phase Status

Allowed statuses: `NOT STARTED`, `IN PROGRESS`, `BLOCKED`, `READY FOR REVIEW`, `APPROVED`,
`PUBLISHED`. A phase is `PUBLISHED` only after its branch exists on GitHub and the remote SHA has
been verified against the local HEAD.

**Local HEAD** is the last commit of the phase's implementation. Updating this file adds one more
commit on top of it, so the branch tip is always that SHA plus the status-file commit.

| Phase | Branch | Status | Local HEAD | Remote Published | Review |
|---|---|---|---|---|---|
| 00 | `phase/00-foundation` | READY FOR REVIEW | `49012a0` | No | Pending |
| 01 | `phase/01-core-interfaces` | NOT STARTED | — | No | Pending |
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
- **Gate:** owner reviews the foundation and protocol before Phase 01 starts.
