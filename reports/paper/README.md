# Manuscript

- `manuscript.md`: the draft (front matter `status: draft`). It contains **no results**; final
  runs are blocked on open protocol decisions (see `docs/phase_status.md`).
- `claim_evidence.csv`: the claim-evidence matrix. Every `<!-- claim: ID -->` marker in the
  manuscript maps to evidence that exists: code, a test, an ADR, a config, a generated value or
  a verified literature entry. Rows that are `pending` have no evidence yet.

Rules, checked by `python -m evooptlab audit-claims reports/paper/manuscript.md` (also in CI):

- Result numbers are written as `{{value:KEY}}` and come from `values.json` files that
  `evooptlab report` generates; typed numbers in result sections fail the audit.
- Citations are `[@key]` and must be rows of `docs/literature/literature_matrix.csv` with
  `verified = yes`.
- Unsupported superlatives fail the audit, and so does "significant" without the corrected
  p-value on the same line.
- A final manuscript may not contain pending claims, unresolved or preliminary values, or
  "RESULTS PENDING".

`python -m evooptlab render-paper manuscript.md --values .../values.json --output OUT.md` fills
in the values. Whether a cited source supports its sentence is not machine-checkable and needs
human review. See `docs/decisions/0007-analysis-reporting-and-claims-audit.md`.
