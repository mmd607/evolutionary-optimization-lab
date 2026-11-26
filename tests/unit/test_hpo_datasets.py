"""Dataset catalogue: provenance, verified fetching, and parsing of synthetic archives."""

from __future__ import annotations

import io
import tarfile
import zipfile
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from evooptlab.hpo import datasets
from evooptlab.hpo.datasets import CATALOG, DatasetError, SourceFile


def test_every_catalogued_task_is_pinned_and_cited() -> None:
    assert set(CATALOG) == {
        "breast_cancer_smoke",
        "wine_quality",
        "bank_marketing",
        "california_housing",
    }
    for task in CATALOG.values():
        assert task.integrity_sha256 is not None and len(task.integrity_sha256) == 64
        assert task.license and task.citation and task.loader_version.startswith(task.name)
        record = task.provenance()
        assert record["task"] == task.name
    assert "unverified" in CATALOG["california_housing"].license
    assert any("duration" in note for note in CATALOG["bank_marketing"].notes)


def test_bundled_task_loads_and_matches_its_content_hash(tmp_path: Path) -> None:
    data = datasets.load("breast_cancer_smoke", None, tmp_path)
    assert (data.n_rows, len(data.feature_names)) == (569, 30)
    assert datasets.fetch("breast_cancer_smoke", tmp_path) is None
    assert not any(tmp_path.iterdir())  # bundled data are never copied into the cache


def test_unknown_task_and_bad_variants(tmp_path: Path) -> None:
    with pytest.raises(DatasetError, match="unknown HPO task"):
        datasets.load("iris", None, tmp_path)
    with pytest.raises(DatasetError, match="needs a variant"):
        datasets.load("wine_quality", None, tmp_path)
    with pytest.raises(DatasetError, match="has no variants"):
        datasets.load("breast_cancer_smoke", "red", tmp_path)


def _with_source(monkeypatch: pytest.MonkeyPatch, name: str, payload: bytes) -> SourceFile:
    import hashlib

    source = SourceFile(
        url="https://example.invalid/data.bin",
        filename="data.bin",
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
    )
    monkeypatch.setitem(CATALOG, name, replace(CATALOG[name], source=source))
    return source


class TestFetch:
    def test_downloads_once_verifies_and_never_overwrites(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = b"raw bytes"
        _with_source(monkeypatch, "wine_quality", payload)
        calls: list[str] = []

        def opener(url: str) -> bytes:
            calls.append(url)
            return payload

        path = datasets.fetch("wine_quality", tmp_path, opener=opener)
        assert path == tmp_path / "raw" / "wine_quality" / "data.bin"
        assert path.read_bytes() == payload
        assert datasets.fetch("wine_quality", tmp_path, opener=opener) == path
        assert calls == ["https://example.invalid/data.bin"]  # cached copy reused

    def test_corrupted_download_is_rejected_before_writing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _with_source(monkeypatch, "wine_quality", b"expected")
        with pytest.raises(DatasetError, match="integrity check failed"):
            datasets.fetch("wine_quality", tmp_path, opener=lambda url: b"tampered")
        assert not (tmp_path / "raw").exists()

    def test_corrupted_cache_is_reported_and_kept(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _with_source(monkeypatch, "wine_quality", b"expected")
        cached = tmp_path / "raw" / "wine_quality" / "data.bin"
        cached.parent.mkdir(parents=True)
        cached.write_bytes(b"tampered")
        with pytest.raises(DatasetError, match="integrity check failed"):
            datasets.fetch("wine_quality", tmp_path, opener=lambda url: b"expected")
        with pytest.raises(DatasetError, match="integrity check failed"):
            datasets.load("wine_quality", "red", tmp_path)
        assert cached.read_bytes() == b"tampered"

    def test_missing_cache_tells_how_to_fetch(self, tmp_path: Path) -> None:
        with pytest.raises(DatasetError, match="evooptlab data fetch bank_marketing"):
            datasets.load("bank_marketing", None, tmp_path)


def _zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buffer.getvalue()


WINE_HEADER = '"fixed acidity";"alcohol";"quality"\n'


def test_wine_parser_variants() -> None:
    raw = _zip(
        {
            "winequality-red.csv": (WINE_HEADER + "7.4;9.4;5\n7.8;9.8;6\n").encode(),
            "winequality-white.csv": (WINE_HEADER + "7.0;8.8;6\n").encode(),
        }
    )
    red = CATALOG["wine_quality"].parse(raw, "red")
    assert red.X.tolist() == [[7.4, 9.4], [7.8, 9.8]] and red.y.tolist() == [5, 6]
    both = CATALOG["wine_quality"].parse(raw, "combined")
    assert both.feature_names[-1] == "is_red"
    assert both.X[:, -1].tolist() == [1.0, 1.0, 0.0]
    assert both.y.tolist() == [5, 6, 6]
    with pytest.raises(DatasetError, match="variant"):
        CATALOG["wine_quality"].parse(raw, "rose")
    with pytest.raises(DatasetError, match="no member"):
        CATALOG["wine_quality"].parse(_zip({"other.csv": b"x"}), "red")


BANK_HEADER = (
    '"age";"job";"marital";"education";"default";"housing";"loan";"contact";"month";'
    '"day_of_week";"duration";"campaign";"pdays";"previous";"poutcome";"emp.var.rate";'
    '"cons.price.idx";"cons.conf.idx";"euribor3m";"nr.employed";"y"\n'
)
BANK_ROW = (
    '56;"housemaid";"married";"basic.4y";"no";"no";"no";"telephone";"may";"mon";261;1;999;0;'
    '"nonexistent";1.1;93.994;-36.4;4.857;5191;"{y}"\n'
)


def _bank(rows: str) -> bytes:
    inner = _zip({"bank-additional/bank-additional-full.csv": (BANK_HEADER + rows).encode()})
    return _zip({"bank-additional.zip": inner, "bank.zip": b""})


def test_bank_parser_drops_duration_and_keeps_categories() -> None:
    data = CATALOG["bank_marketing"].parse(
        _bank(BANK_ROW.format(y="no") + BANK_ROW.format(y="yes")), None
    )
    assert "duration" not in data.feature_names
    assert len(data.feature_names) == 19
    assert [data.feature_names[i] for i in data.categorical_features] == list(
        datasets.BANK_CATEGORICAL
    )
    assert data.y.tolist() == [0, 1]
    assert data.X[0, data.feature_names.index("job")] == "housemaid"
    assert data.X[0, data.feature_names.index("age")] == 56.0
    with pytest.raises(DatasetError, match="labels"):
        CATALOG["bank_marketing"].parse(_bank(BANK_ROW.format(y="maybe")), None)


def test_california_parser_matches_sklearn_feature_definitions() -> None:
    # raw column order: longitude, latitude, age, rooms, bedrooms, population, households,
    # income, value
    line = "-122.23,37.88,41,880,129,322,126,8.3252,452600\n"
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tf:
        payload = (line * 2).encode()
        info = tarfile.TarInfo("CaliforniaHousing/cal_housing.data")
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))
    data = CATALOG["california_housing"].parse(buffer.getvalue(), None)
    np.testing.assert_allclose(
        data.X[0], [8.3252, 41, 880 / 126, 129 / 126, 322, 322 / 126, 37.88, -122.23]
    )
    assert data.y[0] == pytest.approx(4.526)
