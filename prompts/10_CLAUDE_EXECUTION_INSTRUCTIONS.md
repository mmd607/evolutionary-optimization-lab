# Claude Code / Coding Agent Execution Instructions

You are given the EvoOptLab project kit. Treat it as the authoritative project specification.

## First action
Read `README.md`, all files in `docs/`, and `prompts/00_MASTER_AGENT_PROMPT.md`. Then inspect the actual repository and Git state.

## Execution
Execute one phase at a time in numerical order:
- Phase 00 Foundation
- Phase 01 Core Interfaces
- Phase 02 Benchmarks
- Phase 03 Algorithms
- Phase 04 Experiments
- Phase 05 HPO
- Phase 06 Analysis and Paper
- Phase 07 Dashboard
- Phase 08 Release Review

At each phase:
1. State the phase goal and implementation plan.
2. List files expected to change.
3. Identify risks and unresolved decisions.
4. Implement the smallest coherent increment.
5. Run tests and quality checks.
6. Report actual command outputs and results.
7. Update docs and phase status.
8. Stop and request explicit user review before proceeding.

## Git safety
- Never commit, push, merge, rebase, reset, clean, or delete branches unless the user explicitly asks.
- Do not change `main` or `dev` without explicit permission.
- Preserve user changes.
- No agent co-author trailers.

## Research safety
- Do not invent literature, citations, dataset sizes, licenses, metrics, or findings.
- Verify source details.
- Mark all unrun experiments as pending.
- Do not write final abstract/results until final experiments are complete.
- Keep the test set sealed from HPO.
- Report all protocol deviations.

## Initial request
Start with Phase 00 only. Do not begin Phase 01 until Phase 00 has been presented for review and explicitly approved.
