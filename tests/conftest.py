import shutil
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A copy of the repo's schemas, roles, profiles and suites that a test may mutate."""
    for folder in ("schemas", "roles", "profiles", "suites"):
        shutil.copytree(REPO / folder, tmp_path / folder)
    return tmp_path


def edit_yaml(path: Path, change) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
