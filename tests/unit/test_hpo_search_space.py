"""Unit-cube decoding and HPO config validation."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from evooptlab.config.schemas import SearchParameterConfig
from evooptlab.hpo.search_space import SearchSpace, decode_one
from hpo_helpers import hpo_config


def _p(**kwargs: Any) -> SearchParameterConfig:
    return SearchParameterConfig.model_validate(kwargs)


class TestDecode:
    def test_float_linear_and_log_hit_both_ends(self) -> None:
        lin = _p(type="float", low=-1.0, high=3.0)
        assert (decode_one(lin, 0.0), decode_one(lin, 0.5), decode_one(lin, 1.0)) == (-1, 1, 3)
        log = _p(type="float", low=0.01, high=1.0, log=True)
        assert decode_one(log, 0.0) == pytest.approx(0.01)
        assert decode_one(log, 0.5) == pytest.approx(0.1)
        assert decode_one(log, 1.0) == pytest.approx(1.0)

    @pytest.mark.parametrize("log", [False, True])
    def test_int_reaches_every_value_within_bounds(self, log: bool) -> None:
        p = _p(type="int", low=2, high=9, log=log)
        values = {decode_one(p, float(u)) for u in np.linspace(0, 1, 2001)}
        assert values == set(range(2, 10))
        assert all(isinstance(v, int) for v in values)

    def test_int_linear_bins_are_equal_width(self) -> None:
        p = _p(type="int", low=0, high=3)
        counts = np.bincount([decode_one(p, float(u)) for u in np.linspace(0, 1, 4001)])
        assert counts.max() - counts.min() <= 2

    def test_categorical_bins(self) -> None:
        p = _p(type="categorical", choices=["a", "b", "c"])
        assert [decode_one(p, u) for u in (0.0, 0.33, 0.34, 0.99, 1.0)] == list("aabcc")

    def test_out_of_cube_and_wrong_length(self) -> None:
        with pytest.raises(ValueError, match="outside"):
            decode_one(_p(type="float", low=0, high=1), 1.5)
        space = SearchSpace.from_config({"a": _p(type="float", low=0, high=1)})
        with pytest.raises(ValueError, match="expected 1"):
            space.decode([0.1, 0.2])

    def test_space_keeps_order_and_describes_itself(self) -> None:
        space = SearchSpace.from_config(hpo_config().search_space)
        assert space.names == ("learning_rate", "max_iter", "max_leaf_nodes")
        assert space.describe()["max_iter"] == {
            "type": "int",
            "low": 3.0,
            "high": 10.0,
            "log": False,
            "choices": None,
        }


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"type": "float", "low": 1.0, "high": 1.0}, "low < high"),
        ({"type": "float", "low": 0.0, "high": 1.0, "log": True}, "low > 0"),
        ({"type": "int", "low": 0.5, "high": 3}, "integral"),
        ({"type": "int", "choices": [1, 2]}, "not 'choices'"),
        ({"type": "categorical", "choices": ["a"]}, "two choices"),
        ({"type": "categorical", "choices": ["a", "a"]}, "unique"),
        ({"type": "categorical", "choices": ["a", "b"], "low": 0}, "only 'choices'"),
    ],
)
def test_invalid_parameters(kwargs: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        _p(**kwargs)


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"objectives": ["fit_seconds"]}, "start with 'validation_error'"),
        ({"objectives": ["validation_error", "validation_error"]}, "unique"),
        ({"target_metric": "neg_root_mean_squared_error"}, "use target_metric 'f1_macro'"),
        (
            {"task_type": "regression", "target_metric": "neg_root_mean_squared_error"},
            "stratified split or CV",
        ),
        ({"fixed_parameters": {"max_iter": 5}}, "both fixed and searched"),
        ({"task_type": "classification_or_regression"}, "task_type"),
    ],
)
def test_invalid_hpo_problem_configs(overrides: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        hpo_config(**overrides)
