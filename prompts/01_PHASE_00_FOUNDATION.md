# Phase 00 — Foundation and Research Protocol

## Goal
Establish a safe, reproducible project foundation before implementing optimization algorithms.

## Tasks
1. Inspect current repository, Git branch/status, existing files, and user changes.
2. Create/verify package layout and `pyproject.toml`.
3. Configure Python version, dependency groups, Ruff, MyPy, Pytest, and coverage.
4. Add `.gitignore`, pre-commit config, Makefile, and CI workflow.
5. Add package entry point and minimal CLI.
6. Add configuration loading and validation.
7. Add structured logging.
8. Add artifact directory conventions and metadata schema.
9. Finalize research charter, research questions, provisional hypotheses, and literature review matrix.
10. Create a protocol decision record identifying pilot versus final settings.

## Acceptance criteria
- Clean install instructions work.
- `pytest`, Ruff, formatting check, and MyPy execute.
- CI workflow is syntactically valid and runs core checks.
- No raw datasets, secrets, caches, or generated bulky artifacts are tracked.
- Repository structure matches README or documented deviations.
- Research protocol has explicit unresolved decisions rather than invented facts.

## Stop gate
Do not implement algorithms until the user reviews the foundation and protocol.
