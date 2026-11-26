# ADR 0006 — HPO tasks, held-out test evaluation and leakage controls

- **Status:** Accepted for the implementation. The values marked *proposal* (model family,
  search space, population sizes, split strategies, trial budget) still need owner decisions
  (P3, P4, P5, P10) before final runs.
- **Date:** 2026-11-25
- **Phase:** 05 — Hyperparameter optimization
- **Code:** `src/evooptlab/hpo/`, `src/evooptlab/algorithms/optuna_tpe.py`,
  `src/evooptlab/experiments/hpo_evaluation.py`, `configs/studies/hpo_*.yaml`
- **Gate tests:** `tests/leakage/test_hpo_leakage.py`

## Context

Stage C of the protocol compares random search, a model-based method and evolutionary methods
on at least three compact tabular tasks, with identical search spaces and preprocessing, an
equal trial budget, every trial recorded, validation folds for search and a held-out test part
for the selected configuration only. The Phase 05 gate is *leakage tests pass*.

## Decisions

### D1. Dependencies

`scikit-learn` (model family, splits, CV, the bundled breast-cancer data) and `optuna` (TPE) are
core dependencies, pinned in `requirements/constraints-py312.txt` (scikit-learn 1.9.1, optuna
5.1.0). HPO is part of the study, so making them optional would only add import branches. Both
support Python 3.11 and 3.12.

### D2. Dataset catalogue with verified downloads (`evooptlab.hpo.datasets`)

| Task | Source | Licence (as stated by the source, 2026-11-25) | Raw file | Rows | Note |
|---|---|---|---|---|---|
| `breast_cancer_smoke` | bundled with scikit-learn (UCI 17, DOI 10.24432/C5DW2B) | CC BY 4.0 | — (content SHA-256 `25e2eb7b…`) | 569 | smoke test only |
| `wine_quality` | UCI 186, DOI 10.24432/C56S3T | CC BY 4.0 | `wine+quality.zip`, 91 353 B, `3ed56667…` | 1 599 red / 4 898 white | P3 open |
| `bank_marketing` | UCI 222, DOI 10.24432/C5K306 | CC BY 4.0 | `bank+marketing.zip`, 1 023 843 B, `e0bf5f5d…` | 41 188 | see D3 |
| `california_housing` | StatLib via scikit-learn's figshare mirror | **not stated; unverified** | `cal_housing.tgz`, 441 963 B, `aaa5c9a6…` | 20 640 | checksum equals scikit-learn's own record |

- `evooptlab data fetch TASK` downloads into `<data_dir>/raw/<task>/` (gitignored). The file is
  checked against the recorded byte size and SHA-256 **before** it is written, with exclusive
  creation. A cached file is re-verified on every load, and a mismatch is an error.
- Archives are read in memory by exact member name. Nothing is extracted, so archive paths
  cannot escape the cache.
- Downloads send a generic `User-Agent` and no personal or project details.
- Data are never committed or redistributed. `evooptlab data info` prints provenance and cache
  status.

### D3. Task definitions

- **Breast cancer:** binary classification, pipeline smoke test only. It must not drive
  conclusions.
- **Wine Quality:** the loader supports `red`, `white` and `combined` (which adds `is_red`) as
  classification or regression on `quality`. The task type, target metric and variant are owner
  decision **P3**, so the task is not in the pilot.
- **Bank Marketing:** `bank-additional-full.csv`.
  - `duration` is **dropped**, because the source says it is known only after the call and
    should be discarded for a realistic predictive model (target leakage).
  - `unknown` is kept as its own category, as the source suggests.
  - Rows are ordered by date (May 2008 – Nov 2010), so a random split mixes periods. An
    `ordered` split (last rows held out) is available; the choice is **P4**.
- **California Housing:** the same features and target as
  `sklearn.datasets.fetch_california_housing`, so the target is in units of 100 000 USD.

Each task has a `loader_version`, recorded in every run's config hash together with the
dataset checksum.

### D4. One search space for every algorithm: the unit cube

An HPO problem is a `Problem` over `[0, 1]^d`, one coordinate per hyperparameter, decoded
deterministically:
- `float`: linear, or log-uniform when `log` is set.
- `int`: equal-width bins (log-width bins when `log` is set), so every value is reachable.
- `categorical`: equal-width bins.

Random search, the pymoo baselines and TPE therefore search exactly the same space, and a
trial's hyperparameters can always be recovered from `history.csv`. Trade-off: TPE treats
integer and categorical coordinates as continuous. It still benefits from log scaling, which
is applied in the decoder.

**One trial is one full k-fold cross-validation on the training part, and it counts as one
objective evaluation.** The equal-budget control (ADR 0005) therefore means an equal number of
trials.

### D5. Model family and search space (proposal, P10)

`hist_gradient_boosting` (`HistGradientBoostingClassifier`/`Regressor`):
- `early_stopping=False`, so the number of boosting rounds is exactly `max_iter` and no hidden
  validation split is drawn.
- A fixed `random_state` (`model_seed`), so the objective is a deterministic function of the
  hyperparameters.
- Categorical columns are ordinal-encoded **inside the pipeline** and passed as native
  categorical features, with unseen categories becoming missing values.

The pilot space is `learning_rate` [0.01, 0.3] log, `max_iter` [20, 300] log int,
`max_leaf_nodes` [4, 64] log int, `min_samples_leaf` [2, 100] log int and `l2_regularization`
[1e-4, 10] log. Only parameters in `TUNABLE` are accepted.

### D6. Objectives and failed trials

- `validation_error`: `1 - mean macro-F1` (classification) or mean RMSE (regression) over the
  folds. It is always the first objective and is the selection criterion.
- `fit_seconds` (optional second objective): total fit time over the folds. It is measured, so
  it is **noisy and not bit-reproducible**. Whether resource-aware, multi-objective HPO uses
  it, and how its quality is scored without a reference front, is open (see Consequences).
- **A failed trial is a result, not a crash.** If a fit or prediction raises, the trial is
  recorded with `g_0 = 1` (infeasible), and with the worst `validation_error`: 1 for macro-F1
  error, or the CV RMSE of the training-fold-mean predictor for regression. Successful trials
  have `g_0 = 0`. Algorithms see the constraint through their usual handling: feasibility-first
  in pymoo, `Trial.set_constraint` in Optuna.

### D7. Leakage controls (the gate)

1. **The test part never enters the problem.**
   - The split depends only on the data and `split.random_seed`, never on the run seed or the
     algorithm.
   - `HPOProblem` keeps copies of the training rows only and drops everything else after the
     split. Only audit aggregates survive: row counts, index digests, index overlap (always 0),
     and test rows whose features duplicate a training row.
2. **The search sees only CV on the training part**, with the same folds for every trial.
3. **Preprocessing is fitted per training fold**, as a pipeline step.
4. **Selection uses validation error only.** The rule is the lowest `f_0` among feasible trials,
   with ties going to the earliest evaluation.
5. **Test scoring is a separate, one-time step** (D8). Nothing from it reaches an algorithm.

`tests/leakage/test_hpo_leakage.py` attacks each path:
- no test row in any array the problem holds;
- **flipping test labels or replacing test features leaves every search objective
  bit-identical**, and leaves the selected trial unchanged;
- an instrumented encoder never sees a validation or test row, and never sees a category that
  exists only in test;
- the split is identical across seeds and algorithms;
- the test evaluation refits on exactly the training indices.

A stratified split is a function of every label, so it moves if the data change. The tamper
tests therefore use a label-independent (`ordered`) split. What pins a stratified split in
practice is the dataset checksum (D2).

### D8. Held-out test evaluation (`evooptlab test-eval STUDY`)

For each completed canonical run, the selected configuration is refitted on the full training
part and scored once on the test part. The result goes to
`<root>/test_evaluations/<stage>/<run_id>.json` with:
- the run's config hash, the selected evaluation and its validation error;
- the decoded hyperparameters, and the test score and error;
- the split digests and the dataset checksum;
- the evaluator's git state.

- The run directory is **never modified**. An existing evaluation is **never recomputed or
  overwritten**, so a test score cannot be re-rolled.
- Failed runs are not evaluated (ADR 0005: counted, not scored).
- Diagnostics add two checks for HPO studies:
  - `failed_trials`: WARN when trials failed.
  - `test_evaluations`: FAIL if an evaluation does not match its run (hash, or selected trial ≠
    validation-best) or is unreadable. A missing evaluation is WARN in pilot studies and FAIL
    in the final stage.
- `aggregate` reports, per run, the number of trials and failed trials, the selected trial, the
  best validation error, and the test score/error with hyperparameters. Per cell it reports
  descriptive statistics of validation error, test error, failed trials and wall-clock time.

### D9. Study integration

- A study is either all benchmark problems or all HPO problems.
- HPO problem entries carry the task, task type, metric, objectives, model, seed, search space,
  split and CV. All of it enters the run's config hash through the new
  `Problem.describe()` → `problem.details` hook. Analytic benchmarks describe nothing, so their
  config hashes are unchanged; a regression test pins one.
- `data_dir` (default `data`) is machine-specific and is **not** hashed; the dataset checksum
  is.
- `run_study` loads and verifies the data of every pending HPO problem **before** any run
  starts. A missing or corrupted dataset is therefore a study error, and not a run recorded as
  "failed", which resume would then refuse to repeat.

### D10. Model-based baseline: Optuna TPE (`optuna_tpe`)

This resolves the ADR 0004 deferral.
- It is sequential (one candidate per `ask`), valid for any number of objectives, with
  constraints passed through `Trial.set_constraint`.
- The seed is drawn from the run's algorithm RNG.
- `n_startup_trials=10`, `n_ei_candidates=24`, `multivariate=True`, `group=False` and
  `constant_liar=True` are passed explicitly and recorded. They equal Optuna 5.1's defaults.
- The other TPE settings are deprecated as constructor arguments in Optuna 5.x (passing them
  warns) and stay at the defaults of the recorded `implementation` version.
- It passes the same invariant suite as every other algorithm: exact budget, bounds,
  determinism, recorded parameters, constraints and state-dict resume.

## Not implemented / limitations

- **No per-trial timeout.** Only the run-level `timeout_seconds` applies; a single runaway fit
  cannot be interrupted in-process.
- Trials run sequentially (`n_jobs` is still unused, ADR 0005 D10). scikit-learn's histogram
  boosting uses all CPU cores inside a fit, so wall-clock time depends on the machine.
- Nested CV is not used. The protocol allows it only if justified, and the held-out test part
  already separates selection from reporting.
- Multi-objective HPO quality (hypervolume without a reference front) is not computed;
  aggregation reports the selected trial only.
- `docs/dataset_and_benchmarks.md` suggests a `scripts/download_data.py`. The packaged
  `evooptlab data fetch` command replaces it, so that downloads share the catalogue's checksums
  and tests.

## Consequences and open decisions

- **P3:** Wine Quality task type, target metric and variant.
- **P4:** split strategies. In particular, whether `bank_marketing` should use the `ordered`
  (temporal) split. Also whether test rows that duplicate training feature rows are acceptable;
  see the pilot findings.
- **P5:** final trial budget and seeds. The protocol asks for at least 10 seeds per HPO task;
  the pilot projection informs the compute cost.
- **P10:** model family, search space and per-algorithm population sizes. The pilot sizes (10)
  are proposals. Library defaults of 100 would make a 100-trial budget a single generation.
- Whether `fit_seconds` becomes a second objective (resource-aware HPO, RQ3), and how its
  multi-objective quality is scored (linked to P8).
- `configs/hpo_tasks.yaml` is unchanged. Its placeholders (P3, P4) still fail
  `validate-config --strict` on purpose.

## Pilot findings (2026-11-25, `hpo_pilot`, preliminary)

The pilot ran from a clean worktree at commit `3a58ab7`:
- 3 tasks (breast cancer, bank marketing, California housing) × 5 algorithms (`random_search`,
  `ga`, `de`, `pso`, `optuna_tpe`) × 3 seeds × 30 trials;
- data fetched with `evooptlab data fetch`, every checksum verified;
- local Windows CPU, sequential.

The results:

1. **The pipeline and the controls work end to end.** 45/45 runs completed with 0 failed
   trials, and all 45 selected configurations were scored once on the test part. All 11
   diagnostics passed: one commit, a clean tree, uniform software, and every test evaluation
   consistent with its run's validation-best trial. The runs took 85 minutes of wall-clock
   time in total (sum over runs), and the test evaluation took 52 s.
2. **Per-trial cost (P5).** These are medians per trial, i.e. one 5-fold CV:

   | Task | Median per trial |
   |---|---|
   | breast cancer | 0.4–0.6 s |
   | bank marketing | 2.2–3.5 s |
   | California housing | 1.4–4.6 s |

   The linear projection for 100 trials × 10 seeds over these 15 cells is about **8.6 h**
   sequential. It is built from medians, and the pilot's actual total was about 1.8 times its
   median-based sum (5 084 s versus 2 784 s), so budget for more.
3. **Wall-clock time differs between algorithms because of what they choose, not their
   overhead.** Algorithm overhead was ≤ 0.6 % of wall-clock time everywhere. The spread (for
   example DE 4.6 s/trial versus random search 1.4 s/trial on California housing) comes from the
   costs of the configurations each method proposes, such as large `max_iter`. HPO wall-clock
   comparisons therefore measure the chosen models as much as the optimizer, and the paper
   should report them that way (RQ3).
4. **Test rows duplicating training feature rows (P4).** These are counted by `HPOProblem.audit`
   with the pilot split: 0 of 114 for breast cancer, 0 of 4 128 for California housing, and
   **644 of 8 238 for bank marketing**. For Wine Quality, found in an earlier one-off check of
   the red variant with a random split, the count is **77 of 320**. Both datasets contain
   exact-duplicate feature rows. Whether to deduplicate before splitting is part of P4.
5. **Preliminary numbers (n = 3, 30 trials; a pipeline check, NOT a result).**
   - Median test error: breast cancer (1 − macro-F1) 0.028–0.037, bank marketing
     (1 − macro-F1) 0.343–0.348, California housing (RMSE, ×100 000 USD) 0.449–0.456.
   - The differences between algorithms are within the spread of three seeds. On breast cancer
     they are also below the resolution of a 114-row test set. No ranking can be read from
     them.
