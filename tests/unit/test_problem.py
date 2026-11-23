"""Tests for ProblemSpec validation."""

from __future__ import annotations

import numpy as np
import pytest

from evooptlab.core.errors import CandidateError, ProblemDefinitionError
from evooptlab.core.problem import ProblemSpec


def _spec(**kw: object) -> ProblemSpec:
    args: dict[str, object] = {
        "name": "toy",
        "lower_bounds": [0.0, -1.0],
        "upper_bounds": [1.0, 1.0],
        "n_objectives": 2,
    }
    args.update(kw)
    return ProblemSpec(**args)  # type: ignore[arg-type]


class TestDefinition:
    def test_basic_properties(self) -> None:
        spec = _spec()
        assert spec.n_variables == 2
        assert spec.n_constraints == 0
        assert spec.lower_bounds.dtype == np.float64

    def test_bounds_are_read_only_copies(self) -> None:
        lower = np.array([0.0, -1.0])
        spec = _spec(lower_bounds=lower)
        lower[0] = 99.0
        assert spec.lower_bounds[0] == 0.0
        with pytest.raises(ValueError):
            spec.lower_bounds[0] = 5.0

    @pytest.mark.parametrize(
        ("kw", "match"),
        [
            ({"lower_bounds": [0.0], "upper_bounds": [1.0, 1.0]}, "same shape"),
            ({"lower_bounds": [1.0, 0.0], "upper_bounds": [1.0, 1.0]}, "strictly below"),
            ({"lower_bounds": [], "upper_bounds": []}, "non-empty"),
            ({"lower_bounds": [[0.0, 0.0]], "upper_bounds": [[1.0, 1.0]]}, "1-D"),
            ({"lower_bounds": [0.0, -np.inf]}, "finite"),
            ({"n_objectives": 0}, "n_objectives"),
            ({"n_constraints": -1}, "n_constraints"),
            ({"name": "bad__name"}, "problem name"),
            ({"name": "a/b"}, "problem name"),
        ],
    )
    def test_invalid_definitions(self, kw: dict[str, object], match: str) -> None:
        with pytest.raises(ProblemDefinitionError, match=match):
            _spec(**kw)

    def test_equality_and_hash(self) -> None:
        assert _spec() == _spec()
        assert hash(_spec()) == hash(_spec())
        assert _spec() != _spec(n_objectives=3)
        assert _spec() != _spec(upper_bounds=[2.0, 1.0])
        assert _spec().__eq__(object()) is NotImplemented


class TestCandidateValidation:
    def test_valid_batch_including_bounds(self) -> None:
        x = _spec().validate_candidates([[0.0, -1.0], [1.0, 1.0], [0.5, 0.0]])
        assert x.shape == (3, 2)
        assert x.dtype == np.float64

    @pytest.mark.parametrize(
        ("candidates", "match"),
        [
            ([0.5, 0.0], "shape"),
            ([[0.5, 0.0, 0.0]], "shape"),
            (np.empty((0, 2)), "empty"),
            ([[np.nan, 0.0]], "NaN or infinite"),
            ([[np.inf, 0.0]], "NaN or infinite"),
            ([[1.0000001, 0.0]], "outside bounds"),
            ([[0.5, -1.5]], "outside bounds"),
        ],
    )
    def test_invalid_batches(self, candidates: object, match: str) -> None:
        with pytest.raises(CandidateError, match=match):
            _spec().validate_candidates(candidates)  # type: ignore[arg-type]

    def test_out_of_bounds_message_truncates_rows(self) -> None:
        with pytest.raises(CandidateError, match=r"7 candidate\(s\).*\.\.\."):
            _spec().validate_candidates(np.full((7, 2), 5.0))
