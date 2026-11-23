# Phase 02 — Benchmark Problems and Metrics

## Goal
Add trusted multi-objective benchmark problem definitions and metric calculations.

## Tasks
- Integrate a pinned `pymoo` version or implement only verified functions with reference checks.
- Start with ZDT1, ZDT2, ZDT3, DTLZ2, DTLZ7.
- Record bounds, variables, objectives, constraints, and reference-front provenance.
- Implement HV, IGD/IGD+, GD, feasibility rate, and diversity metrics as applicable.
- Document normalization and HV reference-point policy.
- Add reference-value and edge-case tests.

## Acceptance
Metric outputs match trusted references within declared tolerances; no metric is used outside its valid conditions.
