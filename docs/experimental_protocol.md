# Experimental Protocol

## 1. General principles

All comparisons must be fair, repeatable, and auditable. The protocol is defined before full experiments begin. Any deviation must be logged with date, reason, and expected impact.

## 2. Experiment stages

### Stage A — correctness
- Verify objective functions against known reference values or trusted implementations.
- Verify feasibility handling and bounds.
- Test deterministic behavior under fixed seeds where supported.
- Run smoke tests with tiny populations and low budgets.

### Stage B — benchmark experiments
- Begin with ZDT1, ZDT2, ZDT3, DTLZ2, DTLZ7.
- Use a fixed evaluation budget per problem and algorithm.
- Use the same number of independent seeds per algorithm/problem.
- Tune algorithm parameters on a separate calibration set or through a declared protocol; do not tune on final test benchmarks and then report them as unseen.

### Stage C — HPO experiments
- Use at least 3 compact tabular tasks.
- Compare random search, Bayesian optimization, and evolutionary approaches.
- Use the same objective-evaluation budget where possible.
- If algorithms have different overheads, report both objective evaluations and wall-clock time.
- Use identical search spaces and preprocessing pipelines.
- Record failed trials and timeout behavior.

### Stage D — robustness and ablation
- Vary population size, mutation/crossover parameters, evaluation budget, and seed.
- Disable one component at a time for ablation.
- Test sensitivity to objective noise and constraints if in scope.

## 3. Minimum repeated runs

Recommended starting point:
- 20 independent seeds per benchmark/algorithm combination for core results, if compute permits.
- At least 10 independent seeds for expensive HPO tasks, with justification if fewer.
- Never hide a reduced run count. Report exact `n`.

A pilot can use 3–5 seeds to validate the pipeline, but pilot results must be labeled preliminary and not mixed silently with final results.

## 4. Fairness controls

- Equal objective-evaluation budget is the primary comparison control.
- Report wall-clock time separately.
- Use identical hardware and software environment where feasible.
- Record CPU/GPU, RAM, OS, Python and package versions.
- Keep algorithm-specific parameters documented.
- Do not give one algorithm more tuning effort without reporting it.
- Separate algorithm overhead from objective evaluation cost when possible.
- Use the same stopping criteria or explicitly justify differences.

## 5. Randomness and seeds

- Define a master seed and derive per-run seeds deterministically.
- Record seed, run ID, problem, algorithm, config hash, start/end time.
- Set seeds for Python, NumPy, and framework-specific generators.
- Note that GPU kernels and parallel execution may remain nondeterministic.
- Never overwrite prior run outputs; use unique run IDs.

## 6. HPO protocol

- Define search spaces before running experiments.
- Use identical preprocessing and model families across methods.
- Define objective metrics and direction clearly.
- Use nested CV only if justified by the research question and compute budget.
- Prefer repeated stratified/group/time-aware CV as appropriate.
- Use validation folds for search; hold out test set for final selected configurations.
- Record every trial, including failed and pruned trials.
- Report trial count, elapsed time, and resource limits.

## 7. Reproducibility artifacts

Every run should emit:
- `run_metadata.json`;
- `config.yaml` or serialized config;
- `metrics.json`;
- `history.csv` or equivalent;
- algorithm parameters;
- environment metadata;
- stdout/stderr logs;
- artifact paths for plots and Pareto fronts.

## 8. Experiment naming

Suggested:
`{problem}__{algorithm}__{budget}evals__seed-{seed}__{date}-{shortid}`

## 9. Pre-registration / freeze

Before final runs, commit:
- research questions and hypotheses;
- benchmark/task list;
- metrics;
- budgets and seeds;
- algorithm settings;
- statistical tests;
- exclusion criteria.

Tag this commit, e.g. `protocol-v1`. Changes after this tag require a protocol amendment.
