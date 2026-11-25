"""Held-out test evaluation of HPO runs: a separate, one-time step after the runs (ADR 0006).

For every completed canonical run of an HPO study, the configuration with the lowest
validation error among successful trials (:func:`~evooptlab.hpo.problem.select_trial`) is
refitted on the full training part and scored once on the test part. The result is written to

    <root>/test_evaluations/<stage>/<run_id>.json

* The run directory itself is never modified, and an existing evaluation is never recomputed or
  overwritten (exclusive creation), so a test score cannot be "re-rolled".
* The selection uses ``history.csv`` only, i.e. validation results. Nothing here is visible to,
  or fed back into, any algorithm.
* Failed runs are not evaluated: they are excluded from scoring (ADR 0005).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evooptlab.experiments.diagnostics import StudyCollection
from evooptlab.experiments.matrix import StudyError
from evooptlab.experiments.records import held_out_path
from evooptlab.storage.layout import ArtifactLayout
from evooptlab.utils.environment import capture_environment

SELECTION_RULE = "lowest validation_error (f_0) among feasible trials; ties -> earliest"


@dataclass
class HeldOutEvaluationReport:
    evaluated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    no_successful_trial: list[str] = field(default_factory=list)


def evaluate_study_on_test(
    collection: StudyCollection,
    layout: ArtifactLayout,
    *,
    repo_root: Path | None = None,
) -> HeldOutEvaluationReport:
    """Evaluate every completed canonical run that has no stored test evaluation yet."""
    from evooptlab.hpo.datasets import DatasetError
    from evooptlab.hpo.problem import HPOProblem, evaluate_on_test, select_trial

    study = collection.study
    if not study.is_hpo:
        raise StudyError(f"study {study.name!r} has no HPO problems to evaluate on test data")
    report = HeldOutEvaluationReport()
    git = capture_environment(repo_root).git
    problems: dict[str, HPOProblem] = {}
    for cell in collection.cells:
        record = collection.canonical.get(cell.key)
        if record is None or record.metadata.outcome != "completed":
            continue
        path = held_out_path(layout, study.stage, record.run_id)
        if path.exists():
            report.skipped.append(record.run_id)
            continue
        problem = problems.get(cell.problem.name)
        if problem is None:
            built = cell.build_problem()
            assert isinstance(built, HPOProblem)
            try:
                built.prepare()
            except DatasetError as exc:
                raise StudyError(f"problem {cell.problem.name}: {exc}") from exc
            problem = problems[cell.problem.name] = built
        chosen = select_trial(record.read_history())
        document: dict[str, Any] = {
            "run_id": record.run_id,
            "config_hash": record.metadata.config_hash,
            "study": study.name,
            "problem": cell.problem.name,
            "algorithm": cell.algorithm.name,
            "replicate": cell.replicate,
            "selection_rule": SELECTION_RULE,
            "evaluated_at_utc": datetime.now(UTC).isoformat(),
            "evaluator_git_commit": git.commit,
            "evaluator_git_dirty": git.dirty,
        }
        if chosen is None:
            document.update({"selected_evaluation_id": None, "test": None})
            report.no_successful_trial.append(record.run_id)
        else:
            u = [float(chosen[f"x_{i}"]) for i in range(problem.spec.n_variables)]
            document.update(
                {
                    "selected_evaluation_id": int(chosen["evaluation_id"]),
                    "selected_validation_error": float(chosen["f_0"]),
                    "test": evaluate_on_test(problem, u),
                }
            )
            report.evaluated.append(record.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(document, indent=2, sort_keys=True) + "\n")
    return report
