"""Config-driven experiment matrices: plan, run (with safe resume), diagnose, aggregate.

See ``docs/decisions/0005-experiment-runner-and-fairness-checks.md`` and, for HPO studies and
their held-out test evaluation, ``docs/decisions/0006-hpo-tasks-and-leakage-controls.md``.
"""

from __future__ import annotations

from evooptlab.experiments.aggregate import (
    default_output_dir,
    run_rows,
    summary_rows,
    write_aggregate,
)
from evooptlab.experiments.diagnostics import (
    Check,
    DiagnosticsReport,
    StudyCollection,
    collect_study,
    diagnose,
    projected_seconds,
)
from evooptlab.experiments.hpo_evaluation import HeldOutEvaluationReport, evaluate_study_on_test
from evooptlab.experiments.matrix import (
    RunCell,
    StudyError,
    build_matrix,
    cell_config_hash,
    matrix_summary,
    replicate_seeds,
    run_spec,
)
from evooptlab.experiments.records import read_test_evaluations
from evooptlab.experiments.study import StudyRunReport, run_study

__all__ = [
    "Check",
    "DiagnosticsReport",
    "HeldOutEvaluationReport",
    "RunCell",
    "StudyCollection",
    "StudyError",
    "StudyRunReport",
    "build_matrix",
    "cell_config_hash",
    "collect_study",
    "default_output_dir",
    "diagnose",
    "evaluate_study_on_test",
    "matrix_summary",
    "projected_seconds",
    "read_test_evaluations",
    "replicate_seeds",
    "run_rows",
    "run_spec",
    "run_study",
    "summary_rows",
    "write_aggregate",
]
