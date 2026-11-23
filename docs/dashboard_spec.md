# Dashboard Specification

## Purpose

The dashboard is an exploration and reporting layer over stored experiment artifacts. It must not run expensive optimization jobs implicitly when a page loads.

## Suggested stack
Streamlit + Plotly. Keep dashboard code separate from core optimization package.

## Pages

### 1. Overview
- project description;
- experiment count;
- algorithms and benchmark families;
- latest run status;
- reproducibility metadata.

### 2. Benchmark Explorer
- select problem, algorithm, seed, budget;
- display Pareto fronts;
- show objective-space scatter plots;
- compare HV, IGD, runtime, and feasibility.

### 3. Convergence Analysis
- best-so-far / HV / IGD curves versus evaluations;
- median curve and uncertainty band across seeds;
- allow only comparable budgets to be overlaid.

### 4. HPO Explorer
- select dataset, model family, optimizer;
- inspect trial history;
- plot predictive quality versus cost;
- show selected configuration and test result only when final evaluation is authorized.

### 5. Statistical Comparison
- aggregated tables;
- distribution plots;
- test names, effect sizes, adjusted p-values;
- explicit sample counts.

### 6. Run Details
- config, seed, environment, commit hash;
- logs, duration, status;
- artifact download paths.

## Interaction and integrity rules
- Clearly distinguish pilot from final runs.
- Never display fabricated sample results.
- Show `No results available` for empty states.
- Label cached and stale artifacts.
- Do not let users accidentally compare different evaluation budgets without a warning.
- Dashboard is read-only by default; experiment execution requires an explicit action and confirmation.
