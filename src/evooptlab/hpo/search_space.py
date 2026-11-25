"""Map the unit cube that every algorithm searches onto concrete hyperparameters (ADR 0006).

All algorithms see the same box ``[0, 1]^d``, one coordinate per hyperparameter, in the order
the search space lists them. Decoding is a deterministic function of the coordinate, so a
trial's hyperparameters can always be recovered from ``history.csv``.

* ``float``: ``low + u (high - low)``, or log-uniform when ``log`` is set.
* ``int``: ``[low, high]`` is split into ``high - low + 1`` equal-width bins (log-width bins when
  ``log`` is set), so every integer is reachable and ``u = 1`` maps to ``high``.
* ``categorical``: ``k`` equal-width bins, one per choice.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from evooptlab.config.schemas import ChoiceValue, SearchParameterConfig


@dataclass(frozen=True)
class SearchSpace:
    names: tuple[str, ...]
    parameters: tuple[SearchParameterConfig, ...]

    @classmethod
    def from_config(cls, space: Mapping[str, SearchParameterConfig]) -> SearchSpace:
        return cls(tuple(space), tuple(space.values()))

    @property
    def n_dimensions(self) -> int:
        return len(self.names)

    def decode(self, u: Sequence[float]) -> dict[str, ChoiceValue]:
        if len(u) != self.n_dimensions:
            raise ValueError(f"expected {self.n_dimensions} coordinates, got {len(u)}")
        return {
            name: decode_one(p, float(v))
            for name, p, v in zip(self.names, self.parameters, u, strict=True)
        }

    def describe(self) -> dict[str, Any]:
        return {
            n: p.model_dump(mode="json") for n, p in zip(self.names, self.parameters, strict=True)
        }


def decode_one(p: SearchParameterConfig, u: float) -> ChoiceValue:
    if not 0.0 <= u <= 1.0:
        raise ValueError(f"coordinate {u} outside [0, 1]")
    if p.type == "categorical":
        assert p.choices is not None
        k = len(p.choices)
        return p.choices[min(int(u * k), k - 1)]
    assert p.low is not None and p.high is not None
    if p.type == "float":
        if p.log:
            return math.exp(math.log(p.low) + u * (math.log(p.high) - math.log(p.low)))
        return p.low + u * (p.high - p.low)
    low, high = int(p.low), int(p.high)
    if p.log:
        value = math.floor(math.exp(math.log(low) + u * (math.log(high + 1) - math.log(low))))
    else:
        value = low + math.floor(u * (high - low + 1))
    return min(max(value, low), high)
