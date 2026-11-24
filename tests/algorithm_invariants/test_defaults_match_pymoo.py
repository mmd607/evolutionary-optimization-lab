"""Our explicit hyperparameter defaults must equal pymoo 0.6.2's constructor defaults.

The defaults are declared explicitly so that a pymoo upgrade cannot change a run silently. This
test detects any drift.
"""

from __future__ import annotations

import inspect
from typing import Any

import pymoo
import pytest
from pymoo.algorithms.moo.cmopso import CMOPSO
from pymoo.algorithms.moo.gde3 import GDE3
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.algorithms.soo.nonconvex.de import DE
from pymoo.algorithms.soo.nonconvex.ga import GA
from pymoo.algorithms.soo.nonconvex.pso import PSO
from pymoo.operators.crossover.sbx import SBX
from pymoo.operators.mutation.pm import PM

from evooptlab.algorithms import ALGORITHMS
from evooptlab.algorithms.pymoo_adapter import PYMOO_VERSION

PYMOO_CLASSES: dict[str, Any] = {
    "ga": GA,
    "nsga2": NSGA2,
    "de": DE,
    "gde3": GDE3,
    "pso": PSO,
    "cmopso": CMOPSO,
}
OPERATOR_KEYS = {
    "crossover_prob": (SBX, "prob"),
    "crossover_eta": (SBX, "eta"),
    "crossover_prob_var": (SBX, "prob_var"),
    "mutation_prob": (PM, "prob"),
    "mutation_eta": (PM, "eta"),
    "mutation_prob_var": (PM, "prob_var"),
}
LABELS = {"crossover", "mutation"}


def test_pinned_pymoo_version() -> None:
    assert pymoo.__version__ == PYMOO_VERSION


@pytest.mark.parametrize("name", sorted(PYMOO_CLASSES))
def test_defaults_equal_pymoo_signature(name: str) -> None:
    ours = ALGORITHMS[name].default_parameters()  # type: ignore[attr-defined]
    signature = inspect.signature(PYMOO_CLASSES[name].__init__).parameters
    for key, value in ours.items():
        if key in LABELS:
            continue
        if key in OPERATOR_KEYS:
            op_cls, attr = OPERATOR_KEYS[key]
            default = getattr(op_cls(), attr)
            default = getattr(default, "value", default)
            assert value == default, f"{name}.{key}: ours={value} pymoo={default}"
            continue
        assert key in signature, f"{name}: {key} is not a pymoo constructor argument"
        assert value == signature[key].default, (
            f"{name}.{key}: ours={value} pymoo={signature[key].default}"
        )
