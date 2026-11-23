# Phase Plan and Review Gates

| Phase | Name | Main output | Gate |
|---|---|---|---|
| 00 | Foundation | package, tooling, protocol draft | user reviews foundation |
| 01 | Core interfaces | problem/algorithm/evaluator/runner | interface tests pass |
| 02 | Benchmarks | ZDT/DTLZ + metrics | reference tests pass |
| 03 | Algorithms | fair algorithm adapters | invariants pass |
| 04 | Experiments | reproducible benchmark runs | pilot reviewed |
| 05 | HPO | real tabular HPO tasks | leakage tests pass |
| 06 | Analysis & paper | stats, tables, figures, manuscript | claims audited |
| 07 | Dashboard | read-only experiment dashboard | artifact integration passes |
| 08 | Release review | clean install and full audit | explicit user approval |

## Suggested branch naming

- `phase/00-foundation`
- `phase/01-core-interfaces`
- `phase/02-benchmarks`
- `phase/03-algorithms`
- `phase/04-experiments`
- `phase/05-hpo`
- `phase/06-analysis-paper`
- `phase/07-dashboard`
- `phase/08-release-review`

Do not merge or push without explicit permission.
