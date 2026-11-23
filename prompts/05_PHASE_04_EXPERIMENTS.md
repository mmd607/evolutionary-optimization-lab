# Phase 04 — Benchmark Experiment Runner

## Goal
Run controlled, repeatable benchmark experiments.

## Tasks
- Build config-driven matrix of problems, algorithms, budgets, and seeds.
- Support pilot and final experiment labels.
- Record objective evaluation count and wall-clock time.
- Persist complete per-run histories and metadata.
- Add resume behavior only if it cannot corrupt or overwrite artifacts.
- Add aggregate-results command.
- Produce pilot diagnostics before full-scale runs.

## Acceptance
A clean command can run a small matrix end-to-end; artifacts are immutable and reproducible; fairness checks are documented.
