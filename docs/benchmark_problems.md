# Benchmark problem provenance

The core suite, as implemented in `src/evooptlab/benchmarks/` (Phase 02). All objectives are
minimized, `x ∈ [0, 1]^n`, and none of these problems has constraints.

| Problem | n (vars) | M (objs) | Constraints | Pareto-optimal set | Front shape | Reference front construction |
|---|---|---|---|---|---|---|
| ZDT1 | 30 | 2 | none | x₁ ∈ [0, 1], x₂..ₙ = 0 | convex, `f₂ = 1 − √f₁` | 1000 evenly spaced f₁ values |
| ZDT2 | 30 | 2 | none | same | concave, `f₂ = 1 − f₁²` | 1000 evenly spaced f₁ values |
| ZDT3 | 30 | 2 | none | same | disconnected (5 segments) | non-dominated subset of 1000 samples of `f₂ = 1 − √f₁ − f₁ sin(10πf₁)` |
| DTLZ2 | 12 (k = 10) | 3 | none | x_M = 0.5 | unit-sphere octant | Das-Dennis directions (12 partitions, 91 points), normalized to unit length |
| DTLZ7 | 22 (k = 20) | 3 | none | x_M = 0 | disconnected (4 regions for M = 3) | non-dominated subset of a 60 × 60 grid of the g = 1 surface |

Dimensions match `configs/benchmarks.yaml`. `evooptlab.benchmarks.registry.build_suite` fails if
they do not.

## Verification

| Check | Where |
|---|---|
| Points on the Pareto-optimal set land exactly on the analytical front (tolerance 1e-12) | `tests/regression/test_benchmark_problems.py::TestAnalytical` |
| ZDT3 front has exactly five disconnected segments | same |
| Objective values equal pymoo 0.6.2 for 500 random inputs per problem (rtol = atol = 1e-12) | `test_objectives_match_pymoo` |
| Reference fronts agree with pymoo's `pareto_front()` (ZDT: within 1e-3; DTLZ2: exact) | `test_zdt_fronts_match_pymoo`, `test_dtlz2_front_matches_pymoo` |
| HV of the reference fronts converges to the analytical values (ZDT1: 2/3; DTLZ2: 1 − π/6) | `tests/regression/test_metrics.py` |

## Sources (to verify)

The citations below are recorded **unverified**. They must be checked against the DOI or publisher
record and entered in `docs/literature/literature_matrix.csv` before they appear in any report.

- ZDT: E. Zitzler, K. Deb, L. Thiele, "Comparison of Multiobjective Evolutionary Algorithms:
  Empirical Results", *Evolutionary Computation*, 8(2), 2000.
- DTLZ: K. Deb, L. Thiele, M. Laumanns, E. Zitzler, "Scalable Multi-Objective Optimization Test
  Problems", *Proc. IEEE Congress on Evolutionary Computation (CEC)*, 2002.
- Das-Dennis directions: I. Das, J. E. Dennis, "Normal-Boundary Intersection", *SIAM J. Optim.*,
  1998.
- Reference implementation used for cross-checks: pymoo 0.6.2 (pinned in the `test` dependency
  group).
