from __future__ import annotations

import json
from pathlib import Path


def test_warning_is_advisory_only_for_e307() -> None:
    from maid_runner.core.diagnostic_policy import warning_is_advisory
    from maid_runner.core.result import ErrorCode, Severity, ValidationError

    unavailable = ValidationError(
        code=ErrorCode.VALIDATOR_NOT_AVAILABLE,
        message="No validator is registered.",
        severity=Severity.WARNING,
    )
    stub = ValidationError(
        code=ErrorCode.STUB_FUNCTION_DETECTED,
        message="The function is a stub.",
        severity=Severity.WARNING,
    )

    assert warning_is_advisory(unavailable) is True
    assert warning_is_advisory(stub) is False


def test_validate_strict_preview_keeps_e307_visible_without_failing(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands._main import main

    manifest_path = _write_project(
        tmp_path,
        source='def target() -> str:\n    return "exe" + "cuted"\n',
        test=(
            "from src.target import target\n\n"
            "def test_executes_target():\n"
            '    assert target() == "executed"\n'
        ),
    )
    _force_no_validator(monkeypatch)
    monkeypatch.chdir(tmp_path)

    exit_code = main(_strict_command(manifest_path, "--strict-preview"))

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0, payload
    assert payload["success"] is True
    assert {warning["code"] for warning in payload["validation"]["warnings"]} == {
        "E307"
    }


def test_strict_delta_runs_artifact_coverage_despite_e307(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands._main import main

    manifest_path = _write_project(
        tmp_path,
        source='def target() -> str:\n    return "executed".upper()\n',
        test=(
            "from src.target import target\n\n"
            "def test_mentions_target_without_executing_it():\n"
            "    assert target is not None\n"
        ),
    )
    _force_no_validator(monkeypatch)
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "validate",
            "--manifest-dir",
            str(manifest_path.parent),
            "--mode",
            "implementation",
            "--strict-delta",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0, payload
    assert payload["success"] is True
    assert [entry["code"] for entry in payload["strict_delta"]] == ["E710"]


def test_validate_strict_preview_still_fails_on_e310(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands._main import main

    manifest_path = _write_project(
        tmp_path,
        source='def target() -> str:\n    return ""\n',
        test=(
            "from src.target import target\n\n"
            "def test_mentions_target():\n"
            "    assert target is not None\n"
        ),
    )
    monkeypatch.chdir(tmp_path)

    exit_code = main(_strict_command(manifest_path, "--strict-preview"))

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["success"] is False
    assert "E310" in {warning["code"] for warning in payload["warnings"]}


def _strict_command(manifest_path: Path, flag: str) -> list[str]:
    return [
        "validate",
        str(manifest_path),
        "--mode",
        "implementation",
        "--no-chain",
        flag,
        "--json",
    ]


def _force_no_validator(monkeypatch) -> None:
    from pathlib import Path

    from maid_runner.validators.registry import (
        UnsupportedLanguageError,
        ValidatorRegistry,
    )

    builtin = ValidatorRegistry.with_builtin_validators()

    class TestOnlyRegistry:
        def get(self, file_path):
            candidate = Path(file_path)
            if "tests" in candidate.parts:
                return builtin.get(file_path)
            raise UnsupportedLanguageError(candidate.suffix)

        def __getattr__(self, name):
            return getattr(builtin, name)

    monkeypatch.setattr(
        ValidatorRegistry,
        "with_builtin_validators",
        classmethod(lambda cls: TestOnlyRegistry()),
    )


def _write_project(root: Path, *, source: str, test: str) -> Path:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "manifests").mkdir()
    (root / "src" / "__init__.py").write_text("")
    (root / "src" / "target.py").write_text(source)
    (root / "tests" / "test_target.py").write_text(test)
    manifest_path = root / "manifests" / "strict-advisory.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Exercise strict advisory warning behavior"
type: fix
files:
  create:
    - path: src/target.py
      artifacts:
        - kind: function
          name: target
          args: []
          returns: str
  read:
    - tests/test_target.py
validate:
  - python -m pytest tests/test_target.py -q
"""
    )
    return manifest_path.relative_to(root)
