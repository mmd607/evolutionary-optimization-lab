"""Phase 05 gate: the held-out test part cannot influence hyperparameter search.

Each test attacks one leakage path from ADR 0006:

* the problem object never holds test rows;
* changing test labels or test features leaves every search objective bit-identical;
* preprocessing is fitted on training folds only (it never sees validation or test rows);
* the split depends only on the problem definition, never on the run seed or algorithm;
* the reported configuration is chosen on validation error only;
* test scores are computed by a separate step, after the run, from a refit on training rows.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from evooptlab.algorithms import get_algorithm
from evooptlab.core.experiment import ExperimentRunner, RunSpec
from evooptlab.hpo import HPOProblem, datasets, evaluate_on_test, select_trial, split_indices
from evooptlab.hpo.datasets import Dataset
from evooptlab.storage import ArtifactLayout
from hpo_helpers import N_MIXED, N_MIXED_TEST, hpo_config, mixed_config

pytestmark = pytest.mark.integration


def _history(result_dir: Path) -> str:
    return (result_dir / "history.csv").read_text(encoding="utf-8")


def _run(problem: HPOProblem, tmp: Path, algorithm: str = "random_search", seed: int = 3) -> Path:
    alg = (
        get_algorithm(algorithm, batch_size=3)
        if algorithm == "random_search"
        else (get_algorithm(algorithm))
    )
    result = ExperimentRunner(ArtifactLayout(tmp)).run(
        problem, alg, RunSpec("pilot", seed=seed, budget=6)
    )
    assert result.outcome == "completed", result.metadata.failure_reason
    return result.run_dir


#: Tamper tests need a split that does not itself depend on the labels. A stratified split is a
#: function of every label, so altering test labels would move rows between train and test; the
#: dataset checksum (not this test) is what pins a stratified split.
ORDERED = {"strategy": "ordered", "test_fraction": 0.2, "random_seed": 0}


def _tamper_test_part(monkeypatch: pytest.MonkeyPatch, how: str) -> None:
    """Make ``datasets.load`` return data whose *test* rows are altered."""
    original = datasets.load

    def load(name: str, variant: str | None, data_dir: Path) -> Dataset:
        data = original(name, variant, data_dir)
        test = split_indices(data.y, hpo_config(split=ORDERED)).test
        X, y = data.X.copy(), data.y.copy()
        if how == "labels":
            y[test] = 1 - y[test]
        else:
            X[test] = np.random.default_rng(0).normal(size=X[test].shape) * 1e3
        return replace(data, X=X, y=y)

    monkeypatch.setattr(datasets, "load", load)


def test_problem_holds_training_rows_only(tmp_path: Path) -> None:
    problem = HPOProblem(hpo_config(), tmp_path)
    _run(problem, tmp_path)
    data = datasets.load("breast_cancer_smoke", None, tmp_path)
    split = split_indices(data.y, hpo_config())
    assert problem.train_indices is not None
    np.testing.assert_array_equal(problem.train_indices, split.train)
    assert np.intersect1d(problem.train_indices, split.test).size == 0

    test_rows = {row.tobytes() for row in data.X[split.test]}
    for name, value in vars(problem).items():
        if isinstance(value, np.ndarray) and value.ndim == 2:
            leaked = {row.tobytes() for row in value} & test_rows
            assert not leaked, f"attribute {name} holds {len(leaked)} test rows"
    assert problem.audit is not None
    assert problem.audit["index_overlap"] == 0
    assert problem.audit["n_train"] + problem.audit["n_test"] == data.n_rows


@pytest.mark.parametrize("how", ["labels", "features"])
def test_test_part_changes_do_not_change_search(
    how: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = hpo_config(split=ORDERED)
    clean = _history(_run(HPOProblem(config, tmp_path), tmp_path / "a"))
    _tamper_test_part(monkeypatch, how)
    tampered = _history(_run(HPOProblem(config, tmp_path), tmp_path / "b"))
    assert tampered == clean  # every candidate, objective and constraint is bit-identical


@pytest.mark.parametrize("how", ["labels", "features"])
def test_selection_ignores_the_test_part(
    how: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import csv

    def chosen(run_dir: Path) -> dict[str, str] | None:
        return select_trial(list(csv.DictReader(_history(run_dir).splitlines())))

    config = hpo_config(split=ORDERED)
    clean = chosen(_run(HPOProblem(config, tmp_path), tmp_path / "a"))
    _tamper_test_part(monkeypatch, how)
    assert chosen(_run(HPOProblem(config, tmp_path), tmp_path / "b")) == clean


def test_preprocessing_is_fitted_on_training_folds_only(
    synthetic_mixed_task: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sklearn.preprocessing import OrdinalEncoder

    fitted: list[tuple[int, set[str]]] = []
    original_fit = OrdinalEncoder.fit

    def spy_fit(self: Any, X: Any, y: Any = None) -> Any:
        result = original_fit(self, X, y)
        fitted.append((len(X), {str(c) for c in self.categories_[0]}))
        return result

    monkeypatch.setattr(OrdinalEncoder, "fit", spy_fit)
    problem = HPOProblem(mixed_config(), tmp_path)
    problem.evaluate_batch(np.full((1, 3), 0.5))
    n_train = N_MIXED - N_MIXED_TEST
    assert problem.audit is not None and problem.audit["n_test"] == N_MIXED_TEST
    # 3-fold CV on the training part: every encoder fit sees exactly two folds (2/3 of the
    # training rows), never a validation or test row.
    assert fitted and {n for n, _ in fitted} == {n_train * 2 // 3}
    assert all("test_only" not in seen for _, seen in fitted)

    fitted.clear()
    report = evaluate_on_test(problem, [0.5, 0.5, 0.5])
    assert {n for n, _ in fitted} == {n_train}  # refit on the full training part only
    assert "test_only" not in fitted[0][1]
    assert report["n_test"] == N_MIXED_TEST


def test_split_is_fixed_by_the_problem_not_the_run(tmp_path: Path) -> None:
    audits = []
    for algorithm, seed in (("random_search", 1), ("random_search", 2), ("optuna_tpe", 1)):
        problem = HPOProblem(hpo_config(), tmp_path)
        _run(problem, tmp_path / f"{algorithm}-{seed}", algorithm, seed)
        assert problem.audit is not None
        audits.append((problem.audit["train_indices_sha256"], problem.audit["test_indices_sha256"]))
    assert len(set(audits)) == 1
    other = HPOProblem(
        hpo_config(split={"strategy": "stratified", "test_fraction": 0.2, "random_seed": 7}),
        tmp_path,
    )
    other.prepare()
    assert other.audit is not None
    assert other.audit["test_indices_sha256"] != audits[0][1]


def test_split_strategies(tmp_path: Path) -> None:
    y = np.array([0] * 80 + [1] * 20)
    ordered = split_indices(
        y, hpo_config(split={"strategy": "ordered", "test_fraction": 0.25, "random_seed": 0})
    )
    np.testing.assert_array_equal(ordered.test, np.arange(75, 100))
    stratified = split_indices(y, hpo_config())
    assert y[stratified.test].sum() == 4  # 20 % of each class
    for split in (ordered, stratified):
        assert np.intersect1d(split.train, split.test).size == 0
        assert split.train.size + split.test.size == y.size


def test_test_evaluation_refits_on_training_rows_and_reports_the_split(tmp_path: Path) -> None:
    problem = HPOProblem(hpo_config(), tmp_path)
    problem.prepare()
    report = evaluate_on_test(problem, [0.5, 0.5, 0.5])
    assert problem.audit is not None
    assert report["train_indices_sha256"] == problem.audit["train_indices_sha256"]
    assert report["test_indices_sha256"] == problem.audit["test_indices_sha256"]
    assert report["test_score"] == pytest.approx(1.0 - report["test_error"])
    assert 0.0 <= report["test_error"] <= 1.0
    assert report["hyperparameters"] == problem.hyperparameters([0.5, 0.5, 0.5])


def test_bank_marketing_never_offers_the_leaking_duration_feature() -> None:
    assert "duration" in datasets.BANK_DROPPED
