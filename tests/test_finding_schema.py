import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

SCHEMA = json.loads((Path(__file__).resolve().parent.parent / "schemas" / "finding.json").read_text())
V = Draft202012Validator(SCHEMA)

FINDING = {
    "id": "F-1", "claim": "User input reaches the SQL string unescaped.", "category": "CWE-89",
    "severity": "blocking", "impact": "high", "claim_status": "proven",
    "location": {"file": "app/db.py", "line_start": 42, "line_end": 44},
    "evidence": [{"kind": "code_quote", "file": "app/db.py", "line_start": 42, "line_end": 42, "text": "q = 'SELECT ' + name"}],
}


def output(**over):
    return {"role_id": "security-reviewer", "findings": [FINDING], "checks": [{"id": "injection", "outcome": "findings"}], **over}


def test_v2_output_validates():
    assert list(V.iter_errors(output())) == []


def test_empty_findings_with_checks_validate():
    assert list(V.iter_errors(output(findings=[], checks=[{"id": "injection", "outcome": "no_findings"}]))) == []


@pytest.mark.parametrize("severity", ["critical", "high"])
def test_v1_severities_are_rejected(severity):
    bad = output(findings=[{**FINDING, "severity": severity}])
    assert list(V.iter_errors(bad))


def test_checks_are_required():
    bad = output()
    bad.pop("checks")
    assert list(V.iter_errors(bad))


def test_unknown_evidence_kind_is_rejected():
    bad = output(findings=[{**FINDING, "evidence": [{"kind": "reasoning", "text": "trust me"}]}])
    assert list(V.iter_errors(bad))


def test_schema_has_no_conditional_keywords():
    text = json.dumps(SCHEMA)
    for word in ('"allOf"', '"if"', '"then"', '"oneOf"', '"format"'):
        assert word not in text
