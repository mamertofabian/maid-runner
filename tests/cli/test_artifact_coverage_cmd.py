from __future__ import annotations

import json
from pathlib import Path


def test_validate_parser_exposes_artifact_coverage_flag():
    from maid_runner.cli.commands._main import build_parser
    from maid_runner.cli.commands.validate import cmd_validate

    parser = build_parser()

    args = parser.parse_args(["validate", "--artifact-coverage"])

    assert callable(cmd_validate)
    assert args.artifact_coverage is True


def test_verify_parser_exposes_artifact_coverage_flag():
    from maid_runner.cli.commands._main import build_parser
    from maid_runner.cli.commands.verify import cmd_verify

    parser = build_parser()

    args = parser.parse_args(["verify", "--artifact-coverage"])

    assert callable(cmd_verify)
    assert args.artifact_coverage is True


def test_validate_json_includes_artifact_coverage_findings(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    from maid_runner.cli.commands._format import format_validation_result
    from maid_runner.cli.commands._main import main

    assert callable(format_validation_result)
    manifest_path = _write_project(
        tmp_path,
        slug="target",
        source="""
def target() -> str:
    return "executed"
""",
        test="""
from src.target import target


def test_executes_target_body():
    assert target() == "executed"
""",
    )
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "validate",
            str(manifest_path.relative_to(tmp_path)),
            "--mode",
            "schema",
            "--artifact-coverage",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True
    assert payload["artifact_coverage"]["findings"][0]["artifact_name"] == "target"
    assert payload["artifact_coverage"]["findings"][0]["executed"] is True


def test_verify_directory_wide_artifact_coverage_stage_fails_unexecuted_artifact(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    from maid_runner.cli.commands._format import format_verify_result
    from maid_runner.cli.commands._main import main

    assert callable(format_verify_result)
    _write_project(
        tmp_path,
        slug="target",
        source="""
def target() -> str:
    return "executed"
""",
        test="""
from src.target import target


def test_mentions_target_without_executing_body():
    assert target is not None
""",
    )
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "verify",
            "--artifact-coverage",
            "--manifest-dir",
            "manifests/",
            "--keep-going",
            "--no-changed-scope",
            "--json",
        ]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    stage = next(s for s in payload["stages"] if s["name"] == "artifact_coverage")
    assert stage["success"] is False
    assert stage["details"]["errors"][0]["code"] == "E710"
    assert stage["details"]["findings"][0]["executed"] is False


def _write_project(
    root: Path,
    *,
    slug: str,
    source: str,
    test: str,
) -> Path:
    src_dir = root / "src"
    tests_dir = root / "tests"
    manifests_dir = root / "manifests"
    src_dir.mkdir(exist_ok=True)
    tests_dir.mkdir(exist_ok=True)
    manifests_dir.mkdir(exist_ok=True)
    (src_dir / "__init__.py").write_text("")
    (src_dir / "target.py").write_text(source.lstrip())
    (tests_dir / "test_target.py").write_text(test.lstrip())
    manifest_path = manifests_dir / f"{slug}.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Cover target"
type: feature
created: "2026-06-10T00:00:00Z"
files:
  edit:
    - path: src/target.py
      artifacts:
        - kind: function
          name: target
  read:
    - tests/test_target.py
validate:
  - python -m pytest -q tests/test_target.py
""",
    )
    return manifest_path
