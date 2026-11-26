# ADR 0009 — Release-readiness review (Phase 08)

- **Status:** Review complete. **Not ready for a scientific release**: no final results exist. The
  engineering baseline (version 0.0.1) is reviewed, with two fixes, and its remaining blockers are
  listed below.
- **Date:** 2026-11-26
- **Phase:** 08 — Final quality and release-readiness review
- **Reviewed commit:** branch `phase/08-release-review`, from `origin/phase/07-dashboard` @
  `dd64d90`. Nothing was tagged, released, merged or published by this review.

## Decisions recorded

- **P1, licence: MIT** (owner decision, 2026-11-26). Added as `LICENSE`, and in `pyproject.toml`
  as the PEP 639 expression `license = "MIT"` with `license-files`; the build backend floor is now
  `hatchling >= 1.27`. The built wheel carries `License-Expression: MIT` and the licence file. The
  copyright line reads "The EvoOptLab authors" until P2 is decided. Datasets are not
  redistributed and keep their own licences.
- **P2, citation authors: still open.** The owner has not decided ("idk"). `CITATION.cff` is left
  unchanged and is **invalid** under CFF 1.2.0, which requires `authors`. This blocks any release.

## Checklist results

All checks were run locally on Windows with Python 3.12, from clean virtual environments, unless
stated otherwise. Each line states what was actually run.

| Item | Result | Evidence |
|---|---|---|
| Clean environment installation | PASS | Fresh venvs: (a) the core only, without the dashboard extra: `pip check` clean, **524 passed, 1 skipped** (the dashboard module), 98.0 % coverage; (b) core + `.[dashboard]`: 535 passed, 96.6 % coverage (Phase 07 validation); (c) wheel built with `pip wheel`: 63 files, all under `evooptlab/` and its dist-info (no tests, data or dashboard); the wheel installs from a fresh venv and runs the smoke study outside the repository (8/8 runs). |
| Tests, lint, formatting, type checks | PASS | Ruff lint and format, MyPy strict (115 files), Pytest with coverage. Re-run after the fixes below. |
| Algorithm invariants and budget accounting | PASS | `tests/algorithm_invariants` (71 tests) and `tests/unit/test_evaluator.py` (22 tests) pass. On the real pilots, `diagnose` reports `budget_exact` PASS: every run used exactly its budget (10 000 benchmark evaluations, 30 HPO trials). |
| Dataset provenance and licences | PASS, one item unverified | The UCI pages were re-read on 2026-11-26 and confirm "Creative Commons Attribution 4.0 International (CC BY 4.0)" for Breast Cancer Wisconsin (DOI 10.24432/C5DW2B), Wine Quality (10.24432/C56S3T) and Bank Marketing (10.24432/C5K306), matching `hpo/datasets.py`. **California Housing: licence not stated by the source and still unverified**; the scikit-learn page could not be fetched (connection reset, twice). Checksums are verified on every load (ADR 0006). |
| No leakage in HPO | PASS | `tests/leakage` (10 tests) pass: changing test labels or features leaves every search objective bit-identical, among other checks (ADR 0006). On the real HPO pilot, `diagnose` passes `test_evaluations` (one consistent evaluation per run). |
| Complete run metadata and seeds | PASS | Each of the 145 stored pilot runs (100 benchmark, 45 HPO) has a recorded git commit, a clean source tree, a config hash, a seed equal to its config, a run ID consistent with its metadata, `n_evaluations` equal to its budget and its history rows, Python, CPU and package versions: **0 problems**. `diagnose` on both pilots: all checks PASS (9 benchmark, 11 HPO). |
| Reproducible tables and figures | PASS after fix 1 | Two `evooptlab report` runs on each real pilot aggregate are **byte-identical** (23 files each). Before the fix, every SVG differed. A new test (`test_regenerated_reports_are_byte_identical`) guards this. |
| Verified citations and manuscript claims | PASS (vacuous for citations) | `audit-claims`: PASS, 20 claims, 0 citations, 0 value references. The literature matrix has **0 verified entries**, so the manuscript cites nothing and Related Work is pending. Whether a source supports its sentence remains a human review. |
| Dashboard uses real artifacts | PASS | Every page renders without error on the real benchmark pilot (100 runs) and HPO pilot (45 runs) through AppTest (Phase 07). The server starts on the real pilot root (`check_launch.py`, strengthened by fix 2). |
| No secrets or large data in Git | PASS | All 707 objects of every branch were scanned. Largest blob 17.8 KB. No dataset, model, environment or key file was ever committed (the only CSVs are the literature-matrix template and two small metadata tables). No secret pattern (keys, tokens, private keys, passwords) and no email address appears in history or in tracked files. Run artifacts and data are gitignored. |
| Known vulnerabilities in pinned dependencies | PASS | `pip-audit --strict` over all pins in `requirements/constraints-py312.txt`: "No known vulnerabilities found" (2026-11-26). |
| README quick start and reproduction guide | PASS (added) | README "Quick start" and `docs/reproduction_guide.md`, with only commands that exist in this version. The README layout section now states which planned items are not built. |
| Known limitations and future work | PASS (consolidated) | Below. |
| Citation metadata and licence | Licence PASS; **citation BLOCKED** | MIT licence added (P1). `CITATION.cff` is invalid until P2 is decided. |
| Python 3.11 and GitHub Actions | **NOT RUN** | No Python 3.11 interpreter is available locally, and `gh` is not authenticated. CI is configured for 3.11 and 3.12 on Ubuntu and 3.12 on Windows, but no run result has been inspected. The new dashboard pins resolve to Python 3.11 Linux wheels in a pip dry run. |

## Findings fixed in this phase

1. **SVG figures were not byte-reproducible.** Matplotlib assigns random SVG element ids unless
   `svg.hashsalt` is set. The figures module claimed byte-stable output, but only PDFs, tables and
   CSVs were stable. Fixed with a fixed salt, and tested.
2. **The dashboard launch check could report a broken app as healthy.** Streamlit's health
   endpoint answers before any page code runs. The audit hit an environment with a stale editable
   install: the server started, `evooptlab` could not be imported, and the check said "healthy".
   The check now imports the app's modules with the same interpreter first. It is documented as a
   server-start check; page rendering is covered by the AppTest tests.

## Release blockers

| # | Blocker | Needed for |
|---|---|---|
| B1 | **P2: citation authors.** `CITATION.cff` is invalid without `authors`, and the copyright holder in `LICENSE` is a placeholder. | Any release or tag |
| B2 | **CI never inspected.** Python 3.11 and the Ubuntu and Windows jobs are configured but no run result has been seen. | Any release or tag |
| B3 | **No final results.** Final runs wait on P3 (Wine Quality), P4 (splits), P5 (budgets, seeds), P8 (quality policy), P9 (frozen analysis plan) and P10 (tuning). Until then the manuscript has no results and must not be submitted. | Scientific release, manuscript |
| B4 | **Literature review not started.** Zero verified sources, so Related Work and any novelty statement are pending. | Manuscript |
| B5 | **California Housing licence** is unverified (not stated by StatLib or scikit-learn). Using it in a publication needs a decision. | Final HPO runs using it |

## Known limitations

- **Statistical power (ADR 0007).** Under the proposed Holm family of 30 tests per metric, n = 10
  paired replicates can never reach significance; at least 11 are needed. This interacts with P5
  and P9.
- **Quality policy (ADR 0003, P8).** The default DTLZ2 reference front under-represents the
  analytical hypervolume, so hypervolume ratios above one are possible.
- **HPO (ADR 0006).**
  - Per-trial fit time is not recorded, so quality against cost is per run only.
  - There are no per-trial timeouts and no parallel trials.
  - Multi-objective HPO indicators are not implemented.
  - Bank Marketing has test rows that duplicate training feature rows (P4).
- **Tuning (ADR 0004, P10).** Library defaults are used unless the tuning protocol is applied,
  which may favour some methods.
- **Dashboard (ADR 0008).**
  - The first view of a run with a very large non-dominated set takes seconds, because of the
    core's quadratic dominance check.
  - It shows one artifact root at a time.
  - It cannot launch experiments.
  - Rendering in a real browser is not tested.
- **Not built** (planned in the README layout): `api/`, `Dockerfile`, notebooks, technical
  report. The CLI replaces the planned `scripts/`.
- **Platforms.** Only Windows with Python 3.12 was exercised locally.

## Future work

1. Decide P2, confirm CI is green on all jobs, then tag a 0.1.0 engineering release, if the owner
   wants one.
2. Decide P3, P4, P5, P8, P9 and P10, freeze the analysis plan, and run the final studies.
3. Literature review into `docs/literature/literature_matrix.csv` (verified entries only), then
   related work.
4. Design the sensitivity and ablation study (RQ2), and decide on resource-aware HPO with fit time
   as a second objective (RQ3).
5. Faster non-dominated sorting in `evaluation/dominance.py`, so large fronts load quickly in the
   dashboard and in aggregation.
6. A container image (`Dockerfile`) and a technical report generated from the final artifacts.
