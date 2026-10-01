from pathlib import Path

import pytest
import yaml

from sendesis.model import ValidationFailed
from sendesis.validate import validate_repo
from sendesis.workflow import load_workflow

REVIEW_CODE = {
    "id": "review-code",
    "version": "0.1.0",
    "description": "Blind review of a range of commits.",
    "stages": [
        {
            "id": "review",
            "seats": [{"role": "security-reviewer", "count": 2, "distinct_families": 2, "blind": True}],
            "loops": {"max_rounds": 1, "stop_rule": "no_new_confirmed_finding"},
            "gate": {"on": False, "answers": ["approve", "reject"]},
            "evidence": ["diff", "files_in_scope"],
            "network": "none",
        }
    ],
}


def write(root: Path, data: dict) -> Path:
    (root / "workflows").mkdir(exist_ok=True)
    path = root / "workflows" / f"{data['id']}.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


def test_workflow_loads(root: Path):
    wf = load_workflow(write(root, REVIEW_CODE), root)
    stage = wf.stages[0]
    assert wf.id == "review-code" and stage.seats[0].distinct_families == 2 and stage.seats[0].blind
    assert stage.network == "none" and stage.skippable is True


def test_network_only_none_or_loopback(root: Path):
    bad = {**REVIEW_CODE, "stages": [{**REVIEW_CODE["stages"][0], "network": "open"}]}
    with pytest.raises(ValidationFailed):
        load_workflow(write(root, bad), root)


def test_unknown_role_in_seat_fails_validate(root: Path):
    bad = {**REVIEW_CODE, "stages": [{**REVIEW_CODE["stages"][0], "seats": [{"role": "nobody"}]}]}
    write(root, bad)
    errors = validate_repo(root).errors
    assert any("review-code.yaml" in e and "nobody" in e for e in errors)


def test_distinct_families_cannot_exceed_count(root: Path):
    seat = {"role": "security-reviewer", "count": 1, "distinct_families": 2, "blind": True}
    bad = {**REVIEW_CODE, "stages": [{**REVIEW_CODE["stages"][0], "seats": [seat]}]}
    write(root, bad)
    errors = validate_repo(root).errors
    assert any("distinct_families" in e for e in errors)
