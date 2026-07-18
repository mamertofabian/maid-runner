"""Behavioral coverage for YAML-native contract-hash normalization."""

from __future__ import annotations

from pathlib import Path

import pytest

from maid_runner.core.plan_lock import compute_manifest_contract_hash


_BASE_MANIFEST = """schema: "2"
goal: "Normalize YAML-native metadata"
type: fix
created: "2026-07-18T00:00:00Z"
metadata:
{metadata}
files:
  read:
    - tests/test_demo.py
validate:
  - python -m pytest -q tests/test_demo.py
"""


def _write_manifest(path: Path, metadata: str) -> Path:
    path.write_text(_BASE_MANIFEST.format(metadata=metadata))
    return path


def test_contract_hash_accepts_yaml_date_metadata(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path / "dated.manifest.yaml",
        "  reviewed_on: 2026-07-18\n" "  reviewed_at: 2026-07-18T12:34:56+00:00",
    )

    digest = compute_manifest_contract_hash(manifest_path)

    assert digest.startswith("sha256-contract:")


def test_contract_hash_equates_yaml_date_and_quoted_string(tmp_path: Path) -> None:
    unquoted = _write_manifest(
        tmp_path / "unquoted.manifest.yaml",
        "  reviewed_on: 2026-07-18\n" "  reviewed_at: 2026-07-18T12:34:56+00:00",
    )
    quoted = _write_manifest(
        tmp_path / "quoted.manifest.yaml",
        '  reviewed_on: "2026-07-18"\n' '  reviewed_at: "2026-07-18T12:34:56+00:00"',
    )

    assert compute_manifest_contract_hash(unquoted) == compute_manifest_contract_hash(
        quoted
    )


def test_contract_hash_normalizes_non_string_mapping_keys(tmp_path: Path) -> None:
    numeric = _write_manifest(
        tmp_path / "numeric-key.manifest.yaml",
        "  labels:\n    1: first\n    alpha: second",
    )
    string = _write_manifest(
        tmp_path / "string-key.manifest.yaml",
        '  labels:\n    "1": first\n    alpha: second',
    )

    assert compute_manifest_contract_hash(numeric) == compute_manifest_contract_hash(
        string
    )


def test_contract_hash_raises_named_error_for_unsupported_values(
    tmp_path: Path,
) -> None:
    manifest_path = _write_manifest(
        tmp_path / "binary.manifest.yaml",
        "  payload: !!binary ZGVtbw==",
    )

    with pytest.raises(ValueError) as exc_info:
        compute_manifest_contract_hash(manifest_path)

    detail = str(exc_info.value)
    assert str(manifest_path) in detail
    assert "metadata.payload" in detail
    assert "bytes" in detail or "unsupported" in detail.lower()
