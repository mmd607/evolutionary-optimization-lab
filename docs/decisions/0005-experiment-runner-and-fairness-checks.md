# ADR 0005 — Experiment matrices, safe resume, aggregation and fairness checks

- **Status:** Accepted for the implementation. The open protocol choices it touches (P5, P6, P7,
  P8, P10) still need owner decisions before final runs.
- **Date:** 2026-11-25
- **Phase:** 04 — Experiments
- **Code:** `src/evooptlab/experiments/`, `src/evooptlab/cli.py`, `configs/studies/`

## Context

Phase 04 has to run controlled, repeatable benchmark matrices from configs, keep pilot and final
results apart, record evaluation counts and wall-clock time, persist complete histories, resume
only where that cannot corrupt artifacts, aggregate results, and produce pilot diagnostics before
any full-scale run. The acceptance criterion is: *a clean command can run a small matrix
end-to-end; artifacts are immutable and reproducible; fairness checks are documented.*

## Decisions

### D1. One study file per matrix (`configs/studies/*.yaml`, root key `study`)

A study lists problems (with explicit dimensions), algorithms (with explicit hyperparameter
overrides, empty by default), the budget, the seed policy, the stage, and an optional per-run
timeout. Study files are always loaded with `--strict`, so a placeholder can never reach a run.

The owner's `configs/benchmarks.yaml` and `configs/experiments.yaml` are left unchanged.
`experiments.yaml` still names the unresolved placeholders `differential_evolution_variant` and
`particle_swarm_variant`. A study that used those names would fail at planning with
"unknown algorithm".

- `smoke.yaml`: 2 problems × 2 algorithms × 2 seeds × 500 evaluations, run in CI. Framework check
  only.
- `pilot_core.yaml`: the core suite from `benchmarks.yaml` (5 problems, 10 000 evaluations, pilot
  seeds 11/23/37/41/59) with `random_search`, `nsga2` and the ADR 0004 *proposals* `gde3` and
  `cmopso`. It is preliminary until P7 is approved.

### D2. Both seed policies are supported, and seeds are paired (P6 stays open)

- `explicit`: the listed seeds are the replicate seeds.
- `derived`: `derive_run_seeds(master_seed, n_replicates, problem)`.

Either way, replicate *i* of a problem uses the **same run seed for every algorithm** (common
random numbers). This allows paired comparisons and removes seed-set luck as a confound.

### D3. Matrix validation happens before anything runs

Unknown problems or algorithms, invalid hyperparameters, and algorithm/problem pairs outside an
algorithm's domain (for example `pso` on a bi-objective problem) are all collected and reported
together. **Incompatible pairs are never skipped silently**, because a silently smaller matrix
would bias comparisons.

### D4. Interleaved execution order

Cells run problem → replicate → algorithm. Every algorithm runs once before the next replicate
starts, so slow machine-load drift spreads across algorithms instead of hitting whichever one ran
last.

### D5. A cell is identified by the hash of its run config

A stored run belongs to a planned cell when its `config_hash`, the SHA-256 of the canonical
`config.yaml` document, equals the cell's hash. The hash covers the problem and bounds, algorithm
name and every parameter, seed and seed streams, budget, stage, timeout, study name and replicate.
Changing any of these produces a different cell and a fresh run. Adding replicates or problems
leaves the existing cells untouched.

### D6. Resume can never corrupt or overwrite artifacts

| Stored state of a cell | `run` without `--resume` | `run --resume` |
|---|---|---|
| no run | runs | runs |
| `completed` | refuses the whole study | skipped |
| `failed` (genuine, for example a timeout or exception) | refuses | **skipped**: a failure is a result, and retrying until success would be cherry-picking |
| interrupted (`running` after a crash, or `failed: interrupted: ...`) | refuses | runs again under a **new** run ID; the interrupted run stays on disk |

The runner still creates every run directory and file exclusively (ADR 0002), so even a bug in
the resume logic could not overwrite an existing artifact.

### D7. Final-stage guard

`stage: final` refuses to start unless the git commit is known and the working tree is clean
(`git status --porcelain --untracked-files=no` is empty), so every final result traces to
committed code. Final-stage diagnostics additionally fail on missing cells, mixed commits, or a
dirty tree.

### D8. Diagnostics are computed from disk

`evooptlab diagnose` re-reads every stored run and reports these checks:

| Check | FAIL when | WARN when |
|---|---|---|
| `coverage` | final: a planned cell has no settled run | pilot or development: cells missing |
| `failed_runs` | — | a canonical run failed (kept, excluded from quality) |
| `budget_exact` | a completed run did not use exactly the study budget | — |
| `history_integrity` | `history.csv` rows ≠ recorded evaluations, or IDs not contiguous | — |
| `config_integrity` | `config.yaml` no longer matches its recorded hash | — |
| `paired_seeds` | algorithms of a problem were run on different seed sets | — |
| `environment` | final: more than one commit, or a dirty or unknown tree | python, CPU, numpy, scipy, pymoo or pydantic versions differ, or several commits or a dirty tree in a pilot |
| `stray_runs` | — | duplicates, interrupted, unplanned or unreadable run directories (all ignored, none deleted) |
| `failed_evaluations` | — | objective evaluations failed inside a run |

It also reports per-cell timing: median wall-clock time, seconds per evaluation, and the fraction
of time spent outside objective evaluation (algorithm overhead). `--project-budget N
--project-replicates R` turns the timing into a linear, sequential compute estimate for P5.

When a cell has several settled runs, the **earliest** one is canonical. The others are listed and
ignored.

### D9. Aggregation

`evooptlab aggregate` writes `runs.csv` (one row per canonical run), `summary.csv` (per problem ×
algorithm: planned, completed, failed and missing counts, plus median, quartiles, mean and
standard deviation of the HV ratio, IGD+, IGD, GD+ and wall-clock time) and `manifest.json`. The
manifest holds the quality policy, the matrix, the full diagnostics, the run IDs, the excluded
runs, the aggregator's git state, and `preliminary: true` for non-final stages.

- Quality is recomputed from each completed run's full history with ADR 0003's proposed-v1
  policy. That policy is still pending approval (P8).
- **Failed runs are counted but not scored.** They used fewer evaluations, so scoring them would
  break the equal-budget control.
- Aggregation **refuses** when any diagnostic is `FAIL`, and it never writes into an existing
  directory.
- Only descriptive statistics are produced. Hypothesis tests are Phase 06 (P9).

### D10. Parallel execution is not implemented yet

Runs execute sequentially. `execution.n_jobs` in `experiments.yaml` is not used. Parallelism
changes wall-clock comparability, because runs compete for cores, so it waits for an explicit
owner decision on how timing will be reported.

## Fairness controls (summary)

Equal objective-evaluation budget (enforced and verified), identical paired seeds, validated
algorithm domains, explicit and recorded hyperparameters, interleaved order, single-environment
check, timing reported separately from evaluations, failed runs kept and counted, and pilot or
development results labelled preliminary and stored apart from final ones.

## Consequences

- Final runs need a frozen final study file (`stage: final`). Writing one is blocked on P5
  (budgets and seed counts), P6 (seed policy), P7 (variants), P8 (quality policy) and P10
  (tuning).
- At low budgets the normalized HV can be exactly 0 on ZDT problems when no point dominates the
  1.1 reference point. That is a true measurement under the policy, not missing data, and IGD+
  stays informative. It is relevant to the P8 decision.

## Pilot findings (2026-11-25, `pilot_core`, preliminary)

The pilot (100 runs, 10 000 evaluations each, commit `613c87c`, clean tree) passed every
diagnostic. It produced two findings that changed or inform the implementation:

1. **Exact 3-D hypervolume was too slow.** Slicing called a quadratic non-dominated filter in
   every slice (O(n³)). One NSGA-II run on DTLZ2 with 2 142 non-dominated points took 272 s, and
   the full aggregation would have taken hours. The fix (commit `perf(metrics)`) uses a vectorized
   2-D staircase that is exact for dominated points and ties, so a 1 891-point front takes well
   under a second. Equality against the previous algorithm and against pymoo is tested. The
   aggregation of the pilot now takes about 3 minutes, mostly spent on non-dominated filtering of
   the 10 000-point histories.
2. **The HV ratio exceeds 1 on DTLZ2 (P8).** The default DTLZ2 reference front (Das-Dennis, 12
   partitions, 91 points) has only 92.25 % of the analytical hypervolume
   (1.1³ − π/6 ≈ 0.8074 in normalized space). A dense approximation set therefore scores
   `hypervolume_ratio ≈ 1.04`. With 60 partitions (1 891 points) the coverage is 98.4 %, and with
   100 partitions (5 151 points) it is 99.0 %. Options for the owner: (a) use the analytical HV
   as the ratio denominator where one exists (DTLZ2), (b) use denser reference fronts for every
   problem, or (c) report raw normalized HV only. The policy is **not** changed here, because P8
   is an owner decision.
