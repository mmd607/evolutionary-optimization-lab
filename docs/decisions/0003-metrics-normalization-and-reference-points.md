# ADR 0003 — Metric definitions, normalization, and HV reference-point policy

- **Status:** Proposed. This answers open decision **P8** from ADR 0001 and needs owner approval
  before any final run.
- **Date:** 2026-11-24
- **Phase:** 02 — Benchmarks and metrics
- **Code:** `src/evooptlab/evaluation/metrics.py`, `src/evooptlab/evaluation/quality.py`
  (`POLICY_VERSION = "proposed-v1"`)

## Context

HV values depend on objective scaling and the reference point. Distance indicators have several
variants in the literature. Values cannot be compared across runs or papers unless both are fixed
and stated (`docs/metrics_and_statistics.md` §1).

## Indicator definitions (all objectives minimized)

| Indicator | Definition | Better | Valid when |
|---|---|---|---|
| HV | Exact Lebesgue measure dominated by A and bounded by r. Points not strictly better than r in every objective contribute 0. | higher | Fixed r and normalization across everything compared |
| IGD | mean over z in Z of min over a of ‖a − z‖₂ | lower | Reference front Z available and dense |
| IGD+ | mean over z of min over a of ‖max(a − z, 0)‖₂ | lower | Same as IGD; weakly Pareto compliant |
| GD | mean over a in A of min over z of ‖a − z‖₂ | lower | Convergence only, not diversity. Never reported alone. |
| GD+ | mean over a of min over z of ‖max(a − z, 0)‖₂ | lower | Same as GD |
| Spacing (Schott) | std (ddof = 1) of L1 nearest-neighbour distances within A | lower | ≥ 2 points; measures uniformity, not extent |
| Feasibility rate | feasible evaluations / all evaluations | higher | Always |

GD/IGD use the arithmetic mean of distances (`p = 1`). This matches pymoo 0.6 and differs from the
original root-mean-square form. All indicators except spacing are cross-checked against pymoo
0.6.2 in `tests/regression/test_metrics.py`.

## Proposed policy (`proposed-v1`)

1. **Approximation set:** the non-dominated subset of **all feasible evaluations** of a run, not
   only the final population. Every algorithm is then judged on everything it evaluated within the
   same budget, regardless of whether it keeps an archive.
2. **Normalization:** `(f − ideal) / (nadir − ideal)`, with ideal and nadir taken from the problem's
   **analytical reference front**, never from the runs being compared. This keeps the scale
   identical for every algorithm and seed.
3. **HV reference point:** `r = 1.1` in every normalized objective. Points beyond r contribute 0,
   which is reported, not hidden.
4. **HV ratio:** HV(A) / HV(Z) under the same policy, which makes problems comparable on one scale.
   The HV of Z is itself computed from a finite sample, so the ratio can slightly exceed 1.
5. **Reference-front density:** ZDT: 1000 points (ZDT3: non-dominated subset of 1000). DTLZ2:
   Das-Dennis with 12 partitions (91 points for M = 3). DTLZ7: non-dominated subset of a 60 × 60
   grid. The densities must be recorded with the results and must not change after `protocol-v1`.
6. **Missing values:** a run with no feasible evaluation reports `None` plus a `missing_reason` for
   every quality indicator. It never reports 0.

## Alternatives considered

- **Normalize with the per-problem bounds of all runs pooled:** depends on which algorithms are
  included, so adding an algorithm changes every score. Rejected.
- **Use the final population only:** penalizes algorithms that discard good points, which conflates
  archive strategy with search ability. This could be added as a secondary analysis.
- **Other reference-point offsets:** the offset affects how much weight boundary solutions get.
  **The 1.1 choice has to be checked against the literature review** (`docs/literature/`) before it
  is approved. It is not justified by any citation yet.

## Consequences

- Phase 04 computes these indicators from the stored `history.csv` of each run, so analysis never
  reruns experiments.
- Changing any item above after `protocol-v1` requires a dated amendment and a new `POLICY_VERSION`.
