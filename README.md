# EvoOptLab — Evolutionary Optimization & Neural Hyperparameter Search

**Repository:** `evolutionary-optimization-lab`  
**Short name:** `EvoOptLab`  
**Level:** Advanced / research-oriented engineering  
**Primary language:** Python  
**Primary scope:** Multi-objective black-box optimization, evolutionary algorithms, and ML hyperparameter optimization.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install --upgrade "pip>=25.1"
python -m pip install -c requirements/constraints-py312.txt -e ".[dashboard]" --group dev
python -m pytest                                         # offline test suite
make smoke                                               # or the four commands in section 10
python -m streamlit run dashboard/app.py -- --root build/smoke
```

The full reproduction path (benchmarks, HPO, analysis, manuscript, dashboard) is in
[`docs/reproduction_guide.md`](docs/reproduction_guide.md). **Status:** version 0.0.1 has
pilot results only, and they are PRELIMINARY. Final runs wait on open protocol decisions (see
section 11). The code is MIT-licensed (`LICENSE`); datasets keep their own licences and are not
redistributed.

## 1. Project purpose

EvoOptLab is a reproducible experimental framework for implementing, comparing, and analyzing optimization algorithms on:
1. Standard multi-objective benchmark functions.
2. Constrained and computationally expensive optimization tasks.
3. Machine-learning hyperparameter optimization (HPO) tasks.

The project must be more than a collection of notebooks. It should provide reusable algorithms, controlled experiments, statistically defensible comparisons, machine-readable results, a technical research report, and an interactive dashboard.

## 2. Research framing

The project investigates the trade-offs among:
- solution quality / Pareto-front approximation;
- computational budget and number of objective evaluations;
- convergence speed;
- solution diversity;
- robustness across random seeds;
- practical downstream ML performance.

**Important:** The proposed research gap is a hypothesis to investigate, not a claim that no prior work exists. The agent must perform a literature review before making novelty claims.

### Proposed research questions

- **RQ1:** Under equal objective-evaluation budgets, how do NSGA-II, Differential Evolution, Genetic Algorithms, Particle Swarm Optimization, and Bayesian Optimization compare on selected benchmark problems?
- **RQ2:** How do population size, mutation/crossover settings, and search-budget allocation affect convergence, diversity, and robustness?
- **RQ3:** Does a resource-aware evaluation strategy improve the quality-cost trade-off in ML hyperparameter optimization?
- **RQ4:** Do rankings observed on synthetic benchmarks transfer to practical ML hyperparameter optimization tasks?

### Proposed contribution (to validate)

A reproducible, budget-aware comparison framework that evaluates multi-objective evolutionary and model-based optimization methods using common interfaces, fixed evaluation budgets, repeated seeds, quality/diversity metrics, and practical HPO case studies.

Do not claim a new optimization algorithm unless a genuinely new method is implemented and supported by a defensible comparison.

## 3. Scope and non-goals

### In scope
- Implementing baseline algorithms and/or wrapping well-maintained libraries through a common adapter.
- ZDT and DTLZ benchmark families, plus selected constrained problems.
- HPO tasks using small tabular datasets.
- Multi-objective optimization, including predictive score and computational cost.
- Repeated experiments, statistical analysis, visualizations, report generation.
- Optional FastAPI inference/experiment API and Streamlit dashboard.

### Out of scope
- Claiming state-of-the-art performance without broad, fair comparisons.
- Running unbounded experiments or downloading multi-gigabyte datasets by default.
- Comparing algorithms with unequal budgets without explicitly reporting the difference.
- Treating a single random seed as sufficient evidence.
- Using the test set for hyperparameter selection.

## 4. Suggested technology stack

- Python 3.11 or 3.12
- NumPy, SciPy, pandas, Polars (optional)
- scikit-learn
- pymoo (benchmark and algorithm reference implementation; verify versions)
- DEAP (optional evolutionary baseline)
- Optuna (HPO / sampler baseline)
- XGBoost / LightGBM / CatBoost (optional, only where appropriate)
- MLflow or a lightweight local experiment registry
- Matplotlib / Plotly
- Streamlit dashboard
- FastAPI (optional service layer)
- pytest, Ruff, MyPy
- Docker and GitHub Actions

Pin tested versions in the lock file. Do not blindly install every package listed above.

## 5. Repository structure

```text
evolutionary-optimization-lab/
├── configs/
│   ├── benchmarks.yaml
│   ├── experiments.yaml
│   ├── hpo_tasks.yaml
│   └── reporting.yaml
├── data/
│   ├── raw/                 # ignored by Git
│   ├── interim/             # ignored by Git
│   ├── processed/           # ignored by Git
│   └── README.md
├── docs/
│   ├── research_charter.md
│   ├── dataset_and_benchmarks.md
│   ├── experimental_protocol.md
│   ├── metrics_and_statistics.md
│   ├── paper_writing_guide.md
│   ├── tables_and_figures.md
│   ├── reproducibility.md
│   └── decisions/           # architecture decision records
├── notebooks/
│   ├── 01_benchmark_exploration.ipynb
│   ├── 02_algorithm_diagnostics.ipynb
│   └── 03_result_analysis.ipynb
├── reports/
│   ├── figures/
│   ├── tables/
│   ├── paper/
│   └── technical_report/
├── scripts/
│   ├── run_benchmarks.py
│   ├── run_hpo.py
│   ├── aggregate_results.py
│   └── generate_report_assets.py
├── src/evooptlab/
│   ├── algorithms/
│   ├── benchmarks/
│   ├── core/
│   ├── evaluation/
│   ├── hpo/
│   ├── analysis/
│   ├── reporting/
│   ├── storage/
│   └── utils/
├── dashboard/
├── api/                     # optional; do not build before core is stable
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── algorithm_invariants/
│   └── regression/
├── prompts/
├── .github/workflows/
├── .gitignore
├── .pre-commit-config.yaml
├── Dockerfile
├── Makefile
├── pyproject.toml
├── README.md
├── LICENSE
└── CITATION.cff
```

The layout above is the planned target. In version 0.0.1:
- `scripts/` and `notebooks/` are replaced by the `evooptlab` CLI (`evooptlab --help`);
- `api/` and the `Dockerfile` are not built;
- `reports/figures/`, `reports/tables/` and `reports/technical_report/` wait for final results.

`build/` is the gitignored output location of the `make` targets. The deviations are recorded in
`docs/decisions/0001-foundation-and-protocol-decisions.md` and
`docs/decisions/0009-release-review.md`.

## 6. Expected final deliverables

- A documented and installable Python package.
- Common algorithm interface and reproducible implementations/adapters.
- Benchmark suite and small HPO suite.
- Raw per-run results in CSV or Parquet plus metadata in JSON.
- Aggregated metrics and statistical comparisons.
- Publication-quality figures and tables generated from source results.
- Technical report and manuscript draft with verified citations.
- Streamlit dashboard.
- Tests, CI, environment lock, and reproducibility instructions.

## 7. Execution order

Follow the phase prompts in `prompts/` sequentially. Do not skip phase gates. A phase is not complete because code exists; it is complete only when acceptance criteria, tests, artifacts, and review notes are present.

## 8. Data and artifact policy

Never commit raw datasets, large model checkpoints, credentials, or local environment files. Commit download/preparation scripts, dataset provenance, checksums where practical, and instructions. Store generated experiment outputs in a documented local or external artifact location. Commit only small representative samples if licensing permits.

## 9. Research integrity

- Distinguish hypotheses, observations, and established facts.
- Do not fabricate data, metrics, citations, experiments, or claims.
- Never edit results manually to improve appearance.
- Report failed runs and deviations from protocol.
- Record all exclusions and their reasons.
- Do not write “significant” unless an appropriate statistical test supports it.
- Clearly label synthetic benchmark results versus real ML-task results.

## 10. Development

Requires Python 3.11 or 3.12 and pip ≥ 25.1 (for `--group`).

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
python -m pip install --upgrade "pip>=25.1"
python -m pip install -c requirements/constraints-py312.txt -e ".[dashboard]" --group dev
pre-commit install            # optional: run checks on every commit
```

Quality checks (CI runs the same commands; `make check` runs them all where `make` is available):

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest --cov
python -m evooptlab validate-config configs/*.yaml          # pilot: reports open decisions
python -m evooptlab validate-config --strict configs/*.yaml # final runs: open decisions are errors
```

Other CLI commands: `evooptlab version`, `evooptlab env` (environment metadata as JSON) and
`evooptlab schema run-metadata` (the JSON Schema committed at `docs/schemas/run_metadata.schema.json`).

Running an experiment matrix (study configs live in `configs/studies/`; `make smoke` runs the smoke
study):

```bash
python -m evooptlab plan configs/studies/smoke.yaml        # validate and list the matrix; runs nothing
python -m evooptlab run configs/studies/smoke.yaml         # artifacts under artifacts/experiments/pilot/
python -m evooptlab run configs/studies/smoke.yaml --resume  # continue; settled cells are skipped
python -m evooptlab diagnose configs/studies/smoke.yaml    # integrity, fairness and timing checks
python -m evooptlab aggregate configs/studies/smoke.yaml   # runs.csv, summary.csv, manifest.json
```

Pilot and development results are labelled preliminary. Final-stage studies refuse to run from a
dirty or unknown git tree. See `docs/decisions/0005-experiment-runner-and-fairness-checks.md`.

Hyperparameter optimization on tabular tasks (`make hpo-smoke` runs the HPO smoke study on the
bundled breast-cancer data; nothing is downloaded):

```bash
python -m evooptlab data info                                  # provenance, licence, checksum, cache status
python -m evooptlab data fetch bank_marketing california_housing  # verified download into data/raw/ (gitignored)
python -m evooptlab run configs/studies/hpo_pilot.yaml          # search sees cross-validation on training rows only
python -m evooptlab test-eval configs/studies/hpo_pilot.yaml    # score each selected configuration once on test data
python -m evooptlab diagnose configs/studies/hpo_pilot.yaml
python -m evooptlab aggregate configs/studies/hpo_pilot.yaml
```

Datasets are never committed or redistributed. The leakage controls and their tests are described
in `docs/decisions/0006-hpo-tasks-and-leakage-controls.md`.

Analysis, generated tables and figures, and the manuscript audit:

```bash
python -m evooptlab report artifacts/experiments/aggregates/pilot/<aggregate>   # stats, tables, figures, values.json
python -m evooptlab audit-claims reports/paper/manuscript.md                    # citations, numbers, claim evidence
python -m evooptlab render-paper reports/paper/manuscript.md --values <values.json> --output <file>
```

The statistical plan (`configs/analysis_plan.yaml`) is a proposal. Final-stage results are refused
until it is frozen and committed. See `docs/decisions/0007-analysis-reporting-and-claims-audit.md`.

Read-only dashboard over an artifact root (needs the `dashboard` extra; `make dashboard ROOT=...`):

```bash
python -m streamlit run dashboard/app.py -- --root artifacts/experiments   # http://localhost:8501
python dashboard/check_launch.py --root artifacts/experiments               # start, health-check, stop
```

It shows only stored artifacts: runs, aggregates, `evooptlab report` outputs and stored test
evaluations. It never writes or runs anything, labels pilot data PRELIMINARY, and warns about
mixed budgets and stale aggregates. The server binds to `localhost` (`.streamlit/config.toml`). See
`docs/decisions/0008-read-only-dashboard.md`.

## 11. Project status

Progress is tracked per phase in [`docs/phase_status.md`](docs/phase_status.md). Foundation decisions,
pilot vs. final settings, open protocol questions, and deviations from the structure in §5 are recorded
in [`docs/decisions/0001-foundation-and-protocol-decisions.md`](docs/decisions/0001-foundation-and-protocol-decisions.md).
