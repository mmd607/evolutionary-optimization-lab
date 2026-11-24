"""Optimization algorithms behind the common ask/tell interface.

Use :func:`get_algorithm` to build one by name with explicit hyperparameters.
"""

from __future__ import annotations

from typing import Any

from evooptlab.algorithms.random_search import RandomSearch
from evooptlab.core.algorithm import Algorithm

ALGORITHMS: dict[str, type[Algorithm]] = {cls.name: cls for cls in (RandomSearch,)}


def get_algorithm(name: str, **hyperparameters: Any) -> Algorithm:
    """Instantiate a registered algorithm; unknown names or hyperparameters fail early."""
    try:
        cls = ALGORITHMS[name]
    except KeyError as exc:
        raise ValueError(f"unknown algorithm {name!r}; available: {', '.join(ALGORITHMS)}") from exc
    return cls(**hyperparameters)


__all__ = ["ALGORITHMS", "RandomSearch", "get_algorithm"]
