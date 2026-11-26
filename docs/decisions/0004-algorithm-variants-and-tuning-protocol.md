# ADR 0004 — Algorithm variants, valid domains, defaults, and tuning protocol

- **Status:** Proposed. This answers open decisions **P7** (DE/PSO variants) and **P10** (tuning
  protocol) from ADR 0001 and needs owner approval before final runs.
- **Date:** 2026-11-24
- **Phase:** 03 — Algorithms
- **Code:** `src/evooptlab/algorithms/`

## Context

The research charter requires Random Search, a GA, NSGA-II, a DE variant, a PSO variant, and a
Bayesian/Optuna sampler. Every one has to run under the shared budgeted ask/tell contract
(ADR 0002) and be valid for the problems it is compared on. The Phase 03 prompt says: *avoid
implementing a custom algorithm unless correctness can be validated*.

## Decision: implementations

| Name | Variant | Domain | Implementation |
|---|---|---|---|
| `random_search` | Uniform sampling in the box, batch 100 | any M, constraints recorded only | EvoOptLab (trivial; unit-tested) |
| `ga` | Generational GA: SBX + polynomial mutation, binary tournament, fitness survival, duplicate elimination | M = 1 | pymoo 0.6.2 `GA` |
| `nsga2` | NSGA-II: SBX + polynomial mutation, rank-and-crowding survival | M ≥ 2 | pymoo 0.6.2 `NSGA2` |
| `de` | DE/best/1/bin, pymoo CR/F defaults | M = 1 | pymoo 0.6.2 `DE` |
| `gde3` | GDE3 (Kukkonen & Lampinen, 2005, *[verify]*): DE/rand/1/bin, CR = 0.5, F random in (0, 1), dominance-based selection | M ≥ 2 | pymoo 0.6.2 `GDE3` |
| `pso` | PSO with adaptive inertia, LHS initialization, w = 0.9, c1 = c2 = 2 | M = 1 | pymoo 0.6.2 `PSO` |
| `cmopso` | CMOPSO (competitive-mechanism MOPSO), to-bound repair | M ≥ 2 | pymoo 0.6.2 `CMOPSO` |

**Proposed for P7:** GDE3 is the multi-objective DE variant and CMOPSO is the multi-objective PSO
variant used on the ZDT/DTLZ suite. The single-objective `de` and `pso` are kept for
single-objective problems, such as scalar HPO objectives in Phase 05.

### Adapter guarantees (`pymoo_adapter.py`)

1. **No hidden evaluations.** pymoo is set up on a guard problem whose `_evaluate` raises.
   Every evaluation goes through the budgeted evaluator.
2. **No library termination.** pymoo uses `NoTermination`, so the evaluation budget is the only
   stopping rule.
3. **Determinism.** The pymoo seed is drawn from the injected run RNG. Tests confirm byte-identical
   histories under a fixed seed, even after the global NumPy state is perturbed.
4. **Final partial generation.** When the remaining budget is smaller than pymoo's batch, only the
   first `remaining` candidates are evaluated. They count, they are stored, and the run ends with
   them.
5. **Bounds.** Candidates are clipped, the count goes to `n_repaired`, and pymoo's population is
   updated to match. In the invariant tests no adapter produced out-of-bounds candidates
   (`n_repaired = 0`).
6. **Explicit defaults.** Every hyperparameter is passed explicitly. Its default equals pymoo
   0.6.2's constructor default, which `test_defaults_match_pymoo.py` enforces, so a library
   upgrade cannot change runs silently.

## Rejected or deferred

- **pymoo `MOPSO_CD` (rejected).** In pymoo 0.6.2, `MOPSO_CD._setup` evaluates an initial
  population that `_initialize_infill` then discards. That is `pop_size` objective evaluations
  outside the ask/tell loop, which breaks budget accounting. The guard problem caught it during
  prototyping. It is not patched, because modifying library internals would make the "maintained
  implementation" argument void.
- **Custom implementations of GDE3/MOPSO (rejected).** pymoo provides maintained versions, so
  writing unvalidated custom versions is unnecessary.
- **Optuna sampler (deferred to Phase 05).** Its "appropriate" domain is the HPO tasks, which do
  not exist until Phase 05. It will be added there behind the same ask/tell adapter pattern
  (`study.ask` / `study.tell`), with the same invariant tests. *Resolved 2026-11-25:* added as
  `optuna_tpe` (ADR 0006, D10).

## Population sizes (open)

Defaults are pymoo's: 100 for all population-based methods except `pso` (25). Under the pilot
budget of 10 000 evaluations that gives about 100 generations (400 for PSO). Population size is an
RQ2 factor. Whether the primary comparison uses library defaults or a common population size is
part of the tuning decision below.

## Proposed tuning protocol (P10)

1. **Primary comparison: library defaults, no tuning.** All algorithms are equally untuned, the
   setting is reproducible from the pymoo version alone, and it avoids tuning-effort bias.
2. **Optional tuned comparison** (only if the owner approves): an equal tuning budget per
   algorithm, performed only on a **calibration set disjoint from the final benchmarks**, for
   example ZDT4, ZDT6 and DTLZ1, which are listed in `docs/dataset_and_benchmarks.md` but are not
   in the core suite. Tuning budget, search space and selection metric are fixed in advance and
   reported.
3. **Population-size sensitivity** (RQ2) runs as a separate experiment and is not folded into the
   primary ranking.

## Follow-ups

- `configs/experiments.yaml` still lists placeholder names (`differential_evolution_variant`,
  `particle_swarm_variant`). Once P7 is approved they should become `gde3` and `cmopso`. The
  owner's config is left untouched until then.
- Literature verification is needed for the GDE3 and CMOPSO citations and for whether the pymoo
  implementations match the original papers.
