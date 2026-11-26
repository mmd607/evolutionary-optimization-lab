# ADR 0007 — Statistical analysis, generated reporting and the claims audit

- **Status:** Accepted for the implementation. The analysis plan itself (P9) is a **proposal**
  until the owner freezes it.
- **Date:** 2026-11-26
- **Phase:** 06 — Analysis and paper
- **Code:** `src/evooptlab/analysis/`, `src/evooptlab/reporting/`, `configs/analysis_plan.yaml`,
  `configs/reporting.yaml`, `reports/paper/`

## Context

Phase 06 has to turn final, verified run artifacts into reproducible statistics, tables,
figures and an honest manuscript whose claims are audited. **No final artifacts exist.** Final
runs are blocked on owner decisions:
- P3, P4: HPO tasks;
- P5: budgets and seeds;
- P8: quality policy;
- P9: test plan;
- P10: tuning.

This phase therefore builds and tests the whole pipeline and adds the guards that keep
preliminary numbers from being presented as results. It does not report any result.

## Decisions

### D1. The analysis plan is a config file with a pre-registration guard (P9)

`configs/analysis_plan.yaml` declares the following.
- The primary and secondary metrics, with their directions. Benchmarks: `hypervolume_ratio`
  (primary) and `igd_plus`. HPO: `test_error` (primary) and `best_validation_error`.
- The per-problem test: a paired two-sided Wilcoxon signed-rank test with Holm correction and
  the Vargha–Delaney A12 effect size, plus the Holm family.
- The across-problem test: Friedman on per-problem medians, with a Holm-corrected Wilcoxon
  post-hoc.
- Percentile-bootstrap confidence intervals of the median (fixed seed).
- `min_replicates` and the missing-value rule (pairwise complete).

A plan with `status: proposal` may analyse pilot and development aggregates only, and every
output is labelled PRELIMINARY. A final-stage aggregate is refused unless the plan is
`status: frozen` and the source tree is committed and clean. The analysis records the plan's
SHA-256, so the plan cannot be chosen after the final results are seen (protocol §9).

**Pairing is justified and checked.** All algorithms of a problem run on the same replicate seeds
(ADR 0005 D2). The analysis verifies the recorded seeds before pairing and refuses otherwise.

### D2. Statistics are thin, tested layers over scipy (`analysis/stats.py`)

- Wilcoxon and Friedman come from `scipy.stats` and are tested to equality.
- A12 is closed-form, and tested equal to `U / (nm)` of the Mann–Whitney statistic.
- Holm is checked against hand-computed step-down values.
- The bootstrap is a seeded percentile bootstrap.
- Degenerate cases (no pairs, all-zero differences, all ties, fewer than 3 algorithms) are
  reported as "not run" with a reason, never as p = 1 or p = 0.
- A12 magnitude labels are not assigned. The usual thresholds come from the literature, and no
  source is verified in `docs/literature` yet.

### D3. Everything is generated from the aggregate (`evooptlab report`)

`evooptlab report AGGREGATE_DIR` writes the following into a new directory:
- `analysis.json`, `descriptive.csv`, `pairwise.csv` and `across_problems.csv`, at full
  precision;
- `values.json`;
- Markdown and LaTeX tables;
- figures as SVG and PDF, each with the CSV of exactly what it plots;
- a README.

Its inputs are the aggregate (ADR 0005), the stored histories, the plan and the reporting
config, so every asset can be regenerated.
- **Tables:** the direction of every metric (↑/↓) and `n / runs` are shown; failed runs are
  counted; missing values are an em dash with a note, never zero. Nothing is bolded, because
  "best" is a claim that needs the test next to it.
- **Figures:**
  - per-problem box plots with every replicate drawn as a point;
  - anytime curves: IGD+ for benchmarks, best-so-far validation error for HPO, as the median
    with an interquartile band;
  - Okabe–Ito colours with distinct markers and line styles, readable in greyscale;
  - PRELIMINARY in the title when applicable.
- **Benchmark IGD+ curves are computed incrementally**, using the running minimum per reference
  point. A test checks that the final checkpoint equals the aggregated `igd_plus` to 1e-12.

### D4. The manuscript never contains typed results (`evooptlab audit-claims`)

`reports/paper/manuscript.md` refers to results only through `{{value:KEY}}`, which is resolved
from `values.json` by `evooptlab render-paper`. The audit enforces the following. It runs in CI
and as a test:
- No typed numbers in result sections (Abstract, Results, Discussion, Ablation, Conclusion).
  Structural references (Table 2, RQ1, P8, ADR 0005) are allowed.
- Citations `[@key]` must be `verified = yes` rows of the literature matrix.
- Every `<!-- claim: ID -->` has a row in `claim_evidence.csv` whose evidence exists (a
  repository path, a generated value, or a verified source). Rows marked `pending` have none yet.
- No unsupported superlatives. "significant" is allowed only next to the corrected p-value.
- A draft with pending claims says "DRAFT — RESULTS PENDING". A final manuscript has no pending
  claim, no unresolved or preliminary value, and no "RESULTS PENDING".

What the audit cannot check, whether a source supports its sentence, is reported as a required
human review.

### D5. The manuscript draft

The draft describes only what can be verified now: methods, conventions, fairness controls,
leakage controls, datasets and known threats to validity. Each of its 16 method claims is tied to
code, a test, a config or an ADR. The four result claims (RQ1–RQ4) are `pending`. Related work
cites nothing, because the literature matrix is empty.

### D6. Dependencies

`scipy` and `matplotlib` are imported directly now and are declared at their existing pins.
The Optuna floor is corrected to `>= 5.0`, because the TPE adapter uses
`Trial.set_constraint`, which Optuna 5.0 introduced. The Phase 05 pin `>= 4.0` would have
allowed a broken install.

## Findings for owner decisions

1. **Statistical power floor (P5 with P9).** With n paired replicates, the smallest two-sided
   exact Wilcoxon p-value is 2/2ⁿ: 0.0625 for n = 5, 0.00195 for n = 10, 0.00098 for n = 11
   (scipy). Under the proposed Holm family (`metric`) there are 30 tests per metric in both the
   benchmark pilot (6 algorithm pairs × 5 problems) and the HPO pilot (10 pairs × 3 problems).
   The first Holm step then needs p ≤ 0.05/30 ≈ 0.00167, which **n = 10 cannot reach**.
   - So with the protocol's minimum of 10 HPO seeds, no pairwise difference could ever be
     declared under this plan. Options: at least 11 replicates (20 as the protocol recommends
     for benchmarks), a smaller Holm family (`problem_metric`), or fewer pairwise comparisons
     (for example, each method against one baseline).
   - This is a design fact computed from the test itself, not a result.
2. **The pilot analyses behave as intended.** `evooptlab report` on both pilot aggregates (5 and
   3 seeds) produces descriptive statistics and figures. Every test is reported as "not run:
   n < min_replicates", and everything is labelled PRELIMINARY.

## Not done / blocked

- The final analysis, tables, figures and result text: blocked on the final runs.
- Freezing the analysis plan: owner decision P9.
- The literature review and related work: no verified source yet.
- Ablation and sensitivity studies (RQ2): not designed.
- A technical report (`reports/technical_report/`), and copying final figures and tables into
  `reports/`: after the final runs.
- Phase 05 acceptance note: the HPO interface supports all four catalogued tasks, but the pilot
  ran only two non-smoke tasks (bank marketing, California housing). Wine Quality waits for P3,
  so the "at least three distinct tasks" condition needs P3 before final HPO runs.
