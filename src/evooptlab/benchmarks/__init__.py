"""Benchmark problems.

* ``ZDT1``, ``ZDT2``, ``ZDT3``, ``DTLZ2``, ``DTLZ7``: the core multi-objective suite.
* ``Sphere``, ``TwoSpheres``, ``ConstrainedSphere``: synthetic framework-test problems only.
"""

from __future__ import annotations

from evooptlab.benchmarks.dtlz import DTLZ2, DTLZ7
from evooptlab.benchmarks.synthetic import ConstrainedSphere, Sphere, TwoSpheres
from evooptlab.benchmarks.zdt import ZDT1, ZDT2, ZDT3

__all__ = ["DTLZ2", "DTLZ7", "ZDT1", "ZDT2", "ZDT3", "ConstrainedSphere", "Sphere", "TwoSpheres"]
