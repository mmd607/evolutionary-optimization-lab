"""Model families for HPO tasks. Every algorithm tunes the same family and preprocessing.

``hist_gradient_boosting``
    ``HistGradientBoostingClassifier``/``Regressor`` with ``early_stopping=False`` (so the
    number of boosting iterations is exactly the searched ``max_iter`` and no internal
    validation split is drawn) and a fixed ``random_state`` (the problem's ``model_seed``).
    Categorical columns are ordinal-encoded *inside* the pipeline and passed to the model as
    native categorical features; unseen categories become missing values. Because encoding is a
    pipeline step, it is fitted on each training fold only (no preprocessing leakage).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

#: Hyperparameters that a search space or ``fixed_parameters`` may set.
TUNABLE: dict[str, frozenset[str]] = {
    "hist_gradient_boosting": frozenset(
        {
            "learning_rate",
            "max_iter",
            "max_leaf_nodes",
            "max_depth",
            "min_samples_leaf",
            "l2_regularization",
            "max_features",
            "max_bins",
        }
    )
}


def check_parameters(model: str, names: Sequence[str]) -> None:
    unknown = sorted(set(names) - TUNABLE[model])
    if unknown:
        raise ValueError(
            f"{model}: unknown hyperparameters {unknown}; tunable: {sorted(TUNABLE[model])}"
        )


def build_model(
    model: str,
    task_type: str,
    parameters: Mapping[str, Any],
    *,
    model_seed: int,
    categorical_features: Sequence[int],
    n_features: int,
) -> Any:
    """Return an unfitted scikit-learn estimator (a ``Pipeline`` when encoding is needed)."""
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OrdinalEncoder

    if model not in TUNABLE:
        raise ValueError(f"unknown model family {model!r}")
    check_parameters(model, list(parameters))
    estimator_cls = (
        HistGradientBoostingClassifier
        if task_type == "classification"
        else HistGradientBoostingRegressor
    )
    categorical = list(categorical_features)
    if not categorical:
        return estimator_cls(early_stopping=False, random_state=model_seed, **parameters)
    numeric = [i for i in range(n_features) if i not in set(categorical)]
    encode = ColumnTransformer(
        [
            (
                "categorical",
                OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=np.nan),
                categorical,
            ),
            ("numeric", "passthrough", numeric),
        ]
    )
    mask = [True] * len(categorical) + [False] * len(numeric)
    estimator = estimator_cls(
        early_stopping=False, random_state=model_seed, categorical_features=mask, **parameters
    )
    return Pipeline([("encode", encode), ("model", estimator)])
