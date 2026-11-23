"""Deterministic seed derivation.

Two seed policies are supported, because the protocol has not yet chosen one (ADR 0001, P6):

* **explicit**: the config lists per-run seeds (``configs/benchmarks.yaml``);
* **derived**: per-run seeds are derived from a single ``master_seed``
  (``configs/experiments.yaml``) with :func:`derive_run_seeds`.

Either way, one integer *run seed* identifies a run. All randomness inside that run (algorithm,
problem noise, tie-breaking) must come from generators built by :func:`make_rng`, or from
:func:`derive_seed` with that run seed and a named stream, never from global NumPy or ``random``
state.

Derivation hashes the master seed and the keys with SHA-256. It does not depend on the Python
version, the platform, or the order of calls, and new keys never change existing seeds.
"""

from __future__ import annotations

import hashlib
import json

import numpy as np

#: Seeds are kept in [0, 2**63) so they fit a signed 64-bit integer in CSV/Parquet/JSON consumers.
MAX_SEED = 2**63 - 1

SeedKey = str | int


def _check_seed(seed: int, label: str = "seed") -> None:
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError(f"{label} must be an int, got {type(seed).__name__}")
    if not 0 <= seed <= MAX_SEED:
        raise ValueError(f"{label} must be in [0, 2**63 - 1], got {seed}")


def derive_seed(master_seed: int, *keys: SeedKey) -> int:
    """Derive a child seed from ``master_seed`` and an ordered tuple of ``keys``.

    >>> derive_seed(2026, "ZDT1", "nsga2", 0) == derive_seed(2026, "ZDT1", "nsga2", 0)
    True
    """
    _check_seed(master_seed, "master_seed")
    for key in keys:
        if isinstance(key, bool) or not isinstance(key, str | int):
            raise TypeError(f"seed keys must be str or int, got {type(key).__name__}")
    # Tag every key with its type so that 1 and "1" derive different seeds.
    payload = json.dumps(
        [master_seed, [[type(k).__name__, k] for k in keys]], separators=(",", ":")
    )
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & MAX_SEED


def derive_run_seeds(master_seed: int, n_runs: int, *scope: SeedKey) -> list[int]:
    """Derive ``n_runs`` distinct run seeds for a scope such as ``("ZDT1", "nsga2")``.

    The seed for replicate ``i`` depends only on ``(master_seed, *scope, i)``. Increasing
    ``n_runs`` keeps the existing seeds and adds new ones.
    """
    if n_runs < 0:
        raise ValueError("n_runs must be non-negative")
    seeds = [derive_seed(master_seed, *scope, "replicate", i) for i in range(n_runs)]
    if len(set(seeds)) != len(seeds):  # pragma: no cover - 2**-63 collision probability
        raise RuntimeError("seed collision; choose a different master seed")
    return seeds


def make_rng(seed: int) -> np.random.Generator:
    """Return an independent PCG64 generator for ``seed``."""
    _check_seed(seed)
    return np.random.Generator(np.random.PCG64(seed))
