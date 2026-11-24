"""Tiny study configs and misbehaving algorithms for experiment-runner tests."""

from __future__ import annotations

from typing import Any

from evooptlab.algorithms import RandomSearch, get_algorithm
from evooptlab.config.schemas import StudyConfig
from evooptlab.core.algorithm import Algorithm
from evooptlab.core.evaluator import EvaluationResult
from evooptlab.experiments import RunCell

BUDGET = 30


def make_study(**overrides: Any) -> StudyConfig:
    """2 problems x 2 algorithms x 2 seeds at 30 evaluations: 8 runs, well under a second."""
    data: dict[str, Any] = {
        "name": "tiny",
        "stage": "pilot",
        "output_dir": "unused",
        "problems": [
            {"name": "ZDT1", "objectives": 2, "variables": 4},
            {"name": "DTLZ2", "objectives": 3, "variables": 5},
        ],
        "algorithms": [
            {"name": "random_search", "parameters": {"batch_size": 10}},
            {"name": "nsga2", "parameters": {"pop_size": 8}},
        ],
        "budget": {"unit": "objective_evaluations", "max_evaluations": BUDGET},
        "seeds": {"policy": "explicit", "values": [1, 2]},
    }
    data.update(overrides)
    return StudyConfig.model_validate(data)


class Exploding(RandomSearch):
    """Same name and parameters as ``random_search`` (so the same cell hash), but fails."""

    def tell(self, result: EvaluationResult) -> None:
        raise RuntimeError("boom")


class Interrupting(RandomSearch):
    def tell(self, result: EvaluationResult) -> None:
        raise KeyboardInterrupt


def builder_replacing(target: tuple[str, str, int], cls: type[RandomSearch]) -> Any:
    """A ``RunCell.build_algorithm`` replacement that swaps in ``cls`` for one cell."""

    def build(self: RunCell) -> Algorithm:
        if self.key == target:
            return cls(**self.algorithm.parameters)  # type: ignore[arg-type]
        return get_algorithm(self.algorithm.name, **self.algorithm.parameters)

    return build
