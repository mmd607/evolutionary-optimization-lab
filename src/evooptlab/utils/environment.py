"""Capture software, hardware, and source-control metadata for reproducibility records."""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from pydantic import BaseModel, ConfigDict

#: Packages whose versions are recorded with every run when installed.
TRACKED_PACKAGES: tuple[str, ...] = (
    "evooptlab",
    "numpy",
    "scipy",
    "pandas",
    "scikit-learn",
    "pymoo",
    "optuna",
    "pydantic",
    "PyYAML",
)


class GitInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    commit: str | None
    dirty: bool | None
    branch: str | None


class EnvironmentInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    python_version: str
    python_implementation: str
    platform: str
    machine: str
    processor: str
    cpu_count: int | None
    packages: dict[str, str | None]
    git: GitInfo
    packages_lock_hash: str | None


def _run_git(args: list[str], cwd: Path) -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    try:
        result = subprocess.run(
            [git, *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None
    return result.stdout.strip()


def git_info(repo_root: Path | None = None) -> GitInfo:
    """Return the current commit, dirty flag, and branch, or ``None`` fields outside a repo."""
    cwd = repo_root if repo_root is not None else Path.cwd()
    commit = _run_git(["rev-parse", "HEAD"], cwd)
    if commit is None:
        return GitInfo(commit=None, dirty=None, branch=None)
    status = _run_git(["status", "--porcelain", "--untracked-files=no"], cwd)
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    return GitInfo(
        commit=commit,
        dirty=None if status is None else bool(status),
        branch=branch,
    )


def package_versions(names: tuple[str, ...] = TRACKED_PACKAGES) -> dict[str, str | None]:
    """Return installed versions for ``names``; missing packages map to ``None``."""
    versions: dict[str, str | None] = {}
    for name in names:
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            versions[name] = None
    return versions


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def capture_environment(
    repo_root: Path | None = None,
    lock_file: Path | None = None,
) -> EnvironmentInfo:
    """Collect environment metadata. Never raises for missing optional information."""
    lock_hash = file_sha256(lock_file) if lock_file is not None and lock_file.is_file() else None
    return EnvironmentInfo(
        python_version=platform.python_version(),
        python_implementation=platform.python_implementation(),
        platform=platform.platform(),
        machine=platform.machine(),
        processor=platform.processor() or "unknown",
        cpu_count=os.cpu_count(),
        packages=package_versions(),
        git=git_info(repo_root),
        packages_lock_hash=lock_hash,
    )
