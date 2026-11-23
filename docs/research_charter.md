# Research Charter

## Working title

**A Reproducible, Budget-Aware Evaluation of Evolutionary and Model-Based Optimization for Multi-Objective Benchmarks and Machine-Learning Hyperparameter Search**

The title is provisional and must be revised after the literature review and actual findings.

## Problem statement

Optimization algorithms are often compared using different implementations, stopping criteria, hardware, evaluation budgets, or random seeds. Such differences can make reported rankings difficult to interpret. In practical ML hyperparameter optimization, predictive quality is only one concern; training cost, inference latency, model size, and robustness may also matter.

EvoOptLab establishes a common experimental protocol to compare selected optimization methods under controlled budgets and to examine whether benchmark behavior transfers to practical HPO.

## Research gap: investigation plan

Investigate, do not assume, these possible gaps:

1. Inconsistent evaluation budgets and reporting conventions across algorithm comparisons.
2. Limited joint reporting of Pareto quality, diversity, evaluation cost, and run-to-run stability.
3. Weak evidence about whether synthetic multi-objective benchmark rankings predict practical HPO outcomes.
4. Limited reproducibility of resource-aware HPO comparisons under fixed compute budgets.

### Literature review requirements

Search primary papers, benchmark documentation, and reputable surveys. For each source record:
- full bibliographic metadata and DOI/URL;
- problem studied;
- algorithms and baselines;
- datasets/benchmarks;
- metrics;
- compute/evaluation budget;
- limitations acknowledged by authors;
- relevance to this project.

Use a literature matrix. Do not infer a research gap from abstracts alone. Read methods and limitations for the most relevant papers. Verify every citation from the publisher, DOI resolver, or official repository.

## Research questions and hypotheses

| ID | Research question | Example hypothesis (testable) |
|---|---|---|
| RQ1 | How do selected methods compare under equal evaluation budgets? | Rankings differ by benchmark family and objective count. |
| RQ2 | How do hyperparameters affect convergence and diversity? | Larger populations may improve diversity but consume budget faster. |
| RQ3 | Can resource-aware HPO improve quality-cost trade-offs? | Multi-objective search can identify useful accuracy-cost trade-offs. |
| RQ4 | Do benchmark rankings transfer to HPO tasks? | Transfer may be limited; synthetic benchmark performance alone is insufficient. |

Hypotheses are not conclusions. Keep them unchanged in the preregistered experiment plan unless a dated amendment explains why they changed.

## Baselines and comparison groups

At minimum:
- Random Search;
- a simple Genetic Algorithm;
- NSGA-II;
- Differential Evolution (single-objective and a suitable multi-objective variant where applicable);
- Particle Swarm Optimization (with a clearly identified variant);
- Bayesian Optimization / Optuna sampler for HPO.

Do not compare algorithms outside their valid problem setting without explaining the adaptation. For multi-objective tasks, use multi-objective variants or scalarization and report the scalarization method.

## Novelty and contribution rules

Potential contribution types:
- reproducible benchmark implementation;
- careful empirical comparison;
- analysis of budget and diversity trade-offs;
- practical HPO case study;
- new algorithmic component (only if actually designed and evaluated).

A well-executed empirical study is a valid engineering/research portfolio project. It must not be marketed as a novel algorithm unless that claim is substantiated.

## Threats to validity

- Benchmark selection bias.
- Hyperparameter tuning bias favoring one method.
- Unequal evaluation budgets.
- Hardware and software version differences.
- Random-seed variability.
- Data leakage in HPO tasks.
- Overfitting to benchmark functions.
- Incomplete reporting of failed runs.
- Multiple-comparison inflation.
- Implementation differences between library and custom algorithms.

Discuss these explicitly in the paper.

## Protocol status

*Added in Phase 00 (2026-11-23).*

- RQ1–RQ4 and the example hypotheses above are the **provisional draft** of the pre-registered plan.
  They are not results and have not been tested.
- The literature review has **not started**. The matrix is set up in
  `docs/literature/literature_matrix.csv` and has no entries. Until it is complete, the gaps listed
  above stay hypotheses.
- Open decisions that affect validity (budgets, seeds, algorithm variants, HV reference points,
  statistical tests, HPO task definitions) are tracked in
  `docs/decisions/0001-foundation-and-protocol-decisions.md`.
- The `protocol-v1` freeze (experimental protocol §9) happens only after those decisions are resolved
  and the owner has reviewed them.
