# Architecture and Core Interfaces

## Design goals
- Algorithms are interchangeable behind a common interface.
- Objective functions are independent of algorithms.
- Evaluators own budget accounting and metric computation.
- Experiment runners handle seeds, configs, logging, and persistence.
- Analysis/reporting consumes saved artifacts and never silently reruns experiments.

## Core conceptual interfaces

### Problem
Fields:
- `n_variables`
- `n_objectives`
- `lower_bounds`
- `upper_bounds`
- `constraints` (optional)
- `evaluate(decision_vector) -> objective_vector`

### Algorithm
Operations:
- `initialize(problem, config, rng)`
- `ask() -> candidate_solutions`
- `tell(candidates, objective_values)`
- `state_dict()`
- `load_state_dict(state)`

An ask/tell interface is recommended because it supports consistent evaluation-budget accounting and expensive objectives.

### Evaluator
Responsibilities:
- validate candidate shape and bounds;
- count objective evaluations;
- handle constraints;
- time evaluations;
- record failures;
- calculate or delegate metrics.

### ExperimentRunner
Responsibilities:
- load validated configuration;
- set seed;
- instantiate problem and algorithm;
- execute until budget or stopping rule;
- persist immutable artifacts and metadata.

### HPOObjective
Responsibilities:
- define search space;
- build preprocessing/model pipeline inside CV;
- evaluate only on permitted folds;
- record trial metrics, cost, failures, and parameters.

## Separation of concerns
Do not make algorithm classes read datasets, write dashboards, or generate papers. Keep these responsibilities in their own modules.

## Recommended source modules

- `core/problem.py`
- `core/algorithm.py`
- `core/evaluator.py`
- `core/experiment.py`
- `algorithms/nsga2.py`
- `algorithms/genetic_algorithm.py`
- `algorithms/differential_evolution.py`
- `algorithms/particle_swarm.py`
- `algorithms/random_search.py`
- `algorithms/bayesian.py`
- `benchmarks/zdt.py`
- `benchmarks/dtlz.py`
- `hpo/search_spaces.py`
- `hpo/objectives.py`
- `evaluation/metrics.py`
- `evaluation/statistics.py`
- `storage/artifact_store.py`
- `analysis/aggregate.py`
- `reporting/tables.py`
- `reporting/figures.py`

Names are proposed; adjust consistently after architecture review.

## Implemented interfaces (Phase 01)

*Added 2026-11-23. The contracts are recorded in `docs/decisions/0002-core-interface-contracts.md`.*

| Concept | Module | Key API |
|---|---|---|
| Problem | `core/problem.py` | `ProblemSpec` (bounds, `n_objectives`, `n_constraints`, `validate_candidates`), `Problem.evaluate_batch(X) -> ProblemOutput` |
| Algorithm | `core/algorithm.py` | `parameters()`, `initialize(spec, rng)`, `ask(max_candidates)`, `tell(result)`, `state_dict()`, `load_state_dict()`, `supports(spec)` |
| Evaluator | `core/evaluator.py` | `Evaluator(problem, budget).evaluate(X) -> EvaluationResult`; `n_evaluations`, `n_failed_evaluations`, `remaining`, `evaluation_seconds` |
| ExperimentRunner | `core/experiment.py` | `ExperimentRunner(layout).run(problem, algorithm, RunSpec(stage, seed, budget, timeout_seconds))` |
| ExperimentConfig | `config/schemas.py` | Validated YAML schemas. Study configs map to `RunSpec`s in `experiments/` (Phase 04). |
| Seeds | `core/seeding.py` | `derive_seed`, `derive_run_seeds`, `make_rng` |
| Artifacts | `storage/` | `ArtifactLayout`, `RunMetadata`, run IDs per protocol §8 |
| Synthetic test problems | `benchmarks/synthetic.py` | `Sphere`, `TwoSpheres`, `ConstrainedSphere` (framework tests only) |

Deviation from the module list above: `config/` (Phase 00) holds the validated `ExperimentConfig`.
`core/experiment.py` defines `RunSpec` for a single run.

## Experiment matrices (Phase 04)

*Added 2026-11-25. Decisions and fairness checks are recorded in
`docs/decisions/0005-experiment-runner-and-fairness-checks.md`.*

| Concept | Module | Key API |
|---|---|---|
| Study config | `config/schemas.py` | `StudyConfig`: problems × algorithms (+ parameters) × seeds (`explicit` / `derived`) at one budget and stage; files in `configs/studies/` |
| Matrix | `experiments/matrix.py` | `build_matrix(study) -> [RunCell]` (validated, paired seeds, interleaved order), `cell_config_hash` |
| Study runner | `experiments/study.py` | `run_study(study, layout, resume=...)`: one `ExperimentRunner.run` per unsettled cell; never overwrites |
| Stored runs | `experiments/records.py` | `scan_stage(layout, stage)`: read-only view of a stage's run directories |
| Diagnostics | `experiments/diagnostics.py` | `collect_study`, `diagnose -> DiagnosticsReport` (PASS / WARN / FAIL checks, timing), `projected_seconds` |
| Aggregation | `experiments/aggregate.py` | `write_aggregate`: `runs.csv`, `summary.csv`, `manifest.json` in a new directory |
| CLI | `cli.py` | `evooptlab plan / run [--resume] / diagnose / aggregate STUDY [--root DIR]` |

Data flow: `StudyConfig -> build_matrix -> run_study -> artifacts/experiments/<stage>/<run_id>/`
`-> collect_study -> diagnose -> write_aggregate -> artifacts/experiments/aggregates/<stage>/...`.
Analysis reads only stored artifacts, never in-memory run state.

## HPO tasks (Phase 05)

*Added 2026-11-25. Decisions and leakage controls are recorded in
`docs/decisions/0006-hpo-tasks-and-leakage-controls.md`.* The `HPOObjective` concept above is
implemented as an ordinary `Problem`, so HPO runs reuse the runner, studies, resume, diagnostics
and aggregation unchanged.

| Concept | Module | Key API |
|---|---|---|
| Datasets | `hpo/datasets.py` | `CATALOG` (provenance, licence, checksum), `fetch` (verified download), `load` (verified parse) |
| Search space | `hpo/search_space.py` | `SearchSpace.decode(u)`: unit cube -> hyperparameters (float/int/categorical, log) |
| Model family | `hpo/models.py` | `build_model`: preprocessing + estimator pipeline, fitted per training fold |
| HPO problem | `hpo/problem.py` | `HPOProblem` (CV error on training rows only), `select_trial`, `evaluate_on_test` |
| Model-based baseline | `algorithms/optuna_tpe.py` | `OptunaTPE` (`optuna_tpe`): Optuna TPE behind ask/tell |
| Test evaluation | `experiments/hpo_evaluation.py` | `evaluate_study_on_test` -> `<root>/test_evaluations/<stage>/<run_id>.json` (write-once) |
| CLI | `cli.py` | `evooptlab data fetch / info`, `evooptlab test-eval STUDY` |

Data flow: `data fetch -> data/raw/<task>/` (verified) `-> run_study` (data prepared before any
run; the problem keeps training rows only) `-> test-eval` (selected trial refitted on training
rows, scored once on test) `-> diagnose -> aggregate`. The test part is reachable only through
`evaluate_on_test`, which no algorithm or problem calls.
