"""Persistent artifact-coverage evidence cache.

Contract: manifests/drafts/121-21-persist-artifact-coverage-evidence-cache.manifest.yaml
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests.cli.test_verify_deep_evidence_reuse import (
    _stage,
    _verify,
    _write_project,
)


def test_repeat_coverage_stage_reuses_cached_report(
    tmp_path: Path, monkeypatch
) -> None:
    log = tmp_path.parent / f"{tmp_path.name}-executions.log"
    _write_project(tmp_path, log)
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(log))

    first = _verify(tmp_path)
    assert _stage(first, "artifact_coverage").success is True
    log.write_text("")

    second = _verify(tmp_path)
    report = _coverage_report(second)
    assert report.success is True
    assert report.cache_hit is True
    assert log.read_text().splitlines() == ["pytest"]


def test_content_digest_change_misses_cache(tmp_path: Path, monkeypatch) -> None:
    log = tmp_path.parent / f"{tmp_path.name}-executions.log"
    _write_project(tmp_path, log)
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(log))
    _verify(tmp_path)
    (tmp_path / "src" / "target.py").write_text(
        "def target() -> bool:\n    return True\n# changed\n"
    )
    log.write_text("")

    result = _verify(tmp_path)
    report = _coverage_report(result)
    assert report.cache_hit is False
    assert log.read_text().splitlines() == ["pytest", "pytest"]


def test_no_cache_bypasses_stored_result(tmp_path: Path, monkeypatch) -> None:
    log = tmp_path.parent / f"{tmp_path.name}-executions.log"
    _write_project(tmp_path, log)
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(log))
    _verify(tmp_path)
    log.write_text("")

    result = _verify(tmp_path, no_cache=True)
    report = _coverage_report(result)
    assert report.cache_hit is False
    assert log.read_text().splitlines() == ["pytest", "pytest"]


def test_red_coverage_results_are_cached(tmp_path: Path, monkeypatch) -> None:
    log = tmp_path.parent / f"{tmp_path.name}-executions.log"
    _write_project(tmp_path, log, assertion="assert True")
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(log))
    first = _verify(tmp_path)
    assert _stage(first, "artifact_coverage").success is False
    log.write_text("")

    second = _verify(tmp_path)
    report = _coverage_report(second)
    assert report.success is False
    assert report.cache_hit is True
    assert log.read_text().splitlines() == ["pytest"]


def test_cache_key_ignores_git_commit(tmp_path: Path, monkeypatch) -> None:
    log = tmp_path.parent / f"{tmp_path.name}-executions.log"
    _write_project(tmp_path, log)
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(log))
    _git(tmp_path, "init")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")
    _verify(tmp_path)
    _git(tmp_path, "commit", "--allow-empty", "-m", "empty")
    log.write_text("")

    result = _verify(tmp_path)
    assert _coverage_report(result).cache_hit is True
    assert log.read_text().splitlines() == ["pytest"]


def _coverage_report(result):
    return next(
        item
        for item in _stage(result, "artifact_coverage")._errors
        if hasattr(item, "findings")
    )


def _git(root: Path, *args: str) -> None:
    command = ["git", "-C", str(root)]
    if args and args[0] == "commit":
        command.extend(
            [
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "user.email=test@example.com",
                "-c",
                "user.name=Test User",
            ]
        )
    command.extend(args)
    subprocess.run(
        command,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
