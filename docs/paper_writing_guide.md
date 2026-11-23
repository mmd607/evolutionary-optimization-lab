# Scientific Paper Writing Guide

## 1. Manuscript structure

### Title
Specific, concise, and aligned with the actual contribution. Avoid claims such as "novel" or "state-of-the-art" unless supported.

### Abstract (typically 150–250 words; follow target venue)
Include:
1. Problem context.
2. Specific gap / motivation.
3. Objective and methods.
4. Benchmarks and experimental protocol.
5. Main quantitative findings (only after experiments).
6. Practical implication and limitation.

Do not write results before they exist. During planning, use an abstract placeholder clearly marked `DRAFT — RESULTS PENDING`.

### 1. Introduction
- Explain the practical/scientific problem.
- Explain why fair comparison and resource constraints matter.
- Summarize the gap established by literature.
- State research questions.
- List contributions in precise, verifiable terms.
- Provide a short paper roadmap.

### 2. Related Work
Organize by themes:
- evolutionary multi-objective optimization;
- population-based and swarm methods;
- Bayesian/model-based optimization;
- hyperparameter optimization;
- benchmark methodology and statistical comparison.

Synthesize studies; do not write one disconnected paragraph per paper. Identify similarities, differences, and limitations.

### 3. Problem Formulation
Define:
- decision variables;
- objective functions;
- constraints;
- search space and bounds;
- optimization direction;
- evaluation budget;
- noise assumptions.

For HPO, define the model, search space, data split, objective metrics, and compute-cost measure.

### 4. Methodology
Describe:
- framework architecture;
- algorithm implementations and versions;
- algorithm parameters;
- initialization, selection, crossover, mutation, repair, and termination;
- budget accounting;
- metric calculation;
- data preprocessing and HPO pipeline.

Provide enough detail for an independent researcher to reproduce the work.

### 5. Experimental Setup
State:
- hardware and software;
- datasets and licenses;
- benchmark definitions;
- run counts and seeds;
- budgets;
- parameter settings;
- statistical tests;
- exclusion rules.

### 6. Results
Present findings in research-question order. Start with the direct result, then evidence, then interpretation. Report negative and mixed results.

### 7. Discussion
Explain why patterns may have occurred. Compare with prior studies. Separate evidence from speculation. Discuss practical implications and generalization limits.

### 8. Ablation and Sensitivity Analysis
Show the contribution of individual components and sensitivity to important settings. Keep all other conditions controlled.

### 9. Threats to Validity and Limitations
Discuss internal, external, construct, and conclusion validity. Mention benchmark representativeness, implementation bias, seed count, hardware, dataset limitations, and compute budget.

### 10. Conclusion and Future Work
Answer each RQ based on evidence. Do not introduce new results. Give realistic future directions.

### References
Use a consistent style (IEEE or APA, depending on target venue). Verify metadata, DOI, author order, year, venue, and URL. Use a reference manager or BibTeX.

## 2. Writing quality rules

- Use precise academic language.
- Define acronyms at first use.
- Avoid unsupported adjectives: "excellent", "revolutionary", "highly accurate".
- Avoid causal claims from observational comparisons.
- Use past tense for completed methods/results and present tense for established facts.
- Ensure every figure/table is mentioned and interpreted in the text.
- Avoid plagiarism and patchwriting; paraphrase with citation.
- Never fabricate citations or use references that do not support the claim.
- Clearly distinguish the authors' implementation from third-party library behavior.
- State limitations rather than hiding them.

## 3. Research gap validation

Before asserting a gap:
1. Search recent surveys and primary studies.
2. Identify close competing work.
3. Compare their scope, methods, budgets, metrics, and tasks.
4. Read limitations and supplementary materials.
5. Write a gap statement that is narrow and evidenced.
6. Explain exactly how this project addresses it.
7. If prior work already addresses it, revise the question rather than exaggerating novelty.

## 4. Submission readiness

Before selecting a venue:
- check aims and scope;
- verify indexing and current publication policies from official sources;
- check article type, formatting, fees, review model, and ethics requirements;
- avoid predatory journals and guaranteed-acceptance claims;
- do not claim a target quartile without verifying current relevant category/year.
