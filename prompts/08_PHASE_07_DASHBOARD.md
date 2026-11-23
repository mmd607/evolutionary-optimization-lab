# Phase 07 — Dashboard

## Goal
Build a read-only Streamlit dashboard over existing artifacts.

## Pages
- Overview;
- Benchmark Explorer;
- Convergence Analysis;
- HPO Explorer;
- Statistical Comparison;
- Run Details.

## Rules
- No fabricated demo metrics.
- Clearly distinguish pilot/final runs.
- Warn on incomparable budgets.
- Do not execute expensive jobs on page load.
- Show empty states honestly.
- Keep UI separate from core package.

## Acceptance
Dashboard launches from documented command, reads actual artifact store, and has smoke tests for data-loading and key transformations.
