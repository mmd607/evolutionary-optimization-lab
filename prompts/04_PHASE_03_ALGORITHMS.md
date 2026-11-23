# Phase 03 — Optimization Algorithm Adapters

## Goal
Provide fair, interchangeable algorithm implementations/adapters.

## Required baselines
- Random Search;
- Genetic Algorithm;
- NSGA-II;
- Differential Evolution variant;
- Particle Swarm Optimization variant;
- Bayesian/Optuna sampler for appropriate HPO tasks.

## Tasks
- Document algorithm variants and valid problem domains.
- Map all methods to common evaluator and budget interface.
- Record parameter defaults and tuning protocol.
- Ensure bounds and constraint handling are explicit.
- Add algorithm invariant tests.
- Avoid implementing a custom algorithm unless correctness can be validated.

## Acceptance
Every baseline runs on at least one appropriate smoke problem, respects budgets, and produces compatible artifacts.
