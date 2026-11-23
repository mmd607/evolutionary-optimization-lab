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
