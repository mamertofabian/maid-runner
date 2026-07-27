"""Behavioral contract for convert_v1_file output format and header.

`convert_v1_file` rendered YAML into whatever path it was handed and never
called `prepend_manifest_header`, so migrating a v1 manifest to an explicit
`.json` path produced a file `load_manifest_raw` rejects with a JSONDecodeError,
and every migrated manifest landed without the 086-01 banner. These tests pin
that the write format follows the resolved output suffix, matched
case-sensitively because the reader matches it that way, that an unsupported
suffix fails loudly before any filesystem access, and that adding the banner
left the converted body byte-for-byte unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


def _v1_source() -> dict:
    """A v1 manifest exercising the fields migration is asked to carry across."""
    return {
        "version": "1",
        "goal": "Migrate a legacy manifest",
        "taskType": "edit",
        "editableFiles": ["src/app.py"],
        "expectedArtifacts": {
            "file": "src/app.py",
            "contains": [
                {"type": "function", "name": "run", "returns": {"type": "int"}}
            ],
        },
        "validationCommand": "pytest tests/ -v",
    }


def _write_v1(tmp_path: Path) -> Path:
    input_path = tmp_path / "legacy-task.manifest.json"
    input_path.write_text(json.dumps(_v1_source()))
    return input_path


def test_convert_v1_file_json_suffix_round_trips_through_loader(
    tmp_path: Path,
) -> None:
    from maid_runner.compat.v1_loader import convert_v1_file, convert_v1_to_v2
    from maid_runner.core.manifest import load_manifest_raw

    out_path = tmp_path / "migrated.manifest.json"

    convert_v1_file(_write_v1(tmp_path), out_path)

    # Strict json.loads is what load_manifest_raw uses for a .json suffix, so a
    # YAML body would raise JSONDecodeError here rather than round-trip.
    data = load_manifest_raw(out_path)
    # Compared against the whole converted dict, not sampled fields: a lossy
    # JSON body would satisfy a goal/type spot check.
    assert data == convert_v1_to_v2(_v1_source())
    # JSON has no comment syntax, so the 086-01 YAML banner must not appear.
    assert not out_path.read_text().lstrip().startswith("#")


def test_convert_v1_file_yaml_output_carries_self_describing_header(
    tmp_path: Path,
) -> None:
    from maid_runner.compat.v1_loader import convert_v1_file
    from maid_runner.core.manifest import load_manifest_raw

    out_path = convert_v1_file(_write_v1(tmp_path))

    assert out_path.suffix == ".yaml"
    source = out_path.read_text()
    assert source.startswith("#")
    assert "github.com/mamertofabian/maid-runner" in source
    assert load_manifest_raw(out_path)["goal"] == "Migrate a legacy manifest"


def test_convert_v1_file_yml_body_is_the_unheadered_conversion(
    tmp_path: Path,
) -> None:
    from maid_runner.compat.v1_loader import convert_v1_file, convert_v1_to_v2
    from maid_runner.core.manifest import MANIFEST_HEADER_COMMENT

    out_path = tmp_path / "migrated.manifest.yml"

    convert_v1_file(_write_v1(tmp_path), out_path)

    source = out_path.read_text()
    assert source.startswith(MANIFEST_HEADER_COMMENT)
    # The body below the banner must be exactly what the writer produced before
    # this contract. PyYAML parses JSON, so a bare round-trip could not tell a
    # JSON body under the banner apart from a YAML one; this comparison can.
    body = source[len(MANIFEST_HEADER_COMMENT) :]
    assert body == yaml.dump(
        convert_v1_to_v2(_v1_source()), default_flow_style=False, sort_keys=False
    )


def test_convert_v1_file_unsupported_suffix_is_rejected_without_writing(
    tmp_path: Path,
) -> None:
    from maid_runner.compat.v1_loader import convert_v1_file

    out_path = tmp_path / "migrated.txt"
    out_path.write_text("sentinel")

    with pytest.raises(ValueError) as excinfo:
        convert_v1_file(_write_v1(tmp_path), out_path)

    assert ".txt" in str(excinfo.value)
    assert out_path.read_text() == "sentinel"


def test_convert_v1_file_checks_suffix_before_reading_input(tmp_path: Path) -> None:
    from maid_runner.compat.v1_loader import convert_v1_file

    # The input does not exist, so reaching the read would raise
    # FileNotFoundError. Getting ValueError instead is only possible if the
    # suffix is validated first, which is what "no filesystem effect" means
    # here. A sentinel test cannot prove this: a write-then-restore rollback
    # would survive it.
    missing_input = tmp_path / "does-not-exist.manifest.json"

    with pytest.raises(ValueError) as excinfo:
        convert_v1_file(missing_input, tmp_path / "migrated.txt")

    assert ".txt" in str(excinfo.value)


def test_convert_v1_file_uppercase_suffix_is_rejected_without_writing(
    tmp_path: Path,
) -> None:
    from maid_runner.compat.v1_loader import convert_v1_file

    # load_manifest_raw and manifest chain discovery both match the lowercase
    # suffix exactly, so ".YAML" is not a loadable manifest even though it looks
    # like one. Accepting it would recreate the silent-bad-artifact defect.
    out_path = tmp_path / "migrated.manifest.YAML"

    with pytest.raises(ValueError) as excinfo:
        convert_v1_file(_write_v1(tmp_path), out_path)

    assert ".YAML" in str(excinfo.value)
    assert not out_path.exists()


def test_convert_v1_file_suffixless_output_path_is_rejected(tmp_path: Path) -> None:
    from maid_runner.compat.v1_loader import convert_v1_file

    # An empty suffix must not fall back to YAML; load_manifest_raw rejects a
    # suffixless path with "Unknown extension".
    out_path = tmp_path / "migrated"

    with pytest.raises(ValueError):
        convert_v1_file(_write_v1(tmp_path), out_path)

    assert not out_path.exists()
