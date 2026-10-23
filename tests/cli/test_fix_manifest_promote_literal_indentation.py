"""Public promotion keeps valid literal YAML valid and migrates real lock evidence."""

import argparse
import sys
import textwrap
from pathlib import Path
from io import StringIO

import pytest
import yaml
from ruamel.yaml import YAML

from maid_runner.cli.commands.manifest import cmd_manifest
from maid_runner.cli.commands.plan import cmd_plan_lock
from maid_runner.core.plan_lock import PlanLock, default_plan_lock_path

_SLUG = "literal-promotion"
_DESCRIPTION = (
    "1. domain/t3_candidates.py (new, pure): PaperReason (copied, leader_sold_first,\n"
    "   buy_not_in_flows, pair_no_eth_value, no_price_path, pass_blocked); PaperDecision (the buy:\n"
    "- Out of scope: T3 challengers, a non-mirror T3 champion (none runs; the view in child 3 says"
)


def _draft(root: Path, *, problematic: bool = True) -> Path:
    (root / "manifests/drafts").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "a.py").write_text("def value() -> int:\n    return 0\n")
    (root / "tests/test_a.py").write_text(
        "from a import value\n\ndef test_value():\n    assert value() == 1\n"
    )
    rel = f"manifests/drafts/{_SLUG}.manifest.yaml"
    data = {
        "type": "fix",
        "files": {
            "edit": [
                {
                    "path": "a.py",
                    "artifacts": [
                        {
                            "kind": "function",
                            "name": "value",
                            "args": [],
                            "returns": "int",
                        }
                    ],
                }
            ],
            "read": ["tests/test_a.py"],
        },
        "validate": [
            [sys.executable, "-B", "-m", "pytest", "tests/test_a.py", "-q"],
            ["maid", "validate", rel, "--mode", "schema", "--quiet"],
        ],
    }
    description = (
        _DESCRIPTION
        if problematic
        else "Ordinary multiline description\nWith a continuation"
    )
    path = root / rel
    path.write_text(
        "# manifest-kind: implementation\nschema: '2'\ngoal: Preserve literal YAML during promotion\ndescription: |-\n"
        + textwrap.indent(description, "  ")
        + "\n"
        + yaml.safe_dump(data, sort_keys=False)
    )
    assert yaml.safe_load(path.read_text())["description"] == description
    return path


def _promote(root: Path, draft: Path, *, no_run: bool = True) -> int:
    return cmd_manifest(
        argparse.Namespace(
            manifest_command="promote",
            manifest_path=str(draft),
            output_dir=str(root / "manifests"),
            project_root=str(root),
            no_run=no_run,
            json=False,
        )
    )


def _lock(root: Path, draft: Path) -> Path:
    assert (
        cmd_plan_lock(
            argparse.Namespace(
                manifest_path=str(draft),
                project_root=str(root),
                no_run=False,
                json=False,
            )
        )
        == 0
    )
    path = default_plan_lock_path(root, _SLUG)
    assert PlanLock.load(path).red_evidence["red"] is True
    return path


@pytest.mark.parametrize("locked", [False, True])
def test_public_promote_preserves_literal_colons_bullets_and_continuation(
    tmp_path: Path, locked: bool
) -> None:
    draft = _draft(tmp_path)
    before = yaml.safe_load(draft.read_text())
    lock_path = _lock(tmp_path, draft) if locked else None
    assert _promote(tmp_path, draft, no_run=not locked) == 0
    target = tmp_path / f"manifests/{_SLUG}.manifest.yaml"
    promoted = yaml.safe_load(target.read_text())
    assert promoted["description"] == before["description"]
    assert promoted["files"] == before["files"]
    assert promoted["validate"][0] == before["validate"][0]
    assert promoted["validate"][1][2] == f"manifests/{_SLUG}.manifest.yaml"
    assert "description: |" in target.read_text()
    assert not draft.exists()
    if lock_path is not None:
        record = PlanLock.load(lock_path)
        assert record.manifest_path == f"manifests/{_SLUG}.manifest.yaml"
        assert record.revision == 2
        assert record.red_evidence["red"] is True
        assert record.red_evidence["commands"][0]["exit_code"] == 1
        commands = [entry["command"] for entry in record.red_evidence["commands"]]
        assert all("manifests/drafts/" not in command for command in commands)
        assert any(
            f"manifests/{_SLUG}.manifest.yaml" in command for command in commands
        )


def test_public_promote_preserves_normal_literal_content(tmp_path: Path) -> None:
    draft = _draft(tmp_path, problematic=False)
    formatter = YAML()
    data = formatter.load(draft.read_text())
    formatter.indent(mapping=4, sequence=6, offset=2)
    buffer = StringIO()
    formatter.dump(data, buffer)
    draft.write_text(buffer.getvalue())
    path_line = next(line for line in draft.read_text().splitlines() if "path:" in line)
    before = yaml.safe_load(draft.read_text())
    assert _promote(tmp_path, draft) == 0
    target = tmp_path / f"manifests/{_SLUG}.manifest.yaml"
    promoted = yaml.safe_load(target.read_text())
    assert promoted["description"] == before["description"]
    assert promoted["files"] == before["files"]
    assert "description: |" in target.read_text()
    assert (
        next(line for line in target.read_text().splitlines() if "path:" in line)
        == path_line
    )


def test_invalid_yaml_promotion_preserves_draft_and_existing_lock(
    tmp_path: Path,
) -> None:
    draft = _draft(tmp_path, problematic=False)
    lock_path = _lock(tmp_path, draft)
    prior_lock = lock_path.read_bytes()
    malformed = b"schema: '2'\ngoal: Invalid input\nfiles: [\n"
    draft.write_bytes(malformed)
    assert _promote(tmp_path, draft) == 2
    assert draft.read_bytes() == malformed
    assert lock_path.read_bytes() == prior_lock
    assert not (tmp_path / f"manifests/{_SLUG}.manifest.yaml").exists()
