# Literature review

This directory holds the working literature matrix for EvoOptLab. It follows
`docs/research_charter.md` (Literature review requirements) and
`prompts/11_LITERATURE_REVIEW_AGENT_PROMPT.md`.

**Current state (Phase 00):** the matrix structure is set and **contains no entries**. No source has
been reviewed or verified yet. The research gaps in the charter remain hypotheses.

## Files

- `literature_matrix.csv`: one row per source. The columns match `templates/literature_matrix.csv`.

## Column rules

| Column | Rule |
|---|---|
| `paper_id` | Short stable key, e.g. `deb2002nsga2`. |
| `authors`, `year`, `title`, `venue` | Copied from the publisher or DOI record, not from memory. |
| `doi_or_url` | DOI preferred; otherwise the official publisher or repository URL. |
| `problem`, `algorithms`, `benchmarks`, `metrics`, `budget_protocol` | Taken from the methods section, not the abstract. |
| `main_findings`, `limitations` | Quote or closely paraphrase. Note limitations the authors themselves acknowledge. |
| `relevance` | Which RQ (RQ1–RQ4) or design decision the source informs. |
| `verified` | `yes` only after the metadata has been checked against the DOI resolver or publisher; otherwise `no`. |

Never add a row for a source that has not been located and read. Never cite an unverified row in
the paper.
