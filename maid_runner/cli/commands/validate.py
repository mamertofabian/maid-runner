"""CLI handler for 'maid validate' command."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from maid_runner.cli.commands._format import (
    format_batch_result,
    format_coherence_result,
    format_validation_result,
    print_error,
)

if TYPE_CHECKING:
    from maid_runner.coherence.result import CoherenceResult
    from maid_runner.core.result import BatchTestResult


def cmd_validate(args: argparse.Namespace) -> int:
    if (
        getattr(args, "manifest_path", None)
        and getattr(args, "file_tracking", False)
        and not getattr(args, "watch_all", False)
    ):
        print_error(
            "--file-tracking is only supported for directory-wide validation",
            json_mode=getattr(args, "json", False),
        )
        return 2

    if args.watch or args.watch_all:
        return _run_watch(args)

    if args.coherence_only:
        return _run_coherence_only(args)

    from maid_runner.core.types import ValidationMode
    from maid_runner.core.validate import ValidationEngine

    mode = ValidationMode(args.mode)
    engine = ValidationEngine(project_root=".")
    check_assertions, check_stubs, fail_on_warnings = _strict_options(args)

    try:
        if args.manifest_path:
            result = engine.validate(
                args.manifest_path,
                mode=mode,
                use_chain=not args.no_chain,
                manifest_dir=args.manifest_dir,
                check_assertions=check_assertions,
                check_stubs=check_stubs,
                fail_on_warnings=fail_on_warnings,
            )
            test_result = None
            if result.success and getattr(args, "worktree_scope", False):
                _apply_worktree_scope_to_result(result, args)
            if result.success and getattr(args, "run_tests", False):
                test_result = run_validate_commands_for_result(args.manifest_path)
            quiet = args.quiet and not (fail_on_warnings and result.warnings)
            output = format_validation_result(
                result,
                json_mode=args.json,
                quiet=quiet,
                test_result=test_result,
                tests_requested=getattr(args, "run_tests", False),
            )
            if output:
                print(output)

            if args.coherence and result.success:
                coherence = run_coherence(args.manifest_dir, args.json)
                _print_coherence_result(coherence, json_mode=args.json)
                if not coherence.success:
                    return 1

            tests_success = test_result is None or test_result.success
            return 0 if result.success and tests_success else 1
        else:
            batch = engine.validate_all(
                args.manifest_dir,
                mode=mode,
                allow_empty=getattr(args, "allow_empty", False),
                check_file_tracking=getattr(args, "file_tracking", False),
                check_assertions=check_assertions,
                check_stubs=check_stubs,
                fail_on_warnings=fail_on_warnings,
            )
            if batch.success and getattr(args, "worktree_scope", False):
                _apply_worktree_scope_to_batch(batch, args)
            quiet = args.quiet and not _has_warning_failure(
                batch, fail_on_warnings=fail_on_warnings
            )
            test_result = None
            if batch.success and getattr(args, "run_tests", False):
                test_result = _run_validate_commands_for_batch(args.manifest_dir)
            print(
                format_batch_result(
                    batch,
                    json_mode=args.json,
                    quiet=quiet,
                    test_result=test_result,
                    tests_requested=getattr(args, "run_tests", False),
                )
            )

            if args.coherence and batch.success:
                coherence = run_coherence(args.manifest_dir, args.json)
                _print_coherence_result(coherence, json_mode=args.json)
                if not coherence.success:
                    return 1

            tests_success = test_result is None or test_result.success
            return 0 if batch.success and tests_success else 1
    except Exception as e:
        print_error(str(e), json_mode=args.json)
        return 2


def run_validate_commands_for_result(
    manifest_path: str,
    fail_fast: bool = False,
) -> BatchTestResult:
    """Run a validated manifest's validate commands through the shared runner."""
    from maid_runner.core.test_runner import run_manifest_tests

    return run_manifest_tests(manifest_path, fail_fast=fail_fast)


def _run_validate_commands_for_batch(
    manifest_dir: str,
    fail_fast: bool = False,
) -> BatchTestResult:
    """Run active manifest validate commands through the shared runner."""
    from maid_runner.core.test_runner import run_tests

    return run_tests(manifest_dir=manifest_dir, fail_fast=fail_fast)


def _run_coherence_only(args: argparse.Namespace) -> int:
    """Run only coherence checks, no structural validation."""
    try:
        result = run_coherence(args.manifest_dir, args.json)
        print(format_coherence_result(result, json_mode=args.json))
        return 0 if result.success else 1
    except Exception as e:
        print_error(str(e), json_mode=args.json)
        return 2


def run_coherence(manifest_dir: str, json_mode: bool) -> "CoherenceResult":
    """Run coherence checks and return the result."""
    from pathlib import Path

    from maid_runner.coherence.engine import CoherenceEngine
    from maid_runner.core.chain import ManifestChain

    del json_mode
    chain = ManifestChain(manifest_dir)
    engine = CoherenceEngine()
    result = engine.validate(chain, project_root=Path.cwd())
    return result


def _print_coherence_result(result: "CoherenceResult", *, json_mode: bool) -> None:
    """Print coherence output after structural validation output."""
    print()
    print(format_coherence_result(result, json_mode=json_mode))


def _strict_options(args: argparse.Namespace) -> tuple[bool, bool, bool]:
    strict = getattr(args, "strict", False)
    check_assertions = getattr(args, "check_assertions", False) or strict
    check_stubs = getattr(args, "check_stubs", False) or strict
    fail_on_warnings = getattr(args, "fail_on_warnings", False) or strict
    return check_assertions, check_stubs, fail_on_warnings


def _has_warning_failure(batch, *, fail_on_warnings: bool) -> bool:
    if not fail_on_warnings:
        return False
    if any(result.warnings for result in batch.results):
        return True
    return any(error.severity.value == "warning" for error in batch.chain_errors)


def _run_watch(args: argparse.Namespace) -> int:
    """Run validation in watch mode."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        print(
            "Error: Watch mode requires watchdog. "
            "Install with: pip install maid-runner[watch]",
            file=sys.stderr,
        )
        return 2

    import time

    class _Handler(FileSystemEventHandler):
        def __init__(self) -> None:
            self.triggered = False

        def on_modified(self, event) -> None:  # type: ignore[override]
            if not event.is_directory and event.src_path.endswith(
                (".py", ".ts", ".tsx", ".svelte", ".yaml", ".json")
            ):
                self.triggered = True

    handler = _Handler()
    observer = Observer()

    # Determine paths to watch
    from pathlib import Path

    watch_paths = [Path(args.manifest_dir)]
    if args.manifest_path and not args.watch_all:
        # Single-manifest watch: also watch files referenced by the manifest
        try:
            from maid_runner.core.manifest import load_manifest

            m = load_manifest(args.manifest_path)
            for fs in m.all_file_specs:
                p = Path(fs.path).parent
                if p.exists():
                    watch_paths.append(p)
        except Exception:
            pass
    else:
        # Watch-all: watch common source directories
        for d in [Path("maid_runner"), Path("src"), Path(".")]:
            if d.is_dir():
                watch_paths.append(d)
                break

    for p in watch_paths:
        if p.exists():
            observer.schedule(handler, str(p), recursive=True)

    observer.start()
    print("Watching for changes... (Ctrl+C to stop)")

    try:
        # Initial run
        _run_validation_pass(args)
        while True:
            time.sleep(0.5)
            if handler.triggered:
                handler.triggered = False
                time.sleep(0.2)  # Debounce
                print("\n--- Change detected, re-validating ---\n")
                _run_validation_pass(args)
    except KeyboardInterrupt:
        observer.stop()
        print("\nStopped watching.")
    observer.join()
    return 0


def _run_validation_pass(args: argparse.Namespace) -> None:
    """Run a single validation pass (used by watch mode)."""
    from maid_runner.core.types import ValidationMode
    from maid_runner.core.validate import ValidationEngine

    mode = ValidationMode(args.mode)
    engine = ValidationEngine(project_root=".")
    check_assertions, check_stubs, fail_on_warnings = _strict_options(args)

    try:
        if args.manifest_path and not args.watch_all:
            result = engine.validate(
                args.manifest_path,
                mode=mode,
                use_chain=not args.no_chain,
                manifest_dir=args.manifest_dir,
                check_assertions=check_assertions,
                check_stubs=check_stubs,
                fail_on_warnings=fail_on_warnings,
            )
            if result.success and getattr(args, "worktree_scope", False):
                _apply_worktree_scope_to_result(result, args)
            quiet = args.quiet and not (fail_on_warnings and result.warnings)
            output = format_validation_result(result, json_mode=args.json, quiet=quiet)
            if output:
                print(output)
        else:
            batch = engine.validate_all(
                args.manifest_dir,
                mode=mode,
                allow_empty=getattr(args, "allow_empty", False),
                check_file_tracking=getattr(args, "file_tracking", False),
                check_assertions=check_assertions,
                check_stubs=check_stubs,
                fail_on_warnings=fail_on_warnings,
            )
            if batch.success and getattr(args, "worktree_scope", False):
                _apply_worktree_scope_to_batch(batch, args)
            quiet = args.quiet and not _has_warning_failure(
                batch, fail_on_warnings=fail_on_warnings
            )
            print(format_batch_result(batch, json_mode=args.json, quiet=quiet))
    except Exception as e:
        print_error(str(e), json_mode=args.json)


def _apply_worktree_scope_to_result(result, args: argparse.Namespace) -> None:
    errors = _run_worktree_scope(args)
    if not errors:
        return
    result.errors.extend(errors)
    result.success = False


def _apply_worktree_scope_to_batch(batch, args: argparse.Namespace) -> None:
    errors = _run_worktree_scope(args)
    if not errors:
        return

    if batch.results:
        target = batch.results[0]
        target.errors.extend(errors)
        if target.success:
            target.success = False
            batch.passed = max(0, batch.passed - 1)
            batch.failed += 1
        return

    batch.chain_errors.extend(errors)
    batch.failed += 1


def _run_worktree_scope(args: argparse.Namespace):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.result import ErrorCode, Severity, ValidationError
    from maid_runner.core.worktree import validate_worktree_scope

    try:
        chain = ManifestChain(args.manifest_dir, ".")
        return validate_worktree_scope(
            ".",
            chain,
            include_tests=getattr(args, "include_tests", False),
        )
    except Exception as exc:
        return [
            ValidationError(
                code=ErrorCode.FILE_READ_ERROR,
                message=f"Worktree scope gate failed: {exc}",
                severity=Severity.ERROR,
            )
        ]
