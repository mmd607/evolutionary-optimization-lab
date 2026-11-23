"""Tests for environment metadata capture."""

from __future__ import annotations

import hashlib
import platform
from pathlib import Path

import pytest

from evooptlab.utils import environment
from evooptlab.utils.environment import capture_environment, file_sha256, git_info


def test_capture_environment_basic_fields() -> None:
    env = capture_environment()
    assert env.python_version == platform.python_version()
    assert env.packages["pydantic"] is not None
    assert env.packages_lock_hash is None


def test_untracked_packages_are_none() -> None:
    versions = environment.package_versions(("definitely-not-installed-pkg-xyz",))
    assert versions == {"definitely-not-installed-pkg-xyz": None}


def test_lock_file_hash(tmp_path: Path) -> None:
    lock = tmp_path / "lock.txt"
    lock.write_bytes(b"pydantic==2.0\n")
    env = capture_environment(lock_file=lock)
    assert env.packages_lock_hash == hashlib.sha256(b"pydantic==2.0\n").hexdigest()
    assert file_sha256(lock) == env.packages_lock_hash


def test_missing_lock_file_is_none(tmp_path: Path) -> None:
    assert capture_environment(lock_file=tmp_path / "missing.txt").packages_lock_hash is None


def test_git_info_inside_repo(repo_root: Path) -> None:
    info = git_info(repo_root)
    if info.commit is None:
        pytest.skip("git or repository metadata unavailable (e.g. source archive)")
    assert len(info.commit) == 40
    assert info.dirty in (True, False)


def test_git_info_outside_repo(tmp_path: Path) -> None:
    info = git_info(tmp_path)
    assert info.commit is None
    assert info.dirty is None


def test_git_info_without_git_binary(monkeypatch: pytest.MonkeyPatch, repo_root: Path) -> None:
    monkeypatch.setattr("evooptlab.utils.environment.shutil.which", lambda _name: None)
    assert git_info(repo_root).commit is None
