# Tables, Figures, and Scientific Presentation Rules

## 1. General formatting

- Number tables and figures in order of first mention.
- Give every table a concise, informative title above it.
- Give every figure a caption below it.
- Define all abbreviations in a note or caption.
- Include units, sample size (`n`), and metric direction.
- Use consistent decimal places within a column.
- Bold the best result only when the comparison is valid and the direction is clear.
- Do not use color as the only way to encode meaning.
- Use readable fonts and vector output (PDF/SVG) for publication figures where possible.
- Keep chart axes honest; do not truncate axes in a misleading way.
- Avoid 3D charts unless the third dimension is essential.
- Avoid decorative effects, gradients, and excessive gridlines.

## 2. Table design

Recommended table columns:
- Algorithm
- Problem / dataset
- Objective budget
- Metric
- Mean
- Standard deviation
- Median / IQR (when useful)
- Runtime (seconds)
- Number of runs

For multi-objective tables, do not compress different metrics into one unexplained score. State whether higher or lower is better.

### Example table template (illustrative only)

| Algorithm | HV ↑ | IGD ↓ | Runtime (s) ↓ | Runs |
|---|---:|---:|---:|---:|
| NSGA-II | — | — | — | 20 |
| Differential Evolution variant | — | — | — | 20 |
| Random Search | — | — | — | 20 |

The em dash means results have not yet been measured. Never fill placeholders with invented values.

## 3. Figure requirements

Core figures:
1. Research workflow / system architecture.
2. Pareto fronts for representative problems.
3. HV or IGD convergence curves against objective evaluations.
4. Runtime versus solution-quality trade-off.
5. Distribution/box plots across independent seeds.
6. HPO best-so-far curves.
7. Pareto plot for predictive score versus computational cost.
8. Ablation and sensitivity plots.

## 4. Plotting rules

- Use the same axis ranges when comparing equivalent panels.
- Label axes with metric names and units.
- Include legend labels that identify algorithm and configuration.
- Show uncertainty (confidence interval, standard deviation band, or distribution) where appropriate.
- Use consistent algorithm naming and line styles across the paper.
- Save plot data alongside figures.
- Prefer `matplotlib` or Plotly with a documented style configuration.
- Generate figures from scripts, not manual editing.
- Use colorblind-friendly palettes and verify grayscale readability.

## 5. Captions

A useful caption explains:
- what is plotted;
- which algorithms/tasks are compared;
- the budget and number of runs;
- what error bars or shaded bands represent;
- any normalization or reference-front details.

Do not interpret all results only in captions; explain their meaning in the Results section.
