# Data directory

Raw/interim/processed data are intentionally excluded from Git. Use documented download and preparation scripts. Record source, license, version, checksum, file size, and preprocessing provenance for each dataset. Never redistribute data unless its license permits it.

## HPO datasets (Phase 05)

`python -m evooptlab data fetch TASK --data-dir data` downloads a catalogued dataset into
`data/raw/<task>/` and verifies its byte size and SHA-256 before writing it. Cached files are
re-verified on every load. `python -m evooptlab data info` prints the source, licence, citation,
checksum and cache status of every task. The catalogue, licences and preprocessing are documented
in `docs/decisions/0006-hpo-tasks-and-leakage-controls.md`. `breast_cancer_smoke` ships with
scikit-learn and needs no download.
