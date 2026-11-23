# Metrics and Statistical Analysis

## 1. Multi-objective optimization metrics

Use metrics that capture complementary aspects of Pareto approximation. State the reference point/front and normalization method.

| Metric | What it measures | Interpretation |
|---|---|---|
| Hypervolume (HV) | Dominated objective-space volume | Higher is generally better for minimization with a valid reference point |
| Inverted Generational Distance (IGD / IGD+) | Distance to reference Pareto front | Lower is better |
| Generational Distance (GD) | Distance from obtained to reference front | Lower is better |
| Spread / Diversity | Distribution of solutions | Higher/lower depends on exact definition |
| Feasibility rate | Fraction of feasible solutions | Higher is better |
| Evaluations to target | Budget needed to reach threshold | Lower is better |

Do not compare HV values across problems without explaining objective normalization and reference-point selection. For each metric, cite its formal definition and implementation.

## 2. HPO metrics

| Metric | Use |
|---|---|
| Validation macro-F1 / ROC-AUC | Classification quality |
| Validation RMSE / MAE | Regression quality |
| Wall-clock time | Practical cost |
| Objective evaluations / trials | Search budget |
| Peak memory | Resource use |
| Inference latency | Deployment cost |
| Model size | Storage/deployment cost |
| Best-so-far curve | Search progress |

Use task-appropriate metrics. Do not report accuracy alone for imbalanced classification.

## 3. Statistical analysis

- Report mean and standard deviation across independent runs.
- Also report median and interquartile range when distributions are skewed.
- Include confidence intervals where appropriate and explain the method.
- For paired comparisons, use a paired test only when pairing is justified.
- For multiple algorithms across multiple problems, consider Friedman test followed by an appropriate post-hoc procedure (e.g. Holm-adjusted pairwise comparisons).
- For two paired conditions, Wilcoxon signed-rank may be suitable; for independent conditions, select a suitable independent test.
- Check assumptions and sample size. Do not mechanically apply tests.
- Correct for multiple comparisons.
- Report effect sizes, not p-values alone.
- Distinguish statistical significance from practical significance.

The exact test plan must be finalized before inspecting final comparison results.

## 4. Required result tables

1. Benchmark configuration and evaluation budget.
2. Per-problem/per-algorithm metrics across runs.
3. Aggregated ranking with statistical annotations.
4. Runtime and objective-evaluation cost.
5. HPO task results and selected configurations.
6. Ablation results.
7. Robustness / sensitivity results.

## 5. Result integrity

- Tables must be generated from raw experiment artifacts, not typed manually.
- Preserve full precision in machine-readable data; round only for display.
- Include units and metric direction.
- Mark missing or failed runs explicitly.
- Never replace missing values with zero unless zero is the true measured value.
- Keep raw and aggregated results separate.
