"""Behavioral contract for honest files.scope coverage reporting."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from maid_runner.core.result import FileTrackingStatus, ValidationResult


def _write_scope_only_project(root: Path) -> None:
    (root / "manifests").mkdir()
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "owner.py").write_text(
        "def owner() -> str:\n    return ''.join(('ow', 'ned'))\n",
        encoding="utf-8",
    )
    (root / "src" / "scoped.py").write_text(
        "def public_but_uncontracted() -> str:\n    return 'scope-only'\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_owner.py").write_text(
        "from src.owner import owner\n\ndef test_owner():\n    assert owner() == 'owned'\n",
        encoding="utf-8",
    )
    manifest = {
        "schema": "2",
        "goal": "Exercise honest scope-only tracking",
        "type": "fix",
        "created": "2026-08-04T00:00:00Z",
        "files": {
            "edit": [
                {
                    "path": "src/owner.py",
                    "artifacts": [
                        {
                            "kind": "function",
                            "name": "owner",
                            "args": [],
                            "returns": "str",
                        }
                    ],
                }
            ],
            "scope": [
                {
                    "path": "src/scoped.py",
                    "reason": "Private task wiring represented by a public-looking adversarial fixture.",
                }
            ],
            "read": ["tests/test_owner.py"],
        },
        "validate": ["python -m pytest tests/test_owner.py -q"],
    }
    (root / "manifests" / "scope-only.manifest.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )


def test_scope_only_inventory_is_not_artifact_tracked(tmp_path: Path) -> None:
    from maid_runner.cli.commands._format import format_file_tracking
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.types import ValidationMode
    from maid_runner.core.validate import ValidationEngine

    _write_scope_only_project(tmp_path)
    report = ValidationEngine(tmp_path).run_file_tracking(
        ManifestChain(tmp_path / "manifests", tmp_path)
    )

    assert FileTrackingStatus.SCOPE_ONLY.value == "scope_only"
    assert [entry.path for entry in report.scope_only] == ["src/scoped.py"]
    assert "src/scoped.py" not in [entry.path for entry in report.tracked]
    assert "src/scoped.py" not in [entry.path for entry in report.registered]
    assert "src/scoped.py" not in [entry.path for entry in report.undeclared]

    serialized = ValidationResult(
        success=True,
        manifest_slug="scope-only",
        manifest_path="manifests/scope-only.manifest.yaml",
        mode=ValidationMode.IMPLEMENTATION,
        file_tracking=report,
    ).to_dict()
    assert serialized["file_tracking"]["scope_only"] == ["src/scoped.py"]

    text_output = format_file_tracking(report)
    json_output = json.loads(format_file_tracking(report, json_mode=True))
    assert "Scope-only (1):" in text_output
    assert json_output["scope_only"] == ["src/scoped.py"]
    assert "src/scoped.py" not in json_output["tracked"]


def test_scope_only_cli_output_and_fail_gate_are_explicit(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    from maid_runner.cli.commands._main import build_parser
    from maid_runner.cli.commands.files import cmd_files

    _write_scope_only_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    parser = build_parser()
    parsed = parser.parse_args(["files", "--fail-on", "scope-only"])
    assert parsed.fail_on == ["scope-only"]

    common = {
        "manifest_dir": "manifests/",
        "hide_private": False,
        "json": True,
    }
    assert cmd_files(argparse.Namespace(**common, fail_on=None)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["scope_only"] == ["src/scoped.py"]
    assert "src/scoped.py" not in payload["tracked"]

    assert cmd_files(argparse.Namespace(**common, fail_on=["scope-only"])) == 1
    capsys.readouterr()
    assert cmd_files(argparse.Namespace(**common, fail_on=["any"])) == 1


def test_verify_can_require_artifact_contracted_file_tracking(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    from maid_runner.cli.commands._main import build_parser
    from maid_runner.cli.commands.verify import cmd_verify, run_verify

    _write_scope_only_project(tmp_path)

    compatible = run_verify("manifests/", tmp_path)
    strict = run_verify("manifests/", tmp_path, fail_on_scope_only=True)
    compatible_stage = next(
        stage for stage in compatible.stages if stage.name == "file_tracking"
    )
    strict_stage = next(
        stage for stage in strict.stages if stage.name == "file_tracking"
    )
    assert compatible_stage.success is True
    assert [entry.path for entry in compatible_stage._file_tracking.scope_only] == [
        "src/scoped.py"
    ]
    assert strict_stage.success is False

    monkeypatch.chdir(tmp_path)
    args = build_parser().parse_args(
        [
            "verify",
            "--no-changed-scope",
            "--fail-on-scope-only",
            "--json",
        ]
    )
    exit_code = cmd_verify(args)
    output = json.loads(capsys.readouterr().out)
    file_tracking = next(
        stage for stage in output["stages"] if stage["name"] == "file_tracking"
    )
    assert exit_code == 1
    assert file_tracking["success"] is False
    assert file_tracking["details"]["scope_only"] == ["src/scoped.py"]
    assert file_tracking["details"]["registered"] == []
    assert file_tracking["details"]["errors"][0]["code"] == "E402"


def test_risk_recommendation_treats_scope_only_as_contract_debt(
    tmp_path: Path,
) -> None:
    from maid_runner.core.coverage_recommendation import (
        CoverageStatus,
        recommend_coverage,
    )

    _write_scope_only_project(tmp_path)
    report = recommend_coverage(tmp_path)
    scoped = next(
        candidate
        for candidate in report.candidates
        if candidate.path == "src/scoped.py"
    )

    assert scoped.coverage_status is CoverageStatus.WRITABLE_NO_ARTIFACTS
    assert scoped.recommended_action == "complete-behavioral-contract"
