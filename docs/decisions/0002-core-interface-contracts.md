# ADR 0002 — Core interface contracts

- **Status:** Proposed (awaiting owner review at the Phase 01 gate)
- **Date:** 2026-11-23
- **Phase:** 01 — Core interfaces

## Context

`docs/architecture.md` sketches `Problem`, `Algorithm`, `Evaluator` and `ExperimentRunner`. Phase 01
turns them into typed interfaces. The fairness of every later comparison depends on how they account
for evaluations, so the contracts are recorded here.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| C1 | All objectives are **minimized**. Scores to maximize are exposed negated or as `1 - score`. | One direction removes sign errors in dominance, HV and ranking. |
| C2 | Inequality constraints are feasible when **`g(x) <= 0`**. Violation = `sum(max(0, g_j))`. | Same convention as pymoo, which Phase 02 is expected to use as a reference. |
| C3 | Evaluation is **batched** (`(n, d)` in, `(n, m)` / `(n, c)` out). | Population-based algorithms evaluate whole generations; one convention for all. |
| C4 | Algorithms receive only the immutable `ProblemSpec`, never the `Problem`. | An algorithm cannot evaluate outside the budget. |
| C5 | `ask(max_candidates)` must return `1..max_candidates` candidates. The runner never truncates. | Final partial generations are handled explicitly by each algorithm and stay visible in its code. |
| C6 | Out-of-bounds candidates are **rejected** (`CandidateError`), never clipped by the framework. | Repair strategy is an algorithm design choice and must be documented per algorithm (Phase 03). |
| C7 | One candidate evaluated = one objective evaluation. A batch that would exceed the budget is rejected before evaluation. | The budget can never be exceeded. |
| C8 | Problem crashes and malformed or non-finite outputs **count as spent** and are tracked as failed evaluations. Invalid candidates are rejected without spending budget. | Attempted evaluations cost compute (important for HPO). Invalid candidates are algorithm bugs. |
| C9 | The algorithm RNG is `PCG64(derive_seed(run_seed, "algorithm"))`. Further named streams (such as problem noise) can be added without changing existing ones. | Deterministic and independent streams, with no global random state. |
| C10 | Failed runs (contract violation, objective failure, timeout, interrupt) keep all artifacts and are marked `failed` with a reason. Interrupts are re-raised after recording. | Protocol: report failed runs and never drop them silently. |
| C11 | `history.csv` stores every evaluation with `repr(float)`, which round-trips exactly. Timing goes only to `metrics.json`. | Full precision is preserved, and same-seed runs produce byte-identical histories. |
| C12 | `metrics.json` holds accounting and timing only in Phase 01. Quality metrics (HV, IGD, ...) are added in Phase 02. | Keeps scope; metric definitions need the Phase 02 reference checks. |
| C13 | Synthetic problems (`Sphere`, `TwoSpheres`, `ConstrainedSphere`) are framework tests only and are flagged `synthetic: true`. | They must not be reported as benchmark results. |
| C14 | Test-only algorithms live in `tests/helpers.py`. No baseline algorithm is implemented in Phase 01. | Algorithms are Phase 03 scope. |

## Not yet decided

- **P6 (seed policy)** is still open. Both mechanisms are implemented: explicit run seeds, and
  `derive_run_seeds(master_seed, n, *scope)`. The experiment sweep that maps config files to runs
  is Phase 04 scope and must use whichever policy the owner chooses.
- **Checkpoint/resume** is supported at the interface level (`state_dict` / `load_state_dict`), but
  the runner does not yet write checkpoints.
- The runner executes one run at a time. Parallel execution (`execution.n_jobs`) is Phase 04 scope.
