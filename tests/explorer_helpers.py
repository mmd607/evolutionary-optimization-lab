"""A small but real artifact root for explorer and dashboard tests.

Everything in it is produced by the real pipeline: ``run_study`` -> ``test-eval`` ->
``aggregate`` -> ``report``. Nothing is hand-written, so the tests check the dashboard against
what the pipeline actually stores.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from evooptlab.analysis.compare import load_aggregate
from evooptlab.config import load_config
from evooptlab.config.schemas import StudyConfig
from evooptlab.experiments import (
    collect_study,
    diagnose,
    evaluate_study_on_test,
    run_study,
    write_aggregate,
)
from evooptlab.reporting.report import write_report
from evooptlab.storage import ArtifactLayout
from hpo_helpers import hpo_config
from study_helpers import make_study

CONFIGS = Path(__file__).resolve().parents[1] / "configs"
BENCH_SEEDS = [1, 2, 3]


def hpo_study(**overrides: Any) -> StudyConfig:
    base: dict[str, Any] = {
        "name": "hpo-tiny",
        "stage": "pilot",
        "output_dir": "unused",
        "problems": [hpo_config().model_dump(mode="json")],
        "algorithms": [
            {"name": "random_search", "parameters": {"batch_size": 3}},
            {"name": "optuna_tpe", "parameters": {"n_startup_trials": 2}},
        ],
        "budget": {"unit": "objective_evaluations", "max_evaluations": 6},
        "seeds": {"policy": "explicit", "values": [1, 2]},
    }
    base.update(overrides)
    return StudyConfig.model_validate(base)


def bench_study(**overrides: Any) -> StudyConfig:
    return make_study(seeds={"policy": "explicit", "values": BENCH_SEEDS}, **overrides)


def _report(aggregate: Path, root: Path) -> Path:
    plan = load_config(CONFIGS / "analysis_plan.yaml").analysis_plan  # type: ignore[union-attr]
    plan = plan.model_copy(
        update={
            "min_replicates": 2,
            "across_problems": plan.across_problems.model_copy(update={"min_problems": 2}),
        }
    )
    reporting = load_config(CONFIGS / "reporting.yaml").reporting  # type: ignore[union-attr]
    reporting = reporting.model_copy(
        update={"figure_formats": ["svg"], "convergence_checkpoints": 4}
    )
    return write_report(
        load_aggregate(aggregate),
        plan,
        reporting,
        root / "reports" / f"{aggregate.name}__test-plan",
        plan_sha256="0" * 64,
        artifact_root=root,
    )


def build_root(root: Path, data_dir: Path) -> dict[str, Path]:
    """Benchmark study (aggregate + report) and HPO study (test-eval + aggregate)."""
    layout = ArtifactLayout(root)
    bench = bench_study()
    run_study(bench, layout)
    collection = collect_study(bench, layout)
    bench_aggregate = write_aggregate(
        collection, diagnose(collection), root / "aggregates" / "pilot" / "tiny__agg"
    )
    report = _report(bench_aggregate, root)

    hpo = hpo_study()
    run_study(hpo, layout, data_dir=data_dir)
    evaluate_study_on_test(collect_study(hpo, layout, data_dir), layout)
    collection = collect_study(hpo, layout, data_dir)
    hpo_aggregate = write_aggregate(
        collection, diagnose(collection), root / "aggregates" / "pilot" / "hpo-tiny__agg"
    )
    return {"bench_aggregate": bench_aggregate, "hpo_aggregate": hpo_aggregate, "report": report}


def tree_digest(root: Path) -> dict[str, str]:
    """SHA-256 of every file under ``root`` (to prove nothing was written or changed)."""
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }
