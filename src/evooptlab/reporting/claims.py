"""Claims audit for the manuscript (Phase 06 gate, ADR 0007).

Manuscript conventions (``reports/paper/manuscript.md``)
-------------------------------------------------------
* Front matter: ``---`` / ``status: draft|final`` / ``---``.
* **Numbers that are results** are never typed. They are written as ``{{value:KEY}}`` or
  ``{{value:KEY:FORMAT}}`` and resolved from ``values.json`` files that ``evooptlab report``
  generates. In result sections (Abstract, Results, Discussion, Ablation, Conclusion) a bare
  number is an error. Structural references such as "Table 2", "RQ1", "P8" or "ADR 0005" are
  allowed.
* **Citations** are ``[@key]``. The key must be a row of ``docs/literature/literature_matrix.csv``
  with ``verified = yes``.
* **Substantive claims** carry ``<!-- claim: ID -->``. Each ID needs a row in the claim-evidence
  matrix (``claim_evidence.csv``: ``claim_id, section, claim, evidence_type, evidence_ref,
  status``) whose evidence exists:
  - a repository path (``code``, ``adr``, ``config``, ``test``, ``doc``);
  - a ``values.json`` key (``value``);
  - a verified literature key (``literature``).
  ``status: pending`` marks evidence that does not exist yet.
* A draft with pending results must say ``DRAFT — RESULTS PENDING``. A final manuscript must
  contain no pending claim, unresolved value, preliminary value, or "RESULTS PENDING".

The audit is mechanical. It cannot judge whether a citation supports a sentence, so that remains
a human review step, which the report says.
"""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Severity = Literal["FAIL", "WARN"]
RESULT_SECTIONS = ("abstract", "results", "discussion", "ablation", "conclusion")
PENDING_MARK = "DRAFT — RESULTS PENDING"
EVIDENCE_TYPES = ("code", "adr", "config", "test", "doc", "value", "literature")
#: Unsupported superlatives (docs/paper_writing_guide.md section 2).
HYPE = re.compile(
    r"\b(novel|state[- ]of[- ]the[- ]art|revolutionary|excellent|highly accurate|groundbreaking|"
    r"unprecedented|best[- ]in[- ]class)\b",
    re.IGNORECASE,
)
SIGNIFICANT = re.compile(r"\bsignificant(ly)?\b", re.IGNORECASE)
VALUE = re.compile(r"\{\{value:([^}:]+)(?::([^}]+))?\}\}")
CITATION = re.compile(r"\[@([A-Za-z0-9_:\-]+)\]")
CLAIM = re.compile(r"<!--\s*claim:\s*([A-Za-z0-9_\-]+)\s*-->")
NUMBER = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?%?")
STRUCTURAL = re.compile(
    r"\b(?:Table|Figure|Fig\.|Section|RQ|P|D|ADR|H|Phase|Stage|Eq\.)\s?\d+[a-z]?\b"
)


@dataclass(frozen=True)
class Finding:
    severity: Severity
    line: int
    rule: str
    message: str


@dataclass
class AuditReport:
    status: Literal["PASS", "WARN", "FAIL"]
    manuscript_status: str
    findings: list[Finding] = field(default_factory=list)
    n_claims: int = 0
    n_citations: int = 0
    n_values: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "manuscript_status": self.manuscript_status,
            "n_claims": self.n_claims,
            "n_citations": self.n_citations,
            "n_values": self.n_values,
            "findings": [f.__dict__ for f in self.findings],
            "human_review_required": (
                "Whether each cited source supports its sentence is not machine-checkable."
            ),
        }


def _front_matter(lines: list[str]) -> tuple[dict[str, str], int]:
    if not lines or lines[0].strip() != "---":
        return {}, 0
    meta: dict[str, str] = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return meta, i + 1
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta, 0


def load_literature(path: Path) -> dict[str, bool]:
    """``paper_id -> verified`` from the literature matrix."""
    rows = csv.DictReader(path.read_text(encoding="utf-8").splitlines())
    return {r["paper_id"]: r.get("verified", "").strip().lower() == "yes" for r in rows}


def load_values(paths: Iterable[Path]) -> dict[str, dict[str, Any]]:
    store: dict[str, dict[str, Any]] = {}
    for path in paths:
        store.update(json.loads(path.read_text(encoding="utf-8")))
    return store


def load_matrix(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))


def _strip(line: str) -> str:
    """Line text without value references, citations, claim markers and inline code."""
    line = VALUE.sub(" ", line)
    line = CITATION.sub(" ", line)
    line = re.sub(r"<!--.*?-->", " ", line)  # comments, including claim markers
    line = re.sub(r"`[^`]*`", " ", line)
    line = re.sub(r"\]\([^)]*\)", "]", line)  # link targets
    return STRUCTURAL.sub(" ", line)


def audit(
    manuscript: Path,
    *,
    matrix: Path,
    literature: Path,
    values: Sequence[Path] = (),
    repo_root: Path,
) -> AuditReport:
    text = manuscript.read_text(encoding="utf-8")
    lines = text.splitlines()
    meta, body_start = _front_matter(lines)
    status = meta.get("status", "")
    final = status == "final"
    lit = load_literature(literature)
    store = load_values(values)
    rows = load_matrix(matrix)
    findings: list[Finding] = []

    def add(severity: Severity, line: int, rule: str, message: str) -> None:
        findings.append(Finding(severity, line, rule, message))

    if status not in ("draft", "final"):
        add("FAIL", 1, "front_matter", "front matter must set status: draft or final")

    section = ""
    in_code = in_comment = False
    seen_claims: dict[str, int] = {}
    n_citations = n_values = 0
    for number, line in enumerate(lines[body_start:], start=body_start + 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        for claim_id in CLAIM.findall(line):
            seen_claims.setdefault(claim_id, number)
        if "<!--" in line and "-->" not in line:
            in_comment = True
        if in_comment:
            in_comment = "-->" not in line
            continue
        if in_code:
            continue
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            if level <= 2:  # subsections stay inside their section's rules
                section = re.sub(r"^#+\s*(\d+(\.\d+)*\.?\s*)?", "", stripped).lower()
            continue
        code_free = re.sub(r"`[^`]*`", " ", line)  # examples in inline code are not references
        for key in CITATION.findall(code_free):
            n_citations += 1
            if key not in lit:
                add("FAIL", number, "citation", f"[@{key}] is not in the literature matrix")
            elif not lit[key]:
                add("FAIL", number, "citation", f"[@{key}] is not verified (verified != yes)")
        for key, _fmt in VALUE.findall(code_free):
            n_values += 1
            entry = store.get(key)
            if entry is None:
                add("FAIL" if final else "WARN", number, "value", f"unresolved value {key!r}")
            elif final and entry.get("preliminary"):
                add("FAIL", number, "value", f"{key!r} is preliminary; not allowed in final")
        hype = HYPE.search(line)
        if hype:
            add("FAIL", number, "wording", f"unsupported superlative: {hype.group(0)!r}")
        if SIGNIFICANT.search(line) and not re.search(r"\{\{value:[^}]*p_(holm|value)", line):
            add(
                "FAIL",
                number,
                "wording",
                "'significant' needs the corrected test result on the same line "
                "({{value:...p_holm}})",
            )
        if any(section.startswith(s) for s in RESULT_SECTIONS):
            bare = [m.group(0) for m in NUMBER.finditer(_strip(line))]
            if bare:
                add(
                    "FAIL",
                    number,
                    "number",
                    f"typed number(s) {bare} in a result section; use {{{{value:KEY}}}}",
                )
        if final and "RESULTS PENDING" in line:
            add("FAIL", number, "pending", "final manuscript still says RESULTS PENDING")

    findings += _audit_matrix(rows, seen_claims, lit, store, repo_root, final)
    if not final and any(r.get("status") == "pending" for r in rows) and PENDING_MARK not in text:
        add("FAIL", 1, "pending", f"draft with pending claims must state {PENDING_MARK!r}")

    worst = (
        "FAIL" if any(f.severity == "FAIL" for f in findings) else ("WARN" if findings else "PASS")
    )
    return AuditReport(
        status=worst,  # type: ignore[arg-type]
        manuscript_status=status,
        findings=sorted(findings, key=lambda f: (f.line, f.rule)),
        n_claims=len(seen_claims),
        n_citations=n_citations,
        n_values=n_values,
    )


def _audit_matrix(
    rows: list[dict[str, str]],
    seen: dict[str, int],
    lit: dict[str, bool],
    store: dict[str, dict[str, Any]],
    repo_root: Path,
    final: bool,
) -> list[Finding]:
    out: list[Finding] = []
    by_id: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_id.setdefault(row["claim_id"], []).append(row)
    for claim_id, line in seen.items():
        if claim_id not in by_id:
            out.append(Finding("FAIL", line, "claim", f"claim {claim_id} has no evidence row"))
    for claim_id, entries in by_id.items():
        line = seen.get(claim_id, 0)
        if claim_id not in seen:
            out.append(Finding("WARN", 0, "claim", f"evidence row {claim_id} is not cited"))
        for row in entries:
            kind, ref, state = row["evidence_type"], row["evidence_ref"], row["status"]
            if kind not in EVIDENCE_TYPES:
                out.append(Finding("FAIL", line, "evidence", f"{claim_id}: unknown type {kind!r}"))
                continue
            if state not in ("supported", "pending"):
                out.append(Finding("FAIL", line, "evidence", f"{claim_id}: bad status {state!r}"))
                continue
            if state == "pending":
                if final:
                    out.append(Finding("FAIL", line, "evidence", f"{claim_id}: still pending"))
                continue
            ok = (
                (kind == "literature" and lit.get(ref, False))
                or (kind == "value" and ref in store)
                or (kind not in ("literature", "value") and (repo_root / ref).exists())
            )
            if not ok:
                out.append(
                    Finding(
                        "FAIL", line, "evidence", f"{claim_id}: {kind} evidence {ref!r} not found"
                    )
                )
    return out


def render(text: str, store: dict[str, dict[str, Any]]) -> str:
    """Substitute ``{{value:KEY[:FORMAT]}}`` with stored values (missing keys stay visible)."""

    def replace(match: re.Match[str]) -> str:
        entry = store.get(match.group(1))
        if entry is None:
            return match.group(0)
        value, fmt = entry["value"], match.group(2)
        if value is None:
            return "—"
        return format(value, fmt) if fmt else str(value)

    return VALUE.sub(replace, text)
