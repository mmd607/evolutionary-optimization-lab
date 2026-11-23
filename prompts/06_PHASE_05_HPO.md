# Phase 05 — Machine Learning Hyperparameter Optimization

## Goal
Evaluate optimization methods on compact, real tabular ML tasks.

## Tasks
- Implement HPO search-space definitions for classification and regression.
- Use Wine Quality, Bank Marketing, and California Housing; Breast Cancer is smoke-test only.
- Use scikit-learn Pipelines to prevent preprocessing leakage.
- Compare Random Search, Optuna/Bayesian sampler, and suitable evolutionary methods.
- Define quality and cost objectives before running.
- Keep test data inaccessible to the optimizer.
- Record each trial, failure, parameters, validation metrics, time, and resource usage.

## Acceptance
At least three distinct tasks run through the same HPO interface; split logic and leakage protections are tested.
