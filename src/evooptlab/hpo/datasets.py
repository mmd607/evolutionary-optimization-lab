"""Catalogued tabular datasets for HPO tasks: provenance, verified downloads and parsing.

Rules (docs/dataset_and_benchmarks.md, ADR 0006)
-----------------------------------------------
* Raw files are never committed. They are cached under ``<data_dir>/raw/<task>/`` (gitignored).
* Every download is verified against the SHA-256 and byte size recorded here **before** it is
  moved into place, and every load re-verifies the cached file. A mismatch is an error, never a
  warning: a changed source silently changes every result.
* Archives are read in memory (``zipfile``/``tarfile`` members by exact name). Nothing is
  extracted to disk, so archive paths cannot escape the cache directory.
* The recorded checksums are those of the files downloaded on 2026-11-25. For California
  Housing the value also equals the checksum scikit-learn records for the same URL.
* Licences are as stated on the source pages on 2026-11-25. The California Housing source
  (StatLib, via scikit-learn) states none; it is marked unverified. Data are never
  redistributed by this project.
"""

from __future__ import annotations

import csv
import hashlib
import io
import tarfile
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

#: Generic client name for downloads (no personal or project details are sent).
USER_AGENT = "evooptlab-data-fetch"
DOWNLOAD_TIMEOUT_SECONDS = 60


class DatasetError(RuntimeError):
    """A dataset is unknown, missing, corrupted, or cannot be parsed."""


@dataclass(frozen=True)
class SourceFile:
    """A downloadable raw file with its recorded integrity values."""

    url: str
    filename: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class Dataset:
    """A parsed dataset. ``X`` is float64, or object dtype when categorical columns exist."""

    task: str
    variant: str | None
    X: npt.NDArray[Any]
    y: npt.NDArray[Any]
    feature_names: tuple[str, ...]
    categorical_features: tuple[int, ...]

    @property
    def n_rows(self) -> int:
        return int(self.X.shape[0])


@dataclass(frozen=True)
class TaskDefinition:
    """Catalogue entry: where the data come from and how they are parsed."""

    name: str
    title: str
    homepage: str
    license: str
    citation: str
    doi: str | None
    task_types: tuple[str, ...]
    #: Bumped whenever parsing changes; recorded in every run's config hash.
    loader_version: str
    parse: Callable[[bytes | None, str | None], Dataset]
    source: SourceFile | None = None
    #: For bundled data: SHA-256 of the parsed arrays (X float64 bytes, then y int64 bytes).
    content_sha256: str | None = None
    variants: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def integrity_sha256(self) -> str | None:
        """The checksum that pins this task's data (every catalogue entry has one)."""
        return self.source.sha256 if self.source is not None else self.content_sha256

    def provenance(self) -> dict[str, Any]:
        return {
            "task": self.name,
            "title": self.title,
            "homepage": self.homepage,
            "license": self.license,
            "citation": self.citation,
            "doi": self.doi,
            "loader_version": self.loader_version,
            "source": None
            if self.source is None
            else {
                "url": self.source.url,
                "filename": self.source.filename,
                "sha256": self.source.sha256,
                "size_bytes": self.source.size_bytes,
            },
            "content_sha256": self.content_sha256,
            "variants": list(self.variants),
            "task_types": list(self.task_types),
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------------------------
# Parsers (pure functions of the verified raw bytes)
# ---------------------------------------------------------------------------------------------
def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_sha256(X: npt.NDArray[Any], y: npt.NDArray[Any]) -> str:
    digest = hashlib.sha256()
    digest.update(np.ascontiguousarray(X, dtype=np.float64).tobytes())
    digest.update(np.ascontiguousarray(y, dtype=np.int64).tobytes())
    return digest.hexdigest()


def _zip_member(archive: bytes, member: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        try:
            return zf.read(member)
        except KeyError as exc:
            raise DatasetError(f"archive has no member {member!r}") from exc


def _semicolon_rows(text: str) -> tuple[list[str], list[list[str]]]:
    rows = list(csv.reader(io.StringIO(text), delimiter=";", quotechar='"'))
    if len(rows) < 2:
        raise DatasetError("CSV has no data rows")
    return rows[0], rows[1:]


def _parse_breast_cancer(raw: bytes | None, variant: str | None) -> Dataset:
    from sklearn.datasets import load_breast_cancer

    bunch = load_breast_cancer()
    return Dataset(
        task="breast_cancer_smoke",
        variant=None,
        X=np.asarray(bunch.data, dtype=np.float64),
        y=np.asarray(bunch.target, dtype=np.int64),
        feature_names=tuple(str(n) for n in bunch.feature_names),
        categorical_features=(),
    )


def _wine_part(archive: bytes, member: str) -> tuple[list[str], npt.NDArray[np.float64]]:
    header, rows = _semicolon_rows(_zip_member(archive, member).decode("utf-8"))
    return header, np.array(rows, dtype=np.float64)


def _parse_wine(raw: bytes | None, variant: str | None) -> Dataset:
    assert raw is not None
    if variant not in ("red", "white", "combined"):
        raise DatasetError("wine_quality needs variant 'red', 'white' or 'combined'")
    parts = []
    if variant in ("red", "combined"):
        parts.append(("red", *_wine_part(raw, "winequality-red.csv")))
    if variant in ("white", "combined"):
        parts.append(("white", *_wine_part(raw, "winequality-white.csv")))
    header = parts[0][1]
    if header[-1] != "quality" or any(p[1] != header for p in parts):
        raise DatasetError("unexpected wine_quality header")
    blocks, targets = [], []
    for colour, _, values in parts:
        features = values[:, :-1]
        if variant == "combined":
            is_red = np.full((features.shape[0], 1), 1.0 if colour == "red" else 0.0)
            features = np.hstack([features, is_red])
        blocks.append(features)
        targets.append(values[:, -1].astype(np.int64))
    names = tuple(header[:-1]) + (("is_red",) if variant == "combined" else ())
    return Dataset(
        task="wine_quality",
        variant=variant,
        X=np.vstack(blocks),
        y=np.concatenate(targets),
        feature_names=names,
        categorical_features=(),
    )


BANK_DROPPED = ("duration",)
BANK_CATEGORICAL = (
    "job",
    "marital",
    "education",
    "default",
    "housing",
    "loan",
    "contact",
    "month",
    "day_of_week",
    "poutcome",
)


def _parse_bank(raw: bytes | None, variant: str | None) -> Dataset:
    assert raw is not None
    inner = _zip_member(raw, "bank-additional.zip")
    text = _zip_member(inner, "bank-additional/bank-additional-full.csv").decode("utf-8")
    header, rows = _semicolon_rows(text)
    if header[-1] != "y" or not set(BANK_CATEGORICAL) | set(BANK_DROPPED) <= set(header):
        raise DatasetError("unexpected bank_marketing header")
    keep = [i for i, name in enumerate(header[:-1]) if name not in BANK_DROPPED]
    names = tuple(header[i] for i in keep)
    X = np.empty((len(rows), len(keep)), dtype=object)
    categorical = tuple(j for j, name in enumerate(names) if name in BANK_CATEGORICAL)
    for r, row in enumerate(rows):
        for j, i in enumerate(keep):
            X[r, j] = row[i] if j in categorical else float(row[i])
    labels = {row[-1] for row in rows}
    if labels != {"yes", "no"}:
        raise DatasetError(f"unexpected bank_marketing labels {sorted(labels)}")
    y = np.array([1 if row[-1] == "yes" else 0 for row in rows], dtype=np.int64)
    return Dataset("bank_marketing", None, X, y, names, categorical)


def _parse_california(raw: bytes | None, variant: str | None) -> Dataset:
    """Same features and target as ``sklearn.datasets.fetch_california_housing`` (1.9)."""
    assert raw is not None
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
        member = tf.extractfile("CaliforniaHousing/cal_housing.data")
        if member is None:
            raise DatasetError("archive has no cal_housing.data")
        values = np.loadtxt(io.BytesIO(member.read()), delimiter=",", dtype=np.float64)
    values = values[:, [8, 7, 2, 3, 4, 5, 6, 1, 0]]
    target, data = values[:, 0] / 100000.0, values[:, 1:].copy()
    data[:, 2] /= data[:, 5]  # average rooms per household
    data[:, 3] /= data[:, 5]  # average bedrooms per household
    data[:, 5] = data[:, 4] / data[:, 5]  # average occupancy
    names = (
        "MedInc",
        "HouseAge",
        "AveRooms",
        "AveBedrms",
        "Population",
        "AveOccup",
        "Latitude",
        "Longitude",
    )
    return Dataset("california_housing", None, data, target, names, ())


CC_BY_4 = "CC BY 4.0 (as stated on the UCI dataset page, 2026-11-25)"

CATALOG: dict[str, TaskDefinition] = {
    t.name: t
    for t in (
        TaskDefinition(
            name="breast_cancer_smoke",
            title="Breast Cancer Wisconsin (Diagnostic), bundled with scikit-learn",
            homepage="https://archive.ics.uci.edu/dataset/17/breast+cancer+wisconsin+diagnostic",
            license=CC_BY_4,
            citation="Wolberg, Mangasarian, Street, Street (1993). UCI ML Repository.",
            doi="10.24432/C5DW2B",
            task_types=("classification",),
            loader_version="breast_cancer_smoke/v1: sklearn.datasets.load_breast_cancer",
            parse=_parse_breast_cancer,
            content_sha256="25e2eb7b7a8745b1bde5ba18bc4969983d2e2f403291ecd5bde4a29ef30c3859",
            notes=("Pipeline smoke test only; must not drive conclusions.",),
        ),
        TaskDefinition(
            name="wine_quality",
            title="Wine Quality (red and white vinho verde)",
            homepage="https://archive.ics.uci.edu/dataset/186/wine+quality",
            license=CC_BY_4,
            citation="Cortez, Cerdeira, Almeida, Matos, Reis (2009). Decision Support Systems.",
            doi="10.24432/C56S3T",
            task_types=("classification", "regression"),
            loader_version="wine_quality/v1: target quality; combined adds is_red",
            parse=_parse_wine,
            source=SourceFile(
                url="https://archive.ics.uci.edu/static/public/186/wine+quality.zip",
                filename="wine+quality.zip",
                sha256="3ed56667f4b828242bd732d7d1dd7f2861e54432239d7fa63877014cbb0304d4",
                size_bytes=91353,
            ),
            variants=("red", "white", "combined"),
            notes=("Task type and variant are open owner decisions (P3).",),
        ),
        TaskDefinition(
            name="bank_marketing",
            title="Bank Marketing (bank-additional-full.csv)",
            homepage="https://archive.ics.uci.edu/dataset/222/bank+marketing",
            license=CC_BY_4,
            citation="Moro, Cortez, Rita (2014). Decision Support Systems 62:22-31.",
            doi="10.24432/C5K306",
            task_types=("classification",),
            loader_version="bank_marketing/v1: bank-additional-full.csv without duration",
            parse=_parse_bank,
            source=SourceFile(
                url="https://archive.ics.uci.edu/static/public/222/bank+marketing.zip",
                filename="bank+marketing.zip",
                sha256="e0bf5f5de5b846e2f18e9d90606637267d46dfa260e0f17bb12e605db5efbeb4",
                size_bytes=1023843,
            ),
            notes=(
                "'duration' is dropped: the source notes it is only known after the call and "
                "should be discarded for a realistic predictive model (target leakage).",
                "Rows are ordered by date (May 2008 - Nov 2010); a random split mixes periods "
                "(split strategy is an open owner decision, P4).",
                "'unknown' is kept as its own category, as the source suggests.",
            ),
        ),
        TaskDefinition(
            name="california_housing",
            title="California Housing (1990 census block groups), StatLib via scikit-learn",
            homepage="https://lib.stat.cmu.edu/datasets/houses.zip",
            license="not stated by the source (StatLib / scikit-learn); unverified",
            citation="Pace and Barry (1997). Statistics and Probability Letters 33:291-297.",
            doi=None,
            task_types=("regression",),
            loader_version="california_housing/v1: features and target as sklearn 1.9",
            parse=_parse_california,
            source=SourceFile(
                url="https://ndownloader.figshare.com/files/5976036",
                filename="cal_housing.tgz",
                sha256="aaa5c9a6afe2225cc2aed2723682ae403280c4a3695a2ddda4ffb5d8215ea681",
                size_bytes=441963,
            ),
            notes=("Target in units of 100 000 USD.",),
        ),
    )
}


# ---------------------------------------------------------------------------------------------
# Fetching and loading
# ---------------------------------------------------------------------------------------------
def get_task(name: str) -> TaskDefinition:
    try:
        return CATALOG[name]
    except KeyError as exc:
        raise DatasetError(f"unknown HPO task {name!r}; available: {', '.join(CATALOG)}") from exc


def raw_path(task: TaskDefinition, data_dir: Path) -> Path | None:
    if task.source is None:
        return None
    return Path(data_dir) / "raw" / task.name / task.source.filename


def _verify(data: bytes, source: SourceFile, where: str) -> None:
    if len(data) != source.size_bytes or _sha256(data) != source.sha256:
        raise DatasetError(
            f"{where}: integrity check failed (expected {source.size_bytes} bytes, sha256 "
            f"{source.sha256[:12]}...; got {len(data)} bytes, sha256 {_sha256(data)[:12]}...)"
        )


def fetch(
    name: str, data_dir: Path, *, opener: Callable[[str], bytes] | None = None
) -> Path | None:
    """Download a task's raw file into the cache if missing; verify it either way.

    Returns the cached path, or ``None`` for bundled datasets. An existing, valid file is never
    downloaded again; an existing, corrupted file is an error and is left in place for review.
    """
    task = get_task(name)
    path = raw_path(task, data_dir)
    if path is None or task.source is None:
        return None
    if path.exists():
        _verify(path.read_bytes(), task.source, str(path))
        return path
    data = (opener or _download)(task.source.url)
    _verify(data, task.source, task.source.url)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Verified in memory first; exclusive creation never replaces a file that appeared
    # meanwhile. An interrupted write leaves a file that fails the next verification.
    with path.open("xb") as handle:
        handle.write(data)
    return path


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        data: bytes = response.read()
    return data


def load(name: str, variant: str | None, data_dir: Path) -> Dataset:
    """Parse a task from its verified cached file (or the bundled copy)."""
    task = get_task(name)
    if task.variants and variant not in task.variants:
        raise DatasetError(f"{name} needs a variant from {list(task.variants)}, got {variant!r}")
    if not task.variants and variant is not None:
        raise DatasetError(f"{name} has no variants, got {variant!r}")
    raw: bytes | None = None
    path = raw_path(task, data_dir)
    if path is not None and task.source is not None:
        if not path.exists():
            raise DatasetError(
                f"{name}: raw file missing at {path}; run "
                f"`evooptlab data fetch {name} --data-dir {data_dir}` first"
            )
        raw = path.read_bytes()
        _verify(raw, task.source, str(path))
    dataset = task.parse(raw, variant)
    if task.content_sha256 is not None:
        actual = content_sha256(dataset.X, dataset.y)
        if actual != task.content_sha256:
            raise DatasetError(f"{name}: bundled data changed (sha256 {actual[:12]}...)")
    return dataset
