# Phase 01 — Core Optimization Interfaces

## Goal
Implement the domain abstractions without coupling algorithms to storage, datasets, or dashboard code.

## Tasks
- Define `Problem`, `Algorithm`, `Evaluator`, `ExperimentConfig`, and `ExperimentRunner` interfaces.
- Prefer an ask/tell interface to centralize objective-evaluation accounting.
- Validate candidate dimensions, finite values, bounds, objective dimensions, and constraints.
- Implement deterministic seed derivation and metadata capture.
- Implement artifact storage with unique run IDs and no overwrite behavior.
- Add small synthetic test problems.

## Tests
- shape and bounds validation;
- evaluation budget never exceeded;
- objective counter correct;
- deterministic behavior under fixed seeds where applicable;
- invalid config fails early;
- run artifacts contain required metadata;
- existing artifact is never silently overwritten.

## Acceptance
All interfaces documented, typed, tested, and independent of UI.
