"""Hyperparameter optimization as a black-box :class:`~evooptlab.core.problem.Problem`.

Leakage controls (ADR 0006; enforced by ``tests/leakage``)
---------------------------------------------------------
1. **The test part never enters the problem.** The split is drawn once from the problem's own
   ``split.random_seed`` (independent of run seeds and algorithms). :class:`HPOProblem` keeps
   copies of the *training* rows only; the test rows are dropped right after the split, and
   only aggregate audit numbers about them survive.
2. **Search only sees cross-validation on the training part.** Every trial runs the same folds,
   drawn from ``cv.random_seed``.
3. **Preprocessing is fitted inside each training fold**, because it is a pipeline step.
4. **Test scores come from a separate function**, :func:`evaluate_on_test`, which is called only
   after a run has completed and only for the configuration selected on validation error
   (:func:`select_trial`). Its result is never fed back to an algorithm.

Objectives (all minimized)
--------------------------
* ``validation_error``: ``1 - mean macro-F1`` (classification) or mean RMSE (regression) over
  the CV folds.
* ``fit_seconds`` (optional): total wall-clock fit time over the folds. It is measured, so it
  is noisy and not bit-reproducible across machines or runs.

Failed trials
-------------
A trial whose fit or prediction raises is recorded, never dropped: its constraint ``g_0`` is
``1`` (infeasible), ``validation_error`` is the worst value (``1`` for macro-F1 error; the
training-fold-mean predictor's CV RMSE for regression) and ``fit_seconds`` is the time spent.
Successful trials have ``g_0 = 0``. Quality is computed on feasible trials only.
"""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from evooptlab.config.schemas import HPOProblemConfig
from evooptlab.core.problem import FloatArray, Problem, ProblemOutput, ProblemSpec
from evooptlab.hpo import datasets
from evooptlab.hpo.models import build_model, check_parameters
from evooptlab.hpo.search_space import SearchSpace

IntArray = npt.NDArray[np.int64]


@dataclass(frozen=True)
class SplitIndices:
    train: IntArray
    test: IntArray


def split_indices(y: npt.NDArray[Any], config: HPOProblemConfig) -> SplitIndices:
    """Deterministic train/test row indices; depends only on the data and ``config.split``."""
    from sklearn.model_selection import train_test_split

    n = int(y.shape[0])
    rows = np.arange(n, dtype=np.int64)
    split = config.split
    if split.strategy == "ordered":
        n_test = math.ceil(split.test_fraction * n)
        return SplitIndices(rows[: n - n_test], rows[n - n_test :])
    train, test = train_test_split(
        rows,
        test_size=split.test_fraction,
        random_state=split.random_seed,
        stratify=y if split.strategy == "stratified" else None,
    )
    return SplitIndices(np.sort(train), np.sort(test))


def cv_folds(
    y_train: npt.NDArray[Any], config: HPOProblemConfig
) -> list[tuple[IntArray, IntArray]]:
    from sklearn.model_selection import KFold, StratifiedKFold

    cv = config.cv
    splitter = (
        StratifiedKFold(cv.n_splits, shuffle=True, random_state=cv.random_seed)
        if cv.strategy == "stratified_kfold"
        else KFold(cv.n_splits, shuffle=True, random_state=cv.random_seed)
    )
    placeholder = np.zeros((y_train.shape[0], 1))
    return [
        (np.asarray(a, dtype=np.int64), np.asarray(b, dtype=np.int64))
        for a, b in splitter.split(placeholder, y_train)
    ]


def score_error(task_type: str, y_true: npt.NDArray[Any], y_pred: npt.NDArray[Any]) -> float:
    """Error to minimize: ``1 - macro-F1`` or RMSE."""
    from sklearn.metrics import f1_score, root_mean_squared_error

    if task_type == "classification":
        return 1.0 - float(f1_score(y_true, y_pred, average="macro"))
    return float(root_mean_squared_error(y_true, y_pred))


def _row_digests(X: npt.NDArray[Any]) -> list[str]:
    return [hashlib.sha256(repr(tuple(row)).encode("utf-8")).hexdigest() for row in X]


def _index_digest(indices: IntArray) -> str:
    return hashlib.sha256(np.ascontiguousarray(indices, dtype=np.int64).tobytes()).hexdigest()


class HPOProblem(Problem):
    """CV error (and optionally fit time) of one model configuration per candidate.

    Construction is cheap and needs no data: the dataset is loaded, verified and split on the
    first evaluation. Planning and diagnostics therefore work without the raw files.
    """

    def __init__(self, config: HPOProblemConfig, data_dir: Path | str = "data") -> None:
        task = datasets.get_task(config.task)
        if config.task_type not in task.task_types:
            raise ValueError(
                f"{config.task} supports {list(task.task_types)}, not {config.task_type!r}"
            )
        if bool(task.variants) != (config.variant is not None) or (
            config.variant is not None and config.variant not in task.variants
        ):
            raise ValueError(f"{config.task}: variant must be one of {list(task.variants)}")
        check_parameters(config.model, [*config.search_space, *config.fixed_parameters])
        self.config = config
        self.task = task
        self.data_dir = Path(data_dir)
        self.space = SearchSpace.from_config(config.search_space)
        d = self.space.n_dimensions
        super().__init__(
            ProblemSpec(
                name=config.name,
                lower_bounds=np.zeros(d),
                upper_bounds=np.ones(d),
                n_objectives=len(config.objectives),
                n_constraints=1,
                metadata={"kind": "hpo", "task": config.task},
            )
        )
        self._prepared = False
        self._X: npt.NDArray[Any] | None = None
        self._y: npt.NDArray[Any] | None = None
        self._folds: list[tuple[IntArray, IntArray]] = []
        self._categorical: tuple[int, ...] = ()
        self._worst_error = 1.0
        self.train_indices: IntArray | None = None
        self.audit: dict[str, Any] | None = None

    # ------------------------------------------------------------------ definition
    def describe(self) -> dict[str, Any]:
        c = self.config
        return {
            "kind": "hpo",
            "task": c.task,
            "variant": c.variant,
            "dataset_sha256": self.task.integrity_sha256,
            "loader_version": self.task.loader_version,
            "task_type": c.task_type,
            "target_metric": c.target_metric,
            "objectives": list(c.objectives),
            "model": c.model,
            "model_seed": c.model_seed,
            "fixed_parameters": dict(c.fixed_parameters),
            "search_space": self.space.describe(),
            "split": c.split.model_dump(mode="json"),
            "cv": c.cv.model_dump(mode="json"),
            "failed_trial_rule": "g_0 = 1, validation_error = worst value",
        }

    def hyperparameters(self, u: Sequence[float]) -> dict[str, Any]:
        """Full model hyperparameters of a unit-cube point (searched + fixed)."""
        return {**self.config.fixed_parameters, **self.space.decode(u)}

    # ------------------------------------------------------------------ data
    def prepare(self) -> None:
        """Load, verify and split the data; keep only the training part. Idempotent."""
        if self._prepared:
            return
        data = datasets.load(self.config.task, self.config.variant, self.data_dir)
        split = split_indices(data.y, self.config)
        X_train = data.X[split.train].copy()
        y_train = data.y[split.train].copy()
        train_rows = set(_row_digests(X_train))
        duplicates = sum(d in train_rows for d in _row_digests(data.X[split.test]))
        self.audit = {
            "n_rows": data.n_rows,
            "n_train": int(split.train.size),
            "n_test": int(split.test.size),
            "index_overlap": int(np.intersect1d(split.train, split.test).size),
            "train_indices_sha256": _index_digest(split.train),
            "test_indices_sha256": _index_digest(split.test),
            "test_rows_duplicating_train_features": int(duplicates),
            "n_features": len(data.feature_names),
            "categorical_features": [data.feature_names[i] for i in data.categorical_features],
        }
        self._folds = cv_folds(y_train, self.config)
        self._categorical = data.categorical_features
        self._X, self._y = X_train, y_train
        self.train_indices = split.train
        if self.config.task_type == "regression":
            self._worst_error = float(
                np.mean(
                    [
                        score_error("regression", y_train[va], np.full(va.size, y_train[tr].mean()))
                        for tr, va in self._folds
                    ]
                )
            )
        del data, split  # the test part is not kept anywhere in this object
        self._prepared = True

    # ------------------------------------------------------------------ evaluation
    def _trial(self, u: npt.NDArray[np.float64]) -> tuple[float, float, bool]:
        assert self._X is not None and self._y is not None
        params = self.hyperparameters(u.tolist())
        start = time.perf_counter()
        errors: list[float] = []
        try:
            for train, valid in self._folds:
                estimator = build_model(
                    self.config.model,
                    self.config.task_type,
                    params,
                    model_seed=self.config.model_seed,
                    categorical_features=self._categorical,
                    n_features=self._X.shape[1],
                )
                estimator.fit(self._X[train], self._y[train])
                errors.append(
                    score_error(
                        self.config.task_type, self._y[valid], estimator.predict(self._X[valid])
                    )
                )
        except Exception:
            return self._worst_error, time.perf_counter() - start, False
        return float(np.mean(errors)), time.perf_counter() - start, True

    def evaluate_batch(self, candidates: FloatArray) -> ProblemOutput:
        self.prepare()
        n = candidates.shape[0]
        f = np.empty((n, self.spec.n_objectives))
        g = np.empty((n, 1))
        for i in range(n):
            error, seconds, ok = self._trial(candidates[i])
            values = {"validation_error": error, "fit_seconds": seconds}
            f[i] = [values[name] for name in self.config.objectives]
            g[i, 0] = 0.0 if ok else 1.0
        return ProblemOutput(objectives=f, constraints=g)


# ---------------------------------------------------------------------------------------------
# Selection and held-out test evaluation (after a run, never during it)
# ---------------------------------------------------------------------------------------------
def select_trial(rows: Sequence[dict[str, str]]) -> dict[str, str] | None:
    """The trial a run reports: lowest validation error among feasible trials.

    Ties go to the earliest evaluation. Only validation results are used, so the choice cannot
    depend on test data. Returns ``None`` when no trial succeeded.
    """
    feasible = [r for r in rows if r["feasible"] == "True"]
    if not feasible:
        return None
    return min(feasible, key=lambda r: (float(r["f_0"]), int(r["evaluation_id"])))


def evaluate_on_test(problem: HPOProblem, u: Sequence[float]) -> dict[str, Any]:
    """Refit the selected configuration on the full training part; score it once on test."""
    config = problem.config
    data = datasets.load(config.task, config.variant, problem.data_dir)
    split = split_indices(data.y, config)
    params = problem.hyperparameters(u)
    estimator = build_model(
        config.model,
        config.task_type,
        params,
        model_seed=config.model_seed,
        categorical_features=data.categorical_features,
        n_features=data.X.shape[1],
    )
    start = time.perf_counter()
    estimator.fit(data.X[split.train], data.y[split.train])
    fit_seconds = time.perf_counter() - start
    y_test = data.y[split.test]
    error = score_error(config.task_type, y_test, estimator.predict(data.X[split.test]))
    score = 1.0 - error if config.target_metric == "f1_macro" else -error
    return {
        "hyperparameters": params,
        "target_metric": config.target_metric,
        "test_score": score,
        "test_error": error,
        "refit_seconds": fit_seconds,
        "n_train": int(split.train.size),
        "n_test": int(split.test.size),
        "train_indices_sha256": _index_digest(split.train),
        "test_indices_sha256": _index_digest(split.test),
        "dataset_sha256": problem.task.integrity_sha256,
    }
