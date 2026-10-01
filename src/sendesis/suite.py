"""Qualification suites: one folder per case under `<suite>/cases/`.

Layout and labels are described in `suites/security-reviewer/README.md`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

from sendesis.model import ValidationFailed


@dataclass(frozen=True)
class Label:
    cwe: str
    file: str
    line_start: int
    line_end: int


@dataclass(frozen=True)
class Case:
    id: str
    clean: bool
    labels: tuple[Label, ...]
    diff: str
    context: dict[str, str]


@dataclass(frozen=True)
class Suite:
    path: Path
    cases: tuple[Case, ...]
    sha256: str


def suite_sha256(cases_dir: Path) -> str:
    """Hash of every file under `cases/`: relative path plus content hash, in path order."""
    h = hashlib.sha256()
    for path in sorted(p for p in cases_dir.rglob("*") if p.is_file()):
        h.update(path.relative_to(cases_dir).as_posix().encode() + b"\0")
        h.update(hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def _load_case(d: Path) -> tuple[Case | None, list[str]]:
    where = f"{d.parent.parent.name}/cases/{d.name}"
    try:
        data = yaml.safe_load((d / "case.yaml").read_text(encoding="utf-8"))
        diff = (d / "diff.patch").read_text(encoding="utf-8")
    except (OSError, yaml.YAMLError) as exc:
        return None, [f"{where}: {exc}"]
    errors = []
    if not isinstance(data, dict):
        return None, [f"{where}: case.yaml is not a mapping"]
    if data.get("id") != d.name:
        errors.append(f"{where}: id '{data.get('id')}' does not match folder name")
    clean = data.get("clean")
    if not isinstance(clean, bool):
        errors.append(f"{where}: clean must be true or false")
    raw_labels = data.get("labels") or []
    labels = []
    for i, lab in enumerate(raw_labels):
        try:
            label = Label(str(lab["cwe"]), str(lab["file"]), int(lab["line_start"]), int(lab["line_end"]))
        except (KeyError, TypeError, ValueError):
            errors.append(f"{where}: labels[{i}] needs cwe, file, line_start and line_end")
            continue
        if label.line_end < label.line_start:
            errors.append(f"{where}: labels[{i}] line_end is before line_start")
        labels.append(label)
    if clean is True and labels:
        errors.append(f"{where}: a clean case must have no labels")
    if clean is False and not raw_labels:
        errors.append(f"{where}: a vulnerable case needs at least one label")
    if errors:
        return None, errors
    ctx_dir = d / "context"
    context = {}
    if ctx_dir.is_dir():
        for p in sorted(ctx_dir.rglob("*")):
            if p.is_file():
                context[p.relative_to(ctx_dir).as_posix()] = p.read_text(encoding="utf-8", errors="replace")
    return Case(d.name, clean, tuple(labels), diff, context), []


def load_suite(path: Path) -> Suite:
    cases_dir = path / "cases"
    folders = sorted(p for p in cases_dir.iterdir() if p.is_dir()) if cases_dir.is_dir() else []
    if not folders:
        raise ValidationFailed([f"{path}: no cases under {cases_dir}"])
    cases, errors = [], []
    for d in folders:
        case, errs = _load_case(d)
        errors.extend(errs)
        if case:
            cases.append(case)
    if errors:
        raise ValidationFailed(errors)
    return Suite(path, tuple(cases), suite_sha256(cases_dir))
