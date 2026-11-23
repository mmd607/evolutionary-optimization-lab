# Dataset and Benchmark Plan

## Principle

This project is primarily an optimization-method study, not a dataset-size competition. Most core multi-objective benchmarks are mathematical functions and require no external dataset. For HPO, choose compact, publicly accessible tabular datasets. Keep each downloaded dataset comfortably below 3 GB; exact size depends on source, format, and preprocessing, so verify before downloading.

## A. Mathematical benchmark functions

Use a recognized benchmark suite such as `pymoo` and pin its version. Record the exact problem name, objective count, variable count, bounds, constraints, and reference Pareto front source.

| Family | Suggested problems | Purpose | Data download |
|---|---|---|---|
| ZDT | ZDT1, ZDT2, ZDT3, ZDT4, ZDT6 | Foundational bi-objective tests | None |
| DTLZ | DTLZ1, DTLZ2, DTLZ3, DTLZ7 | Scalability and objective-count tests | None |
| WFG (optional) | WFG1, WFG2, WFG4 | More complex landscapes | None |
| Constrained (optional) | CTP family or supported constrained suite | Feasibility handling | None |

Start with ZDT1, ZDT2, ZDT3, DTLZ2, and DTLZ7. Expand only after the pipeline is stable.

## B. HPO datasets

Recommended compact tabular tasks:

| Dataset | Task | Source | Approximate size guidance | Notes |
|---|---|---|---|---|
| Breast Cancer Wisconsin (Diagnostic) | Binary classification | UCI / scikit-learn | Tiny | Suitable pipeline smoke test; not sufficient alone for final claims |
| Wine Quality | Classification or regression | UCI | Small | Define target and task before experiments |
| Bank Marketing | Classification | UCI | Small to moderate | Check categorical preprocessing and class imbalance |
| Adult / Census Income | Classification | UCI | Small | Check licensing and source version |
| California Housing | Regression | scikit-learn / source | Small | Regression HPO task |
| Bike Sharing | Regression | UCI | Small | Time-related features; split carefully if forecasting claims are made |

Official dataset pages should be cited in the repository. Do not assume a dataset's license permits redistribution. Download via scripts and store provenance.

### Recommended initial HPO suite

1. Breast Cancer Wisconsin — pipeline validation only.
2. Wine Quality — compact classification/regression case.
3. Bank Marketing — mixed-type classification.
4. California Housing — regression.

The final suite should contain at least 3 meaningfully different tasks, preferably classification and regression. The tiny smoke-test dataset must not dominate conclusions.

## C. HPO objective design

Possible objective vectors:

### Classification
- maximize validation macro-F1 (or minimize `1 - macro-F1`);
- minimize training time or a standardized compute-cost proxy;
- optionally minimize model size or inference latency.

### Regression
- minimize validation RMSE or MAE;
- minimize training time or inference latency.

Do not mix incomparable raw units without normalization or clear Pareto interpretation. If the objective is cost, define how it is measured and whether it is noisy.

## D. Dataset provenance record

For every dataset, create a record containing:
- dataset name and source URL;
- download date;
- version/release;
- license and citation;
- file names and sizes;
- row/column counts;
- target definition;
- preprocessing steps;
- checksum (SHA-256 preferred);
- train/validation/test split strategy;
- known limitations.

## E. Data splitting and leakage

For ordinary independent tabular tasks:
- create train/validation/test partitions with a fixed, recorded seed;
- stratify classification where appropriate;
- fit imputers, encoders, scalers, feature selection, and resampling only within training folds;
- use pipelines so cross-validation repeats preprocessing safely;
- reserve test data until final evaluation.

For grouped, temporal, or repeated-entity data:
- use group-aware or chronological splits;
- never randomly split records if this leaks entities or future information.

For HPO:
- optimize only against training folds / validation data;
- do not expose test metrics to the optimizer;
- evaluate the selected configuration on test once per prespecified final protocol.

## F. Download and storage policy

- Do not commit raw datasets.
- Provide `scripts/download_data.py` or dataset-specific download instructions.
- Add raw and processed data paths to `.gitignore`.
- Record source, license, and checksum.
- Keep a small synthetic fixture in tests.
- Verify file size before download and document how to reproduce preprocessing.
