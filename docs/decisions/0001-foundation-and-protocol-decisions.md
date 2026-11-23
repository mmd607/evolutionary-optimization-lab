# ADR 0001 — Foundation decisions, pilot vs. final settings, and open protocol questions

- **Status:** Proposed (awaiting owner review at the Phase 00 gate)
- **Date:** 2026-11-23
- **Phase:** 00 — Foundation

## Context

Phase 00 establishes tooling and a protocol draft before any algorithm is implemented. Several
choices that affect validity are not yet decided. This record makes them explicit instead of
silently picking values. Nothing here reports a result; no experiments have been run.

## Decisions taken in Phase 00

| # | Decision | Rationale |
|---|---|---|
| F1 | Python `>=3.11,<3.13`; development venv on 3.12.3. | Matches README (3.11/3.12). 3.13 is excluded until scientific deps are verified on it. |
| F2 | `src/` layout, hatchling build, PEP 735 dependency groups (`test`, `lint`, `dev`). | Prevents accidental imports from the working tree; groups keep runtime deps minimal. |
| F3 | Runtime deps limited to `pydantic` and `PyYAML` for now. | README: "do not blindly install every package". Numerical/ML deps arrive with the phases that need them. |
| F4 | Pinned versions stored as pip constraints in `requirements/constraints-py312.txt`. | `uv`/Poetry not available in the dev environment; constraints are tool-agnostic and cross-platform. |
| F5 | Ruff (lint + format), MyPy `strict` with the pydantic plugin, Pytest with branch coverage ≥ 85 %. | Required by `docs/reproducibility.md`. |
| F6 | Configs are validated by strict schemas (unknown keys rejected). Placeholder values such as `define_before_run` are accepted but reported; `--strict` rejects them. | Pilot work can proceed while open decisions stay visible; final runs must use `--strict`. |
| F7 | Artifacts live under `artifacts/experiments/{pilot,development,final}/<run_id>/`; never overwritten. | Protocol §3 and reproducibility doc: never mix pilot and final results; never overwrite outputs. |
| F8 | Run-metadata schema extends `templates/run_metadata.json` with `schema_version`, `outcome`, `failure_reason`, `config_hash`, `git_dirty`, `software.packages`. `status` keeps the template meaning (study stage: pilot / development / final). | Failed runs must be recorded; results must trace to an exact config and source tree. |
| F9 | Structured JSON-lines logging limited to the `evooptlab` logger hierarchy. | Machine-readable run logs without hijacking host-application logging. |
| F10 | Branch names follow the owner's GitHub workflow instructions (`phase/05-hyperparameter-optimization`, `phase/06-analysis-and-paper`), which differ from `docs/phase_plan.md` (`phase/05-hpo`, `phase/06-analysis-paper`). | The workflow instructions are the more recent owner directive. `docs/phase_plan.md` is left unchanged pending owner confirmation. |

## Pilot vs. final settings

| Setting | Pilot (current `configs/`) | Final (to be fixed before the `protocol-v1` tag) |
|---|---|---|
| Benchmark problems | ZDT1, ZDT2, ZDT3, DTLZ2, DTLZ7 | Same core set; expansion only after the pipeline is stable |
| Evaluation budget | 10 000 objective evaluations (all problems) | **Open (P5)** — set per problem after a compute estimate |
| Seeds (benchmarks) | 5 explicit seeds `[11, 23, 37, 41, 59]` | 20 independent seeds per problem/algorithm if compute permits (protocol §3) |
| Seeds (HPO) | — | ≥ 10 per task, with justification if fewer |
| HPO trial budget | `max_trials: 100`, `timeout_seconds: 7200` | **Open (P5)** |
| Labelling | `pilot: true`; artifacts under `pilot/` | Artifacts under `final/`; configs must pass `validate-config --strict` |

Pilot results are preliminary, must be labelled as such, and are never pooled with final results.

## Open decisions (owner input required)

| ID | Question | Where it shows up | Needed by |
|---|---|---|---|
| P1 | Which license should the repository use? | `pyproject.toml` has no license; no `LICENSE` file | Before any public release (Phase 08); ideally now |
| P2 | Who are the citation authors? CFF 1.2.0 requires `authors`. | `CITATION.cff` (left as authored) | Phase 08 |
| P3 | Wine Quality: classification or regression, and which target metric? | `configs/hpo_tasks.yaml` → `task_type`, `target_metric` placeholders | Phase 05 |
| P4 | Per-task split strategy (stratified / group / temporal)? | `configs/hpo_tasks.yaml` → `split.strategy: task_specific` | Phase 05 |
| P5 | Final evaluation budgets, seed counts and HPO trial limits? | `configs/benchmarks.yaml`, `configs/hpo_tasks.yaml` | Before final runs (Phase 04) |
| P6 | Seed policy: explicit seed list (benchmarks) vs. derivation from `master_seed` (experiments)? The two configs currently use different mechanisms. | `configs/benchmarks.yaml`, `configs/experiments.yaml` | Phase 01 (runner) |
| P7 | Exact multi-objective DE and PSO variants (e.g. which MODE / MOPSO). | `configs/experiments.yaml` → `differential_evolution_variant`, `particle_swarm_variant` | Phase 03 |
| P8 | Hypervolume reference points, reference-front sources and normalization. | `docs/metrics_and_statistics.md` | Phase 02 |
| P9 | Final statistical test plan (e.g. Friedman + Holm post-hoc, effect-size measure). | `docs/metrics_and_statistics.md` | Before inspecting final results |
| P10 | Calibration set used to tune algorithm parameters (must be separate from final benchmarks). | Protocol Stage B | Phase 03 |
| P11 | Confirm branch naming (F10). | `docs/phase_plan.md` | Phase 05 |

## Documented deviations from the README repository structure

Created in Phase 00 but not listed in the README: `src/evooptlab/config/`, `requirements/`,
`docs/schemas/`, `docs/literature/`, `docs/phase_status.md`, `.gitattributes`.

Listed in the README but intentionally deferred to the phase that needs them:

| Path | Deferred to |
|---|---|
| `src/evooptlab/{core,evaluation}/` | Phase 01 |
| `src/evooptlab/benchmarks/` | Phase 02 |
| `src/evooptlab/algorithms/` | Phase 03 |
| `scripts/`, `notebooks/` | Phase 04 |
| `src/evooptlab/hpo/` | Phase 05 |
| `src/evooptlab/{analysis,reporting}/`, `reports/`, `configs/reporting.yaml` | Phase 06 |
| `dashboard/`, `api/` (optional) | Phase 07 |
| `Dockerfile`, `LICENSE` (see P1) | Phase 08 |

Logging and environment capture live in `src/evooptlab/utils/`; artifact conventions live in
`src/evooptlab/storage/` (both match README sub-package names).

## Consequences

- Final runs are blocked by construction until P3–P5 are resolved, because `--strict` rejects
  placeholders.
- Each open decision is recorded here and in `docs/phase_status.md` until it is resolved by a
  dated amendment.
