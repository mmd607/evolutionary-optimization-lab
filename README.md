# EvoOptLab — Evolutionary Optimization & Neural Hyperparameter Search

**Repository:** `evolutionary-optimization-lab`  
**Short name:** `EvoOptLab`  
**Level:** Advanced / research-oriented engineering  
**Primary language:** Python  
**Primary scope:** Multi-objective black-box optimization, evolutionary algorithms, and ML hyperparameter optimization.

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
python -m pip install -c requirements/constraints-py312.txt -e . --group dev
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

## 11. Project status

Progress is tracked per phase in [`docs/phase_status.md`](docs/phase_status.md). Foundation decisions,
pilot vs. final settings, open protocol questions, and deviations from the structure in §5 are recorded
in [`docs/decisions/0001-foundation-and-protocol-decisions.md`](docs/decisions/0001-foundation-and-protocol-decisions.md).
