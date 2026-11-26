---
status: draft
---

# A Reproducible, Budget-Aware Evaluation of Evolutionary and Model-Based Optimization for Multi-Objective Benchmarks and Hyperparameter Search

*Provisional title (research charter). Authors: to be decided by the repository owner (P2).*

**DRAFT — RESULTS PENDING.** This draft contains no result. Final runs are blocked on open
protocol decisions (P3, P4, P5, P8, P9, P10; see `docs/decisions/`). Every number in the result
sections will be inserted from generated `values.json` files (`{{value:KEY}}`), never typed, and
`evooptlab audit-claims` checks this. Pilot outputs are preliminary and are not reported here.

## Abstract

DRAFT — RESULTS PENDING. Background, objective and methods are described in the sections
below. The findings, their practical implications and their limitations will be summarised here
after the final, pre-registered runs and analysis exist.

## 1. Introduction

Comparisons of optimization algorithms are hard to interpret when implementations, stopping
criteria, evaluation budgets, hardware or random seeds differ between the compared methods. In
hyperparameter optimization (HPO), predictive quality is also only one concern next to training
cost. This study compares selected evolutionary, swarm, model-based and random-search methods
under one experimental protocol with an equal objective-evaluation budget, on synthetic
multi-objective benchmarks and on tabular HPO tasks.

Research questions (provisional, from the research charter; the hypotheses are not results):

- RQ1: How do the selected methods compare under equal evaluation budgets?
- RQ2: How do algorithm hyperparameters affect convergence and diversity?
- RQ3: Can resource-aware HPO improve quality–cost trade-offs?
- RQ4: Do benchmark rankings transfer to HPO tasks?

Contributions, stated so that each can be checked:

- An open framework in which every algorithm runs behind one ask/tell interface and every
  objective evaluation passes through a single budgeted evaluator. <!-- claim: C01 -->
- A study runner whose artifacts are write-once and whose resume rules cannot rerun a failed
  run until it succeeds. <!-- claim: C04 -->
- An HPO pipeline whose search can be shown, by tests, not to depend on the held-out test data.
  <!-- claim: C07 -->
- An analysis pipeline whose statistical plan must be frozen before final results are analysed,
  and a mechanical audit that ties manuscript numbers to generated artifacts. <!-- claim: C10 -->

No new optimization algorithm is proposed.

## 2. Related Work

LITERATURE PENDING. The literature matrix (`docs/literature/literature_matrix.csv`) has no
verified entry yet, so this section cites nothing. It will cover evolutionary multi-objective
optimization, swarm methods, model-based optimization, HPO, and benchmarking methodology. Any
research gap stated in Section 1 remains a hypothesis until that review is done.

## 3. Problem Formulation

All objectives are minimized; quantities to maximize are negated or expressed as an error.
Decision vectors are real-valued and box-bounded, and an inequality constraint is satisfied when
its value is at most zero. <!-- claim: C12 -->

*Benchmarks.* ZDT1, ZDT2 and ZDT3 (two objectives) and DTLZ2 and DTLZ7 (three objectives in the
pilot configuration), with the dimensions stated in each study file. <!-- claim: C13 -->

*HPO.* Each HPO problem tunes one model family. Every algorithm searches the same unit cube,
which is decoded deterministically into hyperparameters (linear or log-uniform floats, integers
in equal-width bins, categorical values in equal-width bins). One trial is one complete k-fold
cross-validation on the training part and counts as one objective evaluation. The first objective
is the validation error: one minus mean macro-F1 for classification, or mean RMSE for regression.
<!-- claim: C14 -->

## 4. Methodology

*Budget accounting.* An evaluation batch that would exceed the remaining budget is rejected
before any evaluation, and a batch that fails inside the problem still counts as spent.
<!-- claim: C01 -->

*Algorithms.* Random search; GA, DE and PSO for single-objective problems; NSGA-II, GDE3 and
CMOPSO for multi-objective problems, all through pymoo 0.6.2 adapters whose default parameters
equal the library defaults (enforced by a test); and Optuna's TPE sampler as the model-based
method. <!-- claim: C05 --> <!-- claim: C06 --> Library defaults are used unless a study file
overrides them, and every parameter is recorded in each run's configuration.

*Quality indicators.* The approximation set is the non-dominated subset of all feasible
evaluations of a run. Objectives are normalized with the ideal and nadir points of the reference
front, and the hypervolume reference point is offset by 0.1 in normalized space. A run without a
feasible point has no indicator value rather than a value of zero. This policy is a proposal
awaiting the owner's decision (P8). <!-- claim: C03 -->

*HPO pipeline and leakage controls.*
- The train/test split depends only on the problem definition.
- The problem object holds training rows only.
- Preprocessing is a pipeline step fitted inside each training fold.
- The reported configuration is chosen by validation error only, and it is scored once on the
  test part in a separate step whose output can never be recomputed.

<!-- claim: C07 --> <!-- claim: C09 --> Dataset files are verified against recorded SHA-256
checksums before use. <!-- claim: C08 -->

*Statistical analysis.* Analyses follow `configs/analysis_plan.yaml`:
- Paired two-sided Wilcoxon signed-rank tests per problem, with replicates paired by their shared
  seed.
- Holm correction.
- The Vargha–Delaney A12 effect size.
- Percentile-bootstrap confidence intervals of the median.
- A Friedman test across problems.

The plan is a proposal (P9). Final-stage results are refused until the plan is frozen and
committed. <!-- claim: C10 -->

## 5. Experimental Setup

*Fairness controls.*
- An equal objective-evaluation budget for every algorithm on a problem.
- The same replicate seeds for every algorithm (common random numbers), and an interleaved
  execution order.
- Every incompatible algorithm–problem pair is rejected before any run starts.

<!-- claim: C02 --> Each run records its git commit, source-tree state, Python and package
versions, and CPU. <!-- claim: C11 --> Final budgets, seed counts, search spaces and population
sizes are open decisions (P5, P10). Hardware, budgets, seeds and parameter tables will be
generated from the final run artifacts.

*Datasets.* Breast Cancer Wisconsin (pipeline smoke test only), Bank Marketing and Wine Quality
(UCI, CC BY 4.0 as stated on the source pages) and California Housing (licence not stated by the
source). The data are not redistributed. <!-- claim: C08 -->

## 6. Results

DRAFT — RESULTS PENDING.

### RQ1: Comparison under equal budgets

Pending final benchmark runs. <!-- claim: R1 -->

### RQ2: Effect of algorithm hyperparameters

Pending; the sensitivity study has not been designed yet. <!-- claim: R2 -->

### RQ3: Quality–cost trade-offs in HPO

Pending; whether fit time becomes a second objective is an open decision. <!-- claim: R3 -->

### RQ4: Transfer from benchmarks to HPO

Pending final benchmark and HPO runs. <!-- claim: R4 -->

## 7. Discussion

DRAFT — RESULTS PENDING.

## 8. Ablation and Sensitivity Analysis

DRAFT — RESULTS PENDING. No ablation study is implemented yet.

## 9. Threats to Validity and Limitations

Known threats, independent of the outcome (results will add others):

- *Construct validity.* The hypervolume ratio depends on the reference front. The pilot found
  that the default DTLZ2 front under-represents the analytical hypervolume, so ratios above one
  are possible (ADR 0003, P8). <!-- claim: C15 -->
- *Internal validity.* Library defaults are used without tuning unless the tuning protocol (P10)
  is applied, which may favour some methods. Measured fit time is noisy, and in HPO it reflects
  the configurations an algorithm proposes as much as the algorithm itself. <!-- claim: C16 -->
- *External validity.* Five synthetic benchmarks and a small number of tabular tasks may not
  represent other problems; the breast-cancer task is a smoke test only.
- *Conclusion validity.* Small numbers of replicates limit the power of paired tests, and many
  pairwise comparisons require correction (Holm). Pilot runs are excluded from all conclusions.

## 10. Conclusion and Future Work

DRAFT — RESULTS PENDING.

## References

None yet. Only verified entries of the literature matrix may be cited.
