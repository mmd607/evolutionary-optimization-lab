# Reproducibility and Engineering Standards

## Code quality
- Use type hints for public functions and classes.
- Keep modules cohesive and avoid monolithic notebooks.
- Use Ruff for linting/formatting and MyPy (or an agreed strictness profile) for static typing.
- Use docstrings for public APIs and non-obvious algorithms.
- Keep notebooks for exploration; move reusable logic into `src/`.
- Avoid hidden global state.
- Validate configuration values early.
- Use structured logging.

## Testing
- Unit tests for objective functions, operators, metrics, constraints, and data utilities.
- Property/invariant tests: bounds respected, population size maintained, valid objective dimensions, feasible solutions handled.
- Determinism tests for fixed seeds where applicable.
- Integration tests for complete small runs.
- Regression tests for known benchmark values and metric behavior.
- API tests only if API exists.
- Tests must not require full datasets or GPU access.

## Git workflow
- `main` is protected and always stable.
- Create one branch per phase or feature, e.g. `phase/00-foundation`, `phase/01-benchmarks`.
- Do not merge to `main` or `dev`, push, publish releases, or rewrite remote history without explicit user approval.
- Preserve existing uncommitted changes.
- Never reset, clean, or overwrite user work.
- Do not add agent co-author trailers.
- Commit messages should describe the actual change.
- Keep generated data, caches, checkpoints, and secrets out of Git.

## Experiment management
- Every run receives a unique ID.
- Configs are versioned.
- Store environment and hardware metadata.
- Never overwrite result files.
- Separate pilot, development, and final experiments.
- Use a manifest to map run IDs to source commit hashes.

## Security and licensing
- Never hardcode credentials.
- Check dataset, package, and model licenses.
- Do not redistribute data unless license allows it.
- Pin dependencies and scan for known vulnerabilities as part of release preparation.
