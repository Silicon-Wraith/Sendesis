from pathlib import Path

import pytest

from sendesis.model import ValidationFailed
from sendesis.scoring import CaseOutcome, bootstrap_mean_ci, compute_metrics, matches, wilson
from sendesis.suite import Label, load_suite

DIFF = "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"


def write_case(suite: Path, case_id: str, *, clean: bool, labels: list[dict] | None = None, context: dict | None = None):
    d = suite / "cases" / case_id
    (d / "context").mkdir(parents=True)
    labels = labels if labels is not None else ([] if clean else [{"cwe": "CWE-89", "file": "app.py", "line_start": 10, "line_end": 12}])
    lines = [f"id: {case_id}", "source: planted", f"clean: {'true' if clean else 'false'}", "labels:" + (" []" if not labels else "")]
    for lab in labels:
        lines += [f"  - cwe: {lab['cwe']}", f"    file: {lab['file']}", f"    line_start: {lab['line_start']}", f"    line_end: {lab['line_end']}"]
    (d / "case.yaml").write_text("\n".join(lines) + "\n")
    (d / "diff.patch").write_text(DIFF)
    for rel, text in (context or {"app.py": "x = 2\n"}).items():
        (d / "context" / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / "context" / rel).write_text(text)
    return d


# ---- suite ------------------------------------------------------------------------


def test_load_suite_reads_cases_in_order(tmp_path):
    write_case(tmp_path, "b-vuln", clean=False)
    write_case(tmp_path, "a-clean", clean=True)
    suite = load_suite(tmp_path)
    assert [c.id for c in suite.cases] == ["a-clean", "b-vuln"]
    vuln = suite.cases[1]
    assert vuln.labels == (Label("CWE-89", "app.py", 10, 12),)
    assert vuln.diff == DIFF
    assert vuln.context == {"app.py": "x = 2\n"}
    assert len(suite.sha256) == 64


def test_suite_hash_changes_with_any_case_file(tmp_path):
    d = write_case(tmp_path, "v1", clean=False)
    before = load_suite(tmp_path).sha256
    (d / "context" / "app.py").write_text("x = 3\n")
    assert load_suite(tmp_path).sha256 != before


def test_clean_case_with_labels_fails(tmp_path):
    write_case(tmp_path, "c1", clean=True, labels=[{"cwe": "CWE-79", "file": "a.py", "line_start": 1, "line_end": 1}])
    with pytest.raises(ValidationFailed) as exc:
        load_suite(tmp_path)
    assert any("c1" in m and "clean" in m for m in exc.value.messages)


def test_vulnerable_case_without_labels_fails(tmp_path):
    write_case(tmp_path, "v1", clean=False, labels=[])
    with pytest.raises(ValidationFailed) as exc:
        load_suite(tmp_path)
    assert any("v1" in m and "label" in m for m in exc.value.messages)


def test_case_id_must_match_folder(tmp_path):
    d = write_case(tmp_path, "v1", clean=False)
    (d / "case.yaml").write_text((d / "case.yaml").read_text().replace("id: v1", "id: other"))
    with pytest.raises(ValidationFailed):
        load_suite(tmp_path)


def test_empty_suite_fails(tmp_path):
    (tmp_path / "cases").mkdir()
    with pytest.raises(ValidationFailed):
        load_suite(tmp_path)


# ---- matching -------------------------------------------------------------------------


def finding(file="app.py", start=10, end=12, category="CWE-89"):
    loc = {"file": file}
    if start is not None:
        loc["line_start"] = start
    if end is not None:
        loc["line_end"] = end
    return {"id": "f", "claim": "a claim", "category": category, "severity": "high", "location": loc, "evidence": [{"kind": "quote", "content": "x"}]}


LABEL = Label("CWE-89", "app.py", 10, 12)


@pytest.mark.parametrize(
    "f, expected",
    [
        (finding(), True),
        (finding(start=15, end=15), True),  # 3 lines of slack after line 12
        (finding(start=16, end=20), False),
        (finding(start=5, end=7), True),  # 3 lines of slack before line 10
        (finding(start=1, end=6), False),
        (finding(file="other.py"), False),
        (finding(file="./app.py"), True),  # path spelling normalized
        (finding(file="b/app.py"), True),  # diff prefix normalized
        (finding(start=None, end=None), False),  # no lines, no match
        (finding(start=11, end=None), True),  # line_end defaults to line_start
    ],
)
def test_finding_matches_label_with_three_lines_slack(f, expected):
    assert matches(f, LABEL) is expected


# ---- intervals -------------------------------------------------------------------------


def test_wilson_known_values():
    lo, hi = wilson(6, 10)
    assert lo == pytest.approx(0.3127, abs=1e-4)
    assert hi == pytest.approx(0.8318, abs=1e-4)


def test_wilson_edges():
    assert wilson(0, 10)[0] == 0.0
    assert wilson(10, 10)[1] == pytest.approx(1.0)


def test_bootstrap_is_deterministic_and_brackets_mean():
    values = [0, 0, 1, 0, 2, 0, 0, 1, 0, 0]
    lo, hi = bootstrap_mean_ci(values)
    assert (lo, hi) == bootstrap_mean_ci(values)
    assert lo <= 0.4 <= hi


# ---- metrics ---------------------------------------------------------------------------


def outcome(case_id, clean, labels, findings, valid=True, returned=True):
    return CaseOutcome(case_id, clean, tuple(labels), findings if valid else [], valid=valid, returned=returned)


def test_compute_metrics():
    outcomes = [
        outcome("v1", False, [LABEL], [finding()]),  # hit
        outcome("v2", False, [LABEL, Label("CWE-22", "b.py", 1, 2)], [finding()]),  # 1 of 2
        outcome("v3", False, [LABEL], [], valid=False),  # invalid output: miss
        outcome("c1", True, [], [finding(), finding()]),  # 2 false positives
        outcome("c2", True, [], []),
        outcome("c3", True, [], [], returned=False),  # call failed, nothing returned
    ]
    m = compute_metrics(outcomes)
    assert m["recall"].value == pytest.approx(2 / 4)
    assert m["false_positives_per_clean_case"].value == pytest.approx(2 / 2)  # over clean cases that returned
    assert m["schema_validity"].value == pytest.approx(4 / 5)
    assert m["category_agreement"].value == pytest.approx(1.0)
    assert m["recall"].ci_method == "wilson"
    assert m["false_positives_per_clean_case"].ci_method == "bootstrap"
