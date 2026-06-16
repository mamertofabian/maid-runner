from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest


def test_verify_parser_exposes_knockout_flags() -> None:
    from maid_runner.cli.commands._main import build_parser
    from maid_runner.cli.commands.verify import cmd_verify

    parser = build_parser()

    args = parser.parse_args(
        [
            "verify",
            "--knockout",
            "--knockout-limit",
            "2",
            "--knockout-allow-dirty",
        ]
    )

    assert callable(cmd_verify)
    assert args.knockout is True
    assert args.knockout_limit == 2
    assert args.knockout_allow_dirty is True


def test_verify_parser_rejects_non_positive_knockout_limit() -> None:
    from maid_runner.cli.commands._main import build_parser

    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["verify", "--knockout", "--knockout-limit", "0"])
    with pytest.raises(SystemExit):
        parser.parse_args(["verify", "--knockout", "--knockout-limit", "-1"])


def test_cmd_verify_forwards_knockout_flags_to_run_verify(monkeypatch, capsys) -> None:
    from maid_runner.cli.commands.verify import cmd_verify
    from maid_runner.core.result import VerificationResult

    captured = {}

    def fake_run_verify(**kwargs):
        captured["knockout"] = kwargs["knockout"]
        captured["knockout_limit"] = kwargs["knockout_limit"]
        captured["knockout_allow_dirty"] = kwargs["knockout_allow_dirty"]
        return VerificationResult(stages=(), duration_ms=1.0)

    monkeypatch.setattr("maid_runner.cli.commands.verify._run_verify", fake_run_verify)

    exit_code = cmd_verify(
        argparse.Namespace(
            manifest_dir="manifests/",
            allow_empty=False,
            fail_fast=True,
            strict=False,
            fail_on_warnings=False,
            advisory=False,
            worktree_scope=False,
            changed_scope=False,
            since=None,
            base_ref=None,
            include_tests=False,
            test_jobs=1,
            require_plan_lock=False,
            require_red_evidence=False,
            artifact_coverage=False,
            knockout=True,
            knockout_limit=3,
            knockout_allow_dirty=True,
            json=False,
        )
    )

    assert exit_code == 0
    assert captured == {
        "knockout": True,
        "knockout_limit": 3,
        "knockout_allow_dirty": True,
    }


def test_verify_knockout_fails_hardcoded_artifact_that_tests_do_not_call(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands._main import main

    _write_knockout_project(
        tmp_path,
        source="""
def target() -> str:
    return "hardcoded"
""",
        test="""
from src.target import target


def test_mentions_target_without_calling_it():
    assert target is not None
""",
    )
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "verify",
            "--knockout",
            "--knockout-allow-dirty",
            "--no-changed-scope",
            "--advisory",
            "--json",
        ]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    stage = _stage(payload, "knockout")
    assert stage["success"] is False
    assert stage["details"]["errors"][0]["code"] == "E711"
    assert "target" in stage["details"]["errors"][0]["message"]
    assert "src/target.py" in stage["details"]["errors"][0]["message"]
    assert stage["details"]["results"][0]["artifact_name"] == "target"
    assert stage["details"]["results"][0]["detected"] is False
    assert "duration_ms" in stage["details"]["results"][0]


def test_verify_knockout_passes_honest_artifact(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands._main import main

    _write_knockout_project(
        tmp_path,
        source="""
def target() -> str:
    value = "honest"
    return value
""",
        test="""
from src.target import target


def test_target_behavior():
    assert target() == "honest"
""",
    )
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        ["verify", "--knockout", "--knockout-allow-dirty", "--no-changed-scope"]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Verify: PASS" in output
    assert "PASS knockout" in output
    assert "detected: target (src/target.py)" in output


def test_verify_knockout_harness_failure_is_e712_and_restores_source(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands._main import main
    from maid_runner.core import knockout

    _write_knockout_project(
        tmp_path,
        source="""
def target() -> str:
    value = "honest"
    return value
""",
        test="""
from src.target import target


def test_target_behavior():
    assert target() == "honest"
""",
    )
    source_path = tmp_path / "src" / "target.py"
    original = source_path.read_text()

    def raise_spawn_failure(*args, **kwargs):
        raise RuntimeError("spawn failed")

    monkeypatch.setattr(knockout, "_run_test_command", raise_spawn_failure)
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "verify",
            "--knockout",
            "--knockout-allow-dirty",
            "--no-changed-scope",
            "--json",
        ]
    )

    assert exit_code == 1
    assert source_path.read_text() == original
    payload = json.loads(capsys.readouterr().out)
    stage = _stage(payload, "knockout")
    assert stage["details"]["errors"][0]["code"] == "E712"
    assert "spawn failed" in stage["details"]["errors"][0]["message"]


def test_verify_knockout_limit_bounds_manifest_order(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands._main import main

    _write_knockout_project(
        tmp_path,
        source="""
def alpha() -> str:
    value = "alpha"
    return value


def beta() -> str:
    value = "beta"
    return value
""",
        test="""
from src.target import alpha, beta


def test_targets_behavior():
    assert alpha() == "alpha"
    assert beta() == "beta"
""",
        artifacts=("alpha", "beta"),
    )
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "verify",
            "--knockout",
            "--knockout-limit",
            "1",
            "--knockout-allow-dirty",
            "--no-changed-scope",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    stage = _stage(payload, "knockout")
    assert [result["artifact_name"] for result in stage["details"]["results"]] == [
        "alpha"
    ]


def test_verify_knockout_dirty_refusal_and_allow_dirty_override(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands._main import main
    from maid_runner.core import knockout

    _write_knockout_project(
        tmp_path,
        source="""
def target() -> str:
    value = "honest"
    return value
""",
        test="""
from src.target import target


def test_target_behavior():
    assert target() == "honest"
""",
    )
    monkeypatch.setattr(knockout, "changed_files", lambda root: ("src/target.py",))
    monkeypatch.chdir(tmp_path)

    refused = main(["verify", "--knockout", "--no-changed-scope", "--json"])
    refused_payload = json.loads(capsys.readouterr().out)

    allowed = main(
        [
            "verify",
            "--knockout",
            "--knockout-allow-dirty",
            "--no-changed-scope",
            "--json",
        ]
    )
    allowed_payload = json.loads(capsys.readouterr().out)

    assert refused == 1
    refused_stage = _stage(refused_payload, "knockout")
    assert refused_stage["details"]["errors"][0]["code"] == "E712"
    assert "dirty source file" in refused_stage["details"]["errors"][0]["message"]
    assert allowed == 0
    allowed_stage = _stage(allowed_payload, "knockout")
    assert allowed_stage["success"] is True
    assert allowed_stage["details"]["results"][0]["detected"] is True


def test_verify_knockout_text_and_json_include_same_e711_result_shape(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands._format import format_verify_result
    from maid_runner.cli.commands._main import main

    assert callable(format_verify_result)
    for root in (tmp_path / "text", tmp_path / "json"):
        _write_knockout_project(
            root,
            source="""
def target() -> str:
    return "hardcoded"
""",
            test="""
from src.target import target


def test_mentions_target_without_calling_it():
    assert target is not None
""",
        )

    monkeypatch.chdir(tmp_path / "text")
    text_exit = main(
        [
            "verify",
            "--knockout",
            "--knockout-allow-dirty",
            "--no-changed-scope",
            "--advisory",
        ]
    )
    text_output = capsys.readouterr().out

    monkeypatch.chdir(tmp_path / "json")
    json_exit = main(
        [
            "verify",
            "--knockout",
            "--knockout-allow-dirty",
            "--no-changed-scope",
            "--advisory",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    error = _stage(payload, "knockout")["details"]["errors"][0]

    assert text_exit == json_exit == 1
    assert "FAIL knockout" in text_output
    assert "E711" in text_output
    assert "not detected: target (src/target.py)" in text_output
    assert "Duration:" in text_output
    assert error["code"] == "E711"
    assert "target" in error["message"]
    assert "src/target.py" in error["message"]


def _write_knockout_project(
    root: Path,
    *,
    source: str,
    test: str,
    artifacts: tuple[str, ...] = ("target",),
) -> Path:
    src_dir = root / "src"
    tests_dir = root / "tests"
    manifests_dir = root / "manifests"
    src_dir.mkdir(parents=True)
    tests_dir.mkdir()
    manifests_dir.mkdir()
    (src_dir / "__init__.py").write_text("")
    (src_dir / "target.py").write_text(source.lstrip())
    (tests_dir / "test_target.py").write_text(test.lstrip())
    artifact_yaml = "\n".join(
        f"        - kind: function\n          name: {artifact}"
        for artifact in artifacts
    )
    manifest_path = manifests_dir / "target.manifest.yaml"
    manifest_path.write_text(
        f"""schema: "2"
goal: "Verify knockout target"
type: feature
created: "2026-06-10T00:00:00Z"
files:
  edit:
    - path: src/target.py
      artifacts:
{artifact_yaml}
  read:
    - tests/test_target.py
validate:
  - python -m pytest -q tests/test_target.py
"""
    )
    return manifest_path


def _stage(payload: dict, name: str) -> dict:
    return next(stage for stage in payload["stages"] if stage["name"] == name)
