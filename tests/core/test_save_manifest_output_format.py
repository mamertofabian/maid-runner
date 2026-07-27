"""Behavioral contract for save_manifest output format selection.

`save_manifest` rendered YAML into whatever path it was handed, so
`save_manifest(m, "out.json")` produced a file `load_manifest_raw` then rejects
with a JSONDecodeError, and `save_manifest(m, "out.txt")` produced a file no
MAID command can load. These tests pin that the write format follows the output
suffix, matched case-sensitively because the reader matches it that way, and
that an unsupported suffix fails loudly before touching the filesystem.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maid_runner.core.types import Manifest, TaskType


def _manifest() -> Manifest:
    return Manifest(
        slug="save-manifest-output-format",
        source_path="",
        goal="Pin save_manifest output format",
        validate_commands=(("pytest", "tests/", "-v"),),
        task_type=TaskType.FIX,
    )


def test_save_manifest_json_suffix_round_trips_through_loader(tmp_path: Path) -> None:
    from maid_runner.core.manifest import load_manifest_raw, save_manifest

    out_path = tmp_path / "out.manifest.json"

    save_manifest(_manifest(), out_path)

    # Strict json.loads is what load_manifest_raw uses for a .json suffix, so a
    # YAML body would raise JSONDecodeError here rather than round-trip.
    data = load_manifest_raw(out_path)
    assert data["goal"] == "Pin save_manifest output format"
    assert data["type"] == "fix"
    # JSON has no comment syntax, so the 086-01 YAML banner must not appear.
    assert not out_path.read_text().lstrip().startswith("#")
    json.loads(out_path.read_text())


def test_save_manifest_unsupported_suffix_is_rejected_without_writing(
    tmp_path: Path,
) -> None:
    from maid_runner.core.manifest import save_manifest

    out_path = tmp_path / "out.txt"
    # A sentinel already at the path distinguishes validate-before-write from
    # write-then-roll-back: a writer that wrote and then cleaned up would leave
    # the path missing rather than leave these bytes intact.
    out_path.write_text("sentinel")

    with pytest.raises(ValueError) as excinfo:
        save_manifest(_manifest(), out_path)

    assert ".txt" in str(excinfo.value)
    assert out_path.read_text() == "sentinel"


def test_save_manifest_uppercase_suffix_is_rejected_without_writing(
    tmp_path: Path,
) -> None:
    from maid_runner.core.manifest import save_manifest

    # load_manifest_raw and manifest chain discovery both match the lowercase
    # suffix exactly, so ".YAML" is not a loadable manifest even though it looks
    # like one. Accepting it would recreate the silent-bad-artifact defect.
    out_path = tmp_path / "out.manifest.YAML"

    with pytest.raises(ValueError) as excinfo:
        save_manifest(_manifest(), out_path)

    assert ".YAML" in str(excinfo.value)
    assert not out_path.exists()


def test_save_manifest_yaml_suffix_still_writes_banner_and_loads(
    tmp_path: Path,
) -> None:
    from maid_runner.core.manifest import load_manifest_raw, save_manifest

    out_path = tmp_path / "out.manifest.yaml"

    save_manifest(_manifest(), out_path)

    assert load_manifest_raw(out_path)["goal"] == "Pin save_manifest output format"
    source = out_path.read_text()
    # PyYAML parses JSON, so a bare round-trip cannot tell the two branches
    # apart; only a real YAML write can carry the comment banner.
    assert source.startswith("#")
    assert "github.com/mamertofabian/maid-runner" in source


def test_save_manifest_yml_suffix_writes_banner_and_loads(tmp_path: Path) -> None:
    from maid_runner.core.manifest import load_manifest_raw, save_manifest

    out_path = tmp_path / "out.manifest.yml"

    save_manifest(_manifest(), out_path)

    assert load_manifest_raw(out_path)["goal"] == "Pin save_manifest output format"
    assert out_path.read_text().startswith("#")
