"""Load YAML configuration files into validated models."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from evooptlab.config.schemas import (
    AnalysisPlanFile,
    AnyConfig,
    BenchmarksFile,
    ExperimentsFile,
    HPOTasksFile,
    ReportingFile,
    StudyFile,
    unresolved_fields,
)

_SCHEMAS_BY_ROOT_KEY: dict[str, type[AnyConfig]] = {
    "benchmark_suite": BenchmarksFile,
    "experiment": ExperimentsFile,
    "hpo": HPOTasksFile,
    "study": StudyFile,
    "analysis_plan": AnalysisPlanFile,
    "reporting": ReportingFile,
}


class ConfigError(ValueError):
    """Raised when a configuration file is missing, malformed, or invalid."""


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Read a YAML file whose top level must be a mapping."""
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {file_path}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {file_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{file_path}: top level must be a mapping, got {type(data).__name__}")
    return data


def load_config(path: str | Path, *, strict: bool = False) -> AnyConfig:
    """Load and validate a config file, choosing the schema from its single top-level key.

    Args:
        path: Path to a YAML file in the ``configs/`` format.
        strict: If true, reject configs that still contain placeholder values (unresolved
            protocol decisions). Use strict mode for final, pre-registered runs.

    Raises:
        ConfigError: If the file cannot be read, has an unknown structure, fails validation, or
            (in strict mode) contains unresolved decisions.
    """
    file_path = Path(path)
    data = load_yaml(file_path)
    if len(data) != 1:
        raise ConfigError(
            f"{file_path}: expected exactly one top-level key out of "
            f"{sorted(_SCHEMAS_BY_ROOT_KEY)}, got {sorted(data)}"
        )
    (root_key,) = data
    schema = _SCHEMAS_BY_ROOT_KEY.get(root_key)
    if schema is None:
        raise ConfigError(
            f"{file_path}: unknown top-level key {root_key!r}; "
            f"expected one of {sorted(_SCHEMAS_BY_ROOT_KEY)}"
        )
    try:
        config = schema.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"{file_path}: invalid configuration\n{exc}") from exc

    if strict:
        unresolved = unresolved_fields(config)
        if unresolved:
            details = ", ".join(f"{field}={value!r}" for field, value in unresolved)
            raise ConfigError(f"{file_path}: unresolved decisions in strict mode: {details}")
    return config


def config_hash(config: BaseModel) -> str:
    """Return a stable SHA-256 hex digest of a validated config.

    The hash is computed over canonical JSON (sorted keys, no whitespace), so it is independent
    of YAML formatting, comments, and key order.
    """
    canonical = json.dumps(config.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
