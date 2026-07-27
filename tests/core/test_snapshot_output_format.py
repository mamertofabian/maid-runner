"""Behavioral contract for snapshot output format selection.

`maid snapshot --output <path>.manifest.json` used to write YAML into the
`.json` path and exit 0, producing a file MAID's own loader rejects. These tests
pin that the write format follows the output suffix, and that an unsupported or
contradictory combination fails loudly without leaving an artifact behind.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maid_runner.core.types import Manifest, TaskType


def _manifest() -> Manifest:
    return Manifest(
        slug="snapshot-output-format",
        source_path="",
        goal="Snapshot of demo.py",
        validate_commands=(("pytest", "tests/", "-v"),),
        task_type=TaskType.SNAPSHOT,
        files_snapshot=(),
    )


def test_output_with_json_suffix_writes_loadable_json(tmp_path: Path) -> None:
    from maid_runner.core.manifest import load_manifest_raw
    from maid_runner.core.snapshot import save_snapshot

    out_path = tmp_path / "out.manifest.json"

    written = save_snapshot(_manifest(), output=str(out_path))

    assert written == out_path
    # Strict json.loads is what load_manifest_raw uses for a .json suffix; a
    # YAML body would raise JSONDecodeError here.
    data = load_manifest_raw(written)
    assert data["goal"] == "Snapshot of demo.py"
    assert data["type"] == "snapshot"
    # JSON has no comment syntax, so the 086-01 YAML banner must not appear.
    assert not written.read_text().lstrip().startswith("#")
    json.loads(written.read_text())


def test_output_with_yaml_suffix_writes_loadable_yaml_with_header(
    tmp_path: Path,
) -> None:
    from maid_runner.core.manifest import load_manifest_raw
    from maid_runner.core.snapshot import save_snapshot

    out_path = tmp_path / "out.manifest.yaml"

    written = save_snapshot(_manifest(), output=str(out_path))

    assert written == out_path
    data = load_manifest_raw(written)
    assert data["goal"] == "Snapshot of demo.py"
    source = written.read_text()
    assert source.startswith("#")
    assert "github.com/mamertofabian/maid-runner" in source


def test_output_with_unsupported_suffix_is_rejected_without_writing(
    tmp_path: Path,
) -> None:
    from maid_runner.core.snapshot import save_snapshot

    out_path = tmp_path / "out.txt"

    with pytest.raises(ValueError) as excinfo:
        save_snapshot(_manifest(), output=str(out_path))

    assert ".txt" in str(excinfo.value)
    assert not out_path.exists()


def test_output_suffix_conflicting_with_explicit_format_is_rejected(
    tmp_path: Path,
) -> None:
    from maid_runner.core.snapshot import save_snapshot

    out_path = tmp_path / "out.manifest.json"

    with pytest.raises(ValueError) as excinfo:
        save_snapshot(_manifest(), output=str(out_path), format="yaml")

    message = str(excinfo.value)
    assert "yaml" in message
    assert ".json" in message
    assert not out_path.exists()


def test_output_with_uppercase_suffix_is_rejected_without_writing(
    tmp_path: Path,
) -> None:
    from maid_runner.core.snapshot import save_snapshot

    # load_manifest_raw and manifest discovery match the lowercase suffix
    # exactly, so ".JSON" is not a loadable manifest even though it looks like
    # one. Accepting it would recreate the silent-bad-artifact defect.
    out_path = tmp_path / "out.manifest.JSON"

    with pytest.raises(ValueError) as excinfo:
        save_snapshot(_manifest(), output=str(out_path))

    assert ".JSON" in str(excinfo.value)
    assert not out_path.exists()


def test_output_suffix_matching_explicit_format_is_accepted(tmp_path: Path) -> None:
    from maid_runner.core.snapshot import save_snapshot

    out_path = tmp_path / "out.manifest.json"

    written = save_snapshot(_manifest(), output=str(out_path), format="json")

    assert written == out_path
    assert json.loads(written.read_text())["goal"] == "Snapshot of demo.py"


def test_output_with_yml_suffix_writes_loadable_yaml(tmp_path: Path) -> None:
    from maid_runner.core.manifest import load_manifest_raw
    from maid_runner.core.snapshot import save_snapshot

    out_path = tmp_path / "out.manifest.yml"

    written = save_snapshot(_manifest(), output=str(out_path))

    assert written == out_path
    assert load_manifest_raw(written)["goal"] == "Snapshot of demo.py"


def test_output_dir_still_honors_explicit_format(tmp_path: Path) -> None:
    from maid_runner.core.snapshot import save_snapshot

    as_json = save_snapshot(_manifest(), output_dir=str(tmp_path), format="json")
    as_yaml = save_snapshot(_manifest(), output_dir=str(tmp_path))

    assert as_json.suffix == ".json"
    assert json.loads(as_json.read_text())["goal"] == "Snapshot of demo.py"
    assert as_yaml.suffix == ".yaml"
    assert as_yaml.read_text().startswith("#")
