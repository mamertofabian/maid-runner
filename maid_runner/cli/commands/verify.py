"""CLI handler for 'maid verify' command."""

from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path
from typing import Union

from maid_runner.cli.commands._format import format_verify_result, print_error
from maid_runner.core.result import VerificationResult, VerificationStageResult


def cmd_verify(args: argparse.Namespace) -> int:
    try:
        result = _run_verify(
            manifest_dir=args.manifest_dir,
            project_root=".",
            allow_empty=getattr(args, "allow_empty", False),
            fail_fast=getattr(args, "fail_fast", True),
            check_assertions=getattr(args, "check_assertions", False)
            or getattr(args, "strict", False),
            check_stubs=getattr(args, "check_stubs", False)
            or getattr(args, "strict", False),
            fail_on_warnings=getattr(args, "fail_on_warnings", False)
            or getattr(args, "strict", False),
            require_worktree_scope=getattr(args, "worktree_scope", False),
            include_tests=getattr(args, "include_tests", False),
        )
        print(format_verify_result(result, json_mode=getattr(args, "json", False)))
        return 0 if _result_success(result) else 1
    except Exception as exc:
        print_error(str(exc), json_mode=getattr(args, "json", False))
        return 2


def run_verify(
    manifest_dir: str,
    project_root: Union[str, Path],
) -> VerificationResult:
    return _run_verify(manifest_dir=manifest_dir, project_root=project_root)


def _run_verify(
    *,
    manifest_dir: str,
    project_root: Union[str, Path],
    allow_empty: bool = False,
    fail_fast: bool = True,
    check_assertions: bool = False,
    check_stubs: bool = False,
    fail_on_warnings: bool = False,
    require_worktree_scope: bool = False,
    include_tests: bool = False,
) -> VerificationResult:
    from maid_runner.core.types import ValidationMode
    from maid_runner.core.validate import ValidationEngine

    started = time.monotonic()
    root = Path(project_root)
    engine = ValidationEngine(project_root=root)
    stages: list[VerificationStageResult] = []

    stages.append(
        _validation_stage(
            "schema",
            engine,
            manifest_dir,
            ValidationMode.SCHEMA,
            allow_empty=allow_empty,
            fail_on_warnings=fail_on_warnings,
        )
    )
    if not _should_continue(stages[-1], fail_fast):
        return _verification_result(stages, started)

    stages.append(
        _validation_stage(
            "behavioral",
            engine,
            manifest_dir,
            ValidationMode.BEHAVIORAL,
            allow_empty=allow_empty,
            check_assertions=check_assertions,
            fail_on_warnings=fail_on_warnings,
        )
    )
    if not _should_continue(stages[-1], fail_fast):
        return _verification_result(stages, started)

    stages.append(
        _validation_stage(
            "implementation",
            engine,
            manifest_dir,
            ValidationMode.IMPLEMENTATION,
            allow_empty=allow_empty,
            check_stubs=check_stubs,
            fail_on_warnings=fail_on_warnings,
        )
    )
    if not _should_continue(stages[-1], fail_fast):
        return _verification_result(stages, started)

    if _allow_empty_without_active_manifests(root, manifest_dir, allow_empty):
        skip_message = "Skipped because --allow-empty found no active manifests"
        stages.append(_skipped_stage("coherence", skip_message))
        stages.append(_skipped_stage("file_tracking", skip_message))
        if require_worktree_scope:
            stages.append(_worktree_scope_stage(root, manifest_dir, include_tests))
            if not _should_continue(stages[-1], fail_fast):
                return _verification_result(stages, started)
        elif _git_metadata_available(root):
            stages.append(_skipped_stage("worktree_scope", skip_message))
        stages.append(_skipped_stage("tests", skip_message))
        return _verification_result(stages, started)

    stages.append(_coherence_stage(root, manifest_dir))
    if not _should_continue(stages[-1], fail_fast):
        return _verification_result(stages, started)

    stages.append(_file_tracking_stage(root, manifest_dir, engine))
    if not _should_continue(stages[-1], fail_fast):
        return _verification_result(stages, started)

    if require_worktree_scope or _git_metadata_available(root):
        stages.append(_worktree_scope_stage(root, manifest_dir, include_tests))
        if not _should_continue(stages[-1], fail_fast):
            return _verification_result(stages, started)

    stages.append(_tests_stage(root, manifest_dir, fail_fast))

    return _verification_result(stages, started)


def _validation_stage(
    name: str,
    engine,
    manifest_dir: str,
    mode,
    *,
    allow_empty: bool,
    check_assertions: bool = False,
    check_stubs: bool = False,
    fail_on_warnings: bool = False,
) -> VerificationStageResult:
    started = time.monotonic()
    try:
        result = engine.validate_all(
            manifest_dir,
            mode=mode,
            allow_empty=allow_empty,
            check_assertions=check_assertions,
            check_stubs=check_stubs,
            fail_on_warnings=fail_on_warnings,
        )
        return VerificationStageResult(
            name=name,
            success=result.success,
            _duration_ms=_elapsed_ms(started),
            _validation=result,
        )
    except Exception as exc:
        return _error_stage(name, started, exc)


def _coherence_stage(root: Path, manifest_dir: str) -> VerificationStageResult:
    started = time.monotonic()
    try:
        from maid_runner.coherence.engine import CoherenceEngine
        from maid_runner.core.chain import ManifestChain

        chain = ManifestChain(_manifest_dir_path(root, manifest_dir), root)
        result = CoherenceEngine().validate(chain, project_root=root)
        return VerificationStageResult(
            name="coherence",
            success=result.success,
            _duration_ms=_elapsed_ms(started),
            _coherence=result,
        )
    except Exception as exc:
        return _error_stage("coherence", started, exc)


def _file_tracking_stage(
    root: Path,
    manifest_dir: str,
    engine,
) -> VerificationStageResult:
    started = time.monotonic()
    try:
        from maid_runner.core.chain import ManifestChain

        chain = ManifestChain(_manifest_dir_path(root, manifest_dir), root)
        report = engine.run_file_tracking(chain)
        return VerificationStageResult(
            name="file_tracking",
            success=not report.undeclared and not report.registered,
            _duration_ms=_elapsed_ms(started),
            _file_tracking=report,
        )
    except Exception as exc:
        return _error_stage("file_tracking", started, exc)


def _worktree_scope_stage(
    root: Path,
    manifest_dir: str,
    include_tests: bool,
) -> VerificationStageResult:
    started = time.monotonic()
    try:
        from maid_runner.core.chain import ManifestChain
        from maid_runner.core.worktree import validate_worktree_scope

        chain = ManifestChain(_manifest_dir_path(root, manifest_dir), root)
        errors = validate_worktree_scope(root, chain, include_tests=include_tests)
        return VerificationStageResult(
            name="worktree_scope",
            success=not errors,
            _duration_ms=_elapsed_ms(started),
            _errors=tuple(errors),
        )
    except Exception as exc:
        return _error_stage("worktree_scope", started, exc)


def _tests_stage(
    root: Path,
    manifest_dir: str,
    fail_fast: bool,
) -> VerificationStageResult:
    started = time.monotonic()
    try:
        from maid_runner.core.test_runner import run_tests

        result = run_tests(
            manifest_dir=manifest_dir,
            project_root=root,
            fail_fast=fail_fast,
        )
        return VerificationStageResult(
            name="tests",
            success=result.success,
            _duration_ms=_elapsed_ms(started),
            _tests=result,
        )
    except Exception as exc:
        return _error_stage("tests", started, exc)


def _error_stage(
    name: str,
    started: float,
    exc: Exception,
) -> VerificationStageResult:
    return VerificationStageResult(
        name=name,
        success=False,
        _duration_ms=_elapsed_ms(started),
        _errors=(str(exc),),
    )


def _skipped_stage(name: str, message: str) -> VerificationStageResult:
    return VerificationStageResult(name=name, success=True, _errors=(message,))


def _allow_empty_without_active_manifests(
    root: Path,
    manifest_dir: str,
    allow_empty: bool,
) -> bool:
    if not allow_empty:
        return False

    manifest_path = _manifest_dir_path(root, manifest_dir)
    if not manifest_path.exists():
        return True

    try:
        from maid_runner.core.chain import ManifestChain

        chain = ManifestChain(manifest_path, root)
        return not chain.active_manifests() and not chain.load_errors
    except Exception:
        return False


def _should_continue(stage: VerificationStageResult, fail_fast: bool) -> bool:
    return stage.success or not fail_fast


def _verification_result(
    stages: list[VerificationStageResult],
    started: float,
) -> VerificationResult:
    return VerificationResult(stages=tuple(stages), duration_ms=_elapsed_ms(started))


def _result_success(result: VerificationResult) -> bool:
    return all(stage.success for stage in result.stages)


def _elapsed_ms(started: float) -> float:
    return (time.monotonic() - started) * 1000


def _manifest_dir_path(root: Path, manifest_dir: str) -> Path:
    path = Path(manifest_dir)
    if path.is_absolute():
        return path
    return root / path


def _git_metadata_available(root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"
