"""An explicitly selected draft gets a temporary, isolated proposed chain view."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from maid_runner.core.chain import ManifestChain
from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine, validate


def _write(
    root: Path,
    slug: str,
    test_name: str,
    *,
    draft: bool = False,
    supersedes: list[str] | None = None,
) -> Path:
    directory = root / "manifests" / ("drafts" if draft else "")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{slug}.manifest.yaml"
    data = {
        "schema": "2",
        "goal": slug,
        "type": "fix",
        "created": "2026-10-21T00:00:00Z",
        "files": {
            "edit": [
                {
                    "path": "tests/test_behavior.py",
                    "artifacts": [
                        {
                            "kind": "test_function",
                            "name": test_name,
                            "args": [],
                            "returns": "None",
                        }
                    ],
                }
            ]
        },
        "validate": [["python", "-m", "pytest", "tests/test_behavior.py", "-q"]],
    }
    if supersedes is not None:
        data["supersedes"] = supersedes
    path.write_text(
        ("# manifest-kind: implementation\n" if draft else "") + yaml.safe_dump(data)
    )
    return path


def _project(root: Path) -> tuple[Path, Path]:
    (root / "tests").mkdir()
    (root / "tests/test_behavior.py").write_text(
        "def test_new() -> None:\n    assert 2 + 2 == 4\n"
    )
    executed = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_behavior.py", "-q"],
        cwd=root,
        env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert executed.returncode == 0, executed.stdout + executed.stderr
    old = _write(root, "old", "test_old")
    replacement = _write(
        root, "replacement", "test_new", draft=True, supersedes=["old"]
    )
    return old, replacement


@pytest.mark.parametrize(
    "mode", [ValidationMode.BEHAVIORAL, ValidationMode.IMPLEMENTATION]
)
def test_selected_draft_can_replace_old_test_name(
    tmp_path: Path, mode: ValidationMode
) -> None:
    _, replacement = _project(tmp_path)
    result = validate(replacement, mode=mode, project_root=tmp_path)
    assert result.success, result.errors
    assert not any(
        e.code == ErrorCode.TEST_FUNCTION_MISSING_IN_CODE for e in result.errors
    )


def test_supplied_chain_and_files_remain_unchanged_after_draft_validation(
    tmp_path: Path,
) -> None:
    old, replacement = _project(tmp_path)
    chain = ManifestChain(tmp_path / "manifests", tmp_path)
    before = [(m.slug, m.source_path) for m in chain.all_manifests]
    files = {
        p.relative_to(tmp_path): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    result = ValidationEngine(project_root=tmp_path).validate(
        replacement, mode=ValidationMode.BEHAVIORAL, use_chain=True, chain=chain
    )
    assert result.success, result.errors
    assert [(m.slug, m.source_path) for m in chain.all_manifests] == before
    assert [m.slug for m in chain.active_manifests()] == ["old"]
    assert not chain.is_superseded("old")
    assert {
        p.relative_to(tmp_path): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    } == files
    active = validate(old, mode=ValidationMode.BEHAVIORAL, project_root=tmp_path)
    assert any(e.code == ErrorCode.TEST_FUNCTION_MISSING_IN_CODE for e in active.errors)


def test_unselected_draft_does_not_change_active_chain(tmp_path: Path) -> None:
    old, _ = _project(tmp_path)
    result = validate(old, mode=ValidationMode.BEHAVIORAL, project_root=tmp_path)
    assert not result.success
    assert any(e.code == ErrorCode.TEST_FUNCTION_MISSING_IN_CODE for e in result.errors)
    assert [
        m.slug
        for m in ManifestChain(tmp_path / "manifests", tmp_path).active_manifests()
    ] == ["old"]


def test_selected_draft_does_not_activate_unrelated_drafts_or_bypass_active_contracts(
    tmp_path: Path,
) -> None:
    _, replacement = _project(tmp_path)
    _write(tmp_path, "other", "test_missing")
    _write(tmp_path, "unselected", "test_new", draft=True, supersedes=["other"])
    result = validate(
        replacement, mode=ValidationMode.BEHAVIORAL, project_root=tmp_path
    )
    missing = [
        e.message
        for e in result.errors
        if e.code == ErrorCode.TEST_FUNCTION_MISSING_IN_CODE
    ]
    assert any("test_missing" in m for m in missing), result.errors
    assert not any("test_old" in m for m in missing), result.errors


def test_selected_draft_preserves_missing_target_diagnostic(tmp_path: Path) -> None:
    _, replacement = _project(tmp_path)
    data = yaml.safe_load(replacement.read_text())
    data["supersedes"].append("absent")
    replacement.write_text("# manifest-kind: implementation\n" + yaml.safe_dump(data))
    result = validate(
        replacement, mode=ValidationMode.BEHAVIORAL, project_root=tmp_path
    )
    assert any(
        e.code == ErrorCode.SUPERSEDED_MANIFEST_NOT_FOUND
        for e in result.errors + result.warnings
    ), result


def test_selected_draft_preserves_cycle_diagnostic(tmp_path: Path) -> None:
    old, replacement = _project(tmp_path)
    data = yaml.safe_load(old.read_text())
    data["supersedes"] = ["replacement"]
    old.write_text(yaml.safe_dump(data))
    result = validate(
        replacement, mode=ValidationMode.BEHAVIORAL, project_root=tmp_path
    )
    assert any(e.code == ErrorCode.CIRCULAR_SUPERSESSION for e in result.errors), result


def test_selected_draft_preserves_production_drop_audit(tmp_path: Path) -> None:
    old, replacement = _project(tmp_path)
    (tmp_path / "source.py").write_text("def survive() -> int:\n    return 1\n")
    data = yaml.safe_load(old.read_text())
    data["files"]["edit"].append(
        {
            "path": "source.py",
            "artifacts": [
                {"kind": "function", "name": "survive", "args": [], "returns": "int"}
            ],
        }
    )
    old.write_text(yaml.safe_dump(data))
    result = validate(
        replacement, mode=ValidationMode.BEHAVIORAL, project_root=tmp_path
    )
    assert any(
        e.code == ErrorCode.ARTIFACT_DROPPED_BY_SUPERSESSION
        for e in result.errors + result.warnings
    ), result


def test_selected_draft_uses_configured_manifest_directory(tmp_path: Path) -> None:
    _, replacement = _project(tmp_path)
    (tmp_path / "manifests").rename(tmp_path / "contracts")
    selected = tmp_path / "contracts/drafts" / replacement.name
    result = validate(
        selected,
        mode=ValidationMode.BEHAVIORAL,
        project_root=tmp_path,
        manifest_dir="contracts",
    )
    assert result.success, result.errors
    assert [
        m.slug
        for m in ManifestChain(tmp_path / "contracts", tmp_path).active_manifests()
    ] == ["old"]


def test_selected_draft_preserves_unmarked_draft_rejection(tmp_path: Path) -> None:
    _, replacement = _project(tmp_path)
    replacement.write_text(
        replacement.read_text().replace("# manifest-kind: implementation\n", "")
    )
    result = validate(
        replacement, mode=ValidationMode.BEHAVIORAL, project_root=tmp_path
    )
    assert any(
        e.code == ErrorCode.INACTIVE_MANIFEST_NOT_MARKED for e in result.errors
    ), result


def test_selected_draft_retains_metadata_without_active_status_error(
    tmp_path: Path,
) -> None:
    _, replacement = _project(tmp_path)
    data = yaml.safe_load(replacement.read_text())
    data["metadata"] = {"status": "draft", "note": "keep this exact proposal"}
    replacement.write_text("# manifest-kind: implementation\n" + yaml.safe_dump(data))
    before = replacement.read_bytes()
    result = validate(
        replacement, mode=ValidationMode.BEHAVIORAL, project_root=tmp_path
    )
    assert result.success, result.errors
    assert replacement.read_bytes() == before


def test_selected_draft_preserves_unrelated_active_lifecycle_error(
    tmp_path: Path,
) -> None:
    _, replacement = _project(tmp_path)
    other = _write(tmp_path, "other", "test_new")
    data = yaml.safe_load(other.read_text())
    data["metadata"] = {"status": "draft"}
    other.write_text(yaml.safe_dump(data))
    result = validate(
        replacement, mode=ValidationMode.BEHAVIORAL, project_root=tmp_path
    )
    assert any(
        e.code == ErrorCode.ACTIVE_MANIFEST_INACTIVE_STATUS and "other" in e.message
        for e in result.errors
    ), result
