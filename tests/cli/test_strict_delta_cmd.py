from __future__ import annotations

import argparse
import json
from pathlib import Path


def test_parser_accepts_strict_delta_for_validate() -> None:
    from maid_runner.cli.commands._main import build_parser
    from maid_runner.cli.commands.validate import cmd_validate

    parser = build_parser()

    args = parser.parse_args(["validate", "--strict-delta"])

    assert callable(cmd_validate)
    assert args.strict_delta is True


def test_main_dispatches_strict_delta_to_validate_handler(monkeypatch) -> None:
    from maid_runner.cli.commands import validate as validate_cmd
    from maid_runner.cli.commands._main import main

    seen: list[bool] = []

    def fake_validate(args: argparse.Namespace) -> int:
        seen.append(args.strict_delta)
        return 0

    monkeypatch.setattr(validate_cmd, "cmd_validate", fake_validate)

    assert main(["validate", "--strict-delta"]) == 0
    assert seen == [True]


def test_validate_strict_delta_json_reports_strict_only_artifact_coverage(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands._main import main

    manifest_path = _write_project(
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
            "validate",
            str(manifest_path.relative_to(tmp_path)),
            "--mode",
            "schema",
            "--no-chain",
            "--strict-delta",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["success"] is True
    assert payload["strict_delta"] == [
        {
            "manifest_path": "manifests/target.manifest.yaml",
            "file": "src/target.py",
            "code": "E710",
            "severity": "error",
            "message": (
                "No body line of declared artifact 'target' was executed by tests"
            ),
        }
    ]


def test_validate_strict_delta_preserves_default_failure_exit_code(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands._main import main

    _write_project(
        tmp_path,
        slug="strict-only",
        source="""
def target() -> str:
    return "executed"
""",
        test="""
from src.target import target


def test_calls_target_without_assertions():
    target()
""",
    )
    _write_project(
        tmp_path,
        slug="default-fails",
        source="# missing declared target\n",
        test="""
def test_placeholder():
    assert True
""",
        append=True,
    )
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "validate",
            "--manifest-dir",
            "manifests/",
            "--mode",
            "behavioral",
            "--strict-delta",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["success"] is False
    assert {
        (entry["manifest_path"], entry["file"], entry["code"])
        for entry in payload["strict_delta"]
    } == {("manifests/strict-only.manifest.yaml", "tests/test_strict_only.py", "E210")}


def test_validate_strict_delta_text_reports_empty_delta(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands._main import main

    manifest_path = _write_project(
        tmp_path,
        slug="clean",
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
            "--no-chain",
            "--strict-delta",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Strict Delta: 0 strict-only diagnostics" in output
    assert "strict-preview" not in output


def _write_project(
    root: Path,
    *,
    slug: str,
    source: str,
    test: str,
    append: bool = False,
) -> Path:
    src_dir = root / "src"
    tests_dir = root / "tests"
    manifests_dir = root / "manifests"
    src_dir.mkdir(exist_ok=True)
    tests_dir.mkdir(exist_ok=True)
    manifests_dir.mkdir(exist_ok=True)
    (src_dir / "__init__.py").write_text("")
    file_slug = slug.replace("-", "_")
    source_path = src_dir / f"{file_slug}.py"
    test_path = tests_dir / f"test_{file_slug}.py"
    source_path.write_text(source.lstrip())
    test_path.write_text(test.lstrip())
    manifest_path = manifests_dir / f"{slug}.manifest.yaml"
    if append:
        source_file = f"src/{file_slug}.py"
    else:
        source_file = "src/target.py"
        source_path.rename(root / source_file)
    manifest_path.write_text(
        f"""schema: "2"
goal: "Cover {slug}"
type: feature
files:
  create:
    - path: {source_file}
      artifacts:
        - kind: function
          name: target
          returns: str
  read:
    - {test_path.relative_to(root).as_posix()}
validate:
  - python -m pytest {test_path.relative_to(root).as_posix()} -q
"""
    )
    return manifest_path
