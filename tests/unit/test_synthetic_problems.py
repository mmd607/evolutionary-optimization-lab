"""Reference-value tests for the synthetic framework-test problems."""

from __future__ import annotations

import numpy as np
import pytest

from evooptlab.benchmarks import ConstrainedSphere, Sphere, TwoSpheres


def test_sphere_optimum_and_values() -> None:
    p = Sphere(3, center=[1.0, -2.0, 0.5])
    out = p.evaluate_batch(np.array([[1.0, -2.0, 0.5], [0.0, 0.0, 0.0]]))
    np.testing.assert_allclose(out.objectives[:, 0], [0.0, 1.0 + 4.0 + 0.25])
    assert out.constraints is None
    assert p.spec.n_objectives == 1


@pytest.mark.parametrize("kw", [{"n_variables": 0}, {"center": [1.0]}, {"center": [9.0, 0, 0]}])
def test_sphere_rejects_bad_arguments(kw: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        Sphere(**kw)  # type: ignore[arg-type]


def test_two_spheres_front_points_are_attained() -> None:
    p = TwoSpheres(4)
    t = np.linspace(0, 1, 11)
    x = np.repeat(t[:, None], 4, axis=1)  # Pareto set: x = t * 1
    np.testing.assert_allclose(p.evaluate_batch(x).objectives, p.pareto_front(11))


def test_two_spheres_off_front_is_dominated() -> None:
    p = TwoSpheres(2)
    off = p.evaluate_batch(np.array([[0.2, 0.8]])).objectives[0]
    on = p.evaluate_batch(np.array([[0.5, 0.5]])).objectives[0]
    assert np.all(on <= off)
    assert np.any(on < off)


def test_constrained_sphere_feasibility_and_optimum() -> None:
    p = ConstrainedSphere(2)
    out = p.evaluate_batch(np.array([[0.5, 0.5], [0.1, 0.1], [1.0, 1.0]]))
    assert out.constraints is not None
    np.testing.assert_allclose(out.constraints[:, 0], [0.0, 0.8, -1.0])
    np.testing.assert_allclose(out.objectives[0, 0], p.spec.metadata["optimum_value"])


def test_synthetic_problems_are_flagged() -> None:
    for problem in (Sphere(), TwoSpheres(), ConstrainedSphere()):
        assert problem.spec.metadata["synthetic"] is True


@pytest.mark.parametrize("cls", [TwoSpheres, ConstrainedSphere])
def test_dimension_must_be_positive(cls: type[TwoSpheres] | type[ConstrainedSphere]) -> None:
    with pytest.raises(ValueError):
        cls(0)
