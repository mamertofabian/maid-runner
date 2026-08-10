from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode


def test_failure_reports_ignore_volatile_pytest_elapsed_duration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from maid_runner.core.artifact_coverage import (
        run_artifact_coverage,
        run_artifact_coverage_batch,
    )

    manifests = [load_manifest(path) for path in _write_failing_project(tmp_path)]
    real_run = subprocess.run
    elapsed = iter(("0.01s", "0.02s", "0.03s"))

    def run_with_distinct_elapsed_durations(command, *args, **kwargs):
        result = real_run(command, *args, **kwargs)
        normalized = tuple(str(part) for part in command)
        if "coverage" not in normalized or "run" not in normalized:
            return result
        stdout = re.sub(
            r"(?m)(^=+[^\n]*\bin )\d+(?:\.\d+)?s(?=\s*=+\s*$)",
            rf"\g<1>{next(elapsed)}",
            result.stdout,
        )
        return subprocess.CompletedProcess(
            result.args,
            result.returncode,
            stdout=stdout,
            stderr=result.stderr,
        )

    monkeypatch.setattr(subprocess, "run", run_with_distinct_elapsed_durations)
    independent = {
        manifest.source_path: run_artifact_coverage(manifest, tmp_path).to_dict()
        for manifest in manifests
    }

    batched = {
        path: report.to_dict()
        for path, report in run_artifact_coverage_batch(manifests, tmp_path).items()
    }

    assert batched == independent
    for report in batched.values():
        assert [error["code"] for error in report["errors"]] == [
            ErrorCode.INTERNAL_ERROR.value
        ]
        suggestion = report["errors"][0]["suggestion"]
        assert "test_beta" in suggestion
        assert "1 failed\nin 12.34s" in suggestion
        assert "RuntimeError: downstream reported 1 failed in 12.34s" in suggestion
        assert re.search(
            r"(?m)^=+ 1 failed, 1 passed in <duration> =+$",
            suggestion,
        )


def test_failure_reports_preserve_context_around_unbounded_ci_assertion_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from maid_runner.core.artifact_coverage import run_artifact_coverage

    manifest = load_manifest(_write_failing_project(tmp_path)[0])
    real_run = subprocess.run
    oversized_assertion = "rendered-prefix-" + ("x" * 1_000) + "-rendered-suffix"
    indented_source = '    >       assert "appears to be a stub" in suggestion'
    indented_caret = "            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^"

    def run_with_unbounded_ci_assertion_line(command, *args, **kwargs):
        result = real_run(command, *args, **kwargs)
        normalized = tuple(str(part) for part in command)
        if "coverage" not in normalized or "run" not in normalized:
            return result
        stdout = (
            result.stdout
            + f"\n{indented_source}\n{indented_caret}\n"
            + f"E       assert expected in {oversized_assertion}\n"
        )
        return subprocess.CompletedProcess(
            result.args,
            result.returncode,
            stdout=stdout,
            stderr=result.stderr,
        )

    monkeypatch.setattr(subprocess, "run", run_with_unbounded_ci_assertion_line)

    report = run_artifact_coverage(manifest, tmp_path).to_dict()

    assert [error["code"] for error in report["errors"]] == [
        ErrorCode.INTERNAL_ERROR.value
    ]
    suggestion = report["errors"][0]["suggestion"]
    assert len(suggestion) <= 500
    assert 'assert "appears to be a stub" in suggestion' in suggestion
    assert f"{indented_source}\n{indented_caret}" in suggestion
    assert "rendered-prefix-" in suggestion
    assert "-rendered-suffix" in suggestion

    ordinary_prefix = "    ordinary-long-context-"
    ordinary_suffix = "-ordinary-end"
    ordinary_long_line = (
        ordinary_prefix
        + ("y" * (477 - len(ordinary_prefix) - len(ordinary_suffix)))
        + ordinary_suffix
    )

    def run_with_ordinary_long_line(command, *args, **kwargs):
        result = real_run(command, *args, **kwargs)
        normalized = tuple(str(part) for part in command)
        if "coverage" not in normalized or "run" not in normalized:
            return result
        return subprocess.CompletedProcess(
            result.args,
            result.returncode,
            stdout=result.stdout + f"\n{ordinary_long_line}\n",
            stderr=result.stderr,
        )

    monkeypatch.setattr(subprocess, "run", run_with_ordinary_long_line)

    ordinary_report = run_artifact_coverage(manifest, tmp_path).to_dict()
    ordinary_suggestion = ordinary_report["errors"][0]["suggestion"]
    assert len(ordinary_suggestion) <= 500
    assert ordinary_long_line in ordinary_suggestion

    long_exception = "E       VeryLongError: " + ("z" * 220)

    def run_with_long_exception_before_assertion(command, *args, **kwargs):
        result = real_run(command, *args, **kwargs)
        normalized = tuple(str(part) for part in command)
        if "coverage" not in normalized or "run" not in normalized:
            return result
        stdout = (
            result.stdout
            + f"\n{long_exception}\n{indented_source}\n{indented_caret}\n"
            + f"E       assert expected in {oversized_assertion}\n"
        )
        return subprocess.CompletedProcess(
            result.args,
            result.returncode,
            stdout=stdout,
            stderr=result.stderr,
        )

    monkeypatch.setattr(
        subprocess,
        "run",
        run_with_long_exception_before_assertion,
    )

    long_exception_report = run_artifact_coverage(manifest, tmp_path).to_dict()
    long_exception_suggestion = long_exception_report["errors"][0]["suggestion"]
    assert len(long_exception_suggestion) <= 500
    assert f"{indented_source}\n{indented_caret}" in long_exception_suggestion
    assert "rendered-prefix-" in long_exception_suggestion
    assert "-rendered-suffix" in long_exception_suggestion


def _write_failing_project(root: Path) -> tuple[Path, Path]:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "manifests").mkdir()
    (root / "src" / "__init__.py").write_text("")
    (root / "src" / "alpha.py").write_text('def alpha() -> str:\n    return "alpha"\n')
    (root / "src" / "beta.py").write_text('def beta() -> str:\n    return "beta"\n')
    (root / "tests" / "test_targets.py").write_text(
        "from src.alpha import alpha\n"
        "from src.beta import beta\n\n"
        "def test_alpha():\n"
        '    assert alpha() == "alpha"\n\n'
        "def test_beta():\n"
        '    print("1 failed\\nin 12.34s")\n'
        "    beta()\n"
        '    raise RuntimeError("downstream reported 1 failed in 12.34s")\n'
    )
    return (
        _write_manifest(root, "alpha"),
        _write_manifest(root, "beta"),
    )


def _write_manifest(root: Path, function_name: str) -> Path:
    path = root / "manifests" / f"{function_name}.manifest.yaml"
    path.write_text(
        f"""schema: "2"
goal: "Cover {function_name}"
type: feature
created: "2026-08-09T00:00:00Z"
files:
  edit:
  - path: src/{function_name}.py
    artifacts:
    - kind: function
      name: {function_name}
      args: []
      returns: str
  read:
  - tests/test_targets.py
validate:
- python -m pytest tests/test_targets.py
"""
    )
    return path
