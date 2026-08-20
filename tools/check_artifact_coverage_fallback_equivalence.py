"""Compare the serial oracle with isolated artifact-coverage fallbacks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from maid_runner.core._runtime_command_executor import (
    RuntimeCommandExecutor,
    RuntimeCommandRecord,
    RuntimeFileExecution,
    SubprocessRuntimeCommandExecutor,
)
from maid_runner.core.artifact_coverage import (
    _coverage_targets,
    _pytest_args,
    evaluate_artifact_coverage_from_evidence,
    run_artifact_coverage_batch,
)
from maid_runner.core.chain import get_cached_manifest_chain
from maid_runner.core.config import load_config
from maid_runner.core.runtime_evidence import (
    RuntimeEvidenceBundle,
    RuntimeEvidenceCompleteness,
    _content_digest,
    collect_runtime_evidence,
)


class _CheckpointingExecutor:
    """Cache only successful serial-oracle commands for identical content."""

    def __init__(
        self,
        delegate: RuntimeCommandExecutor,
        cache_directory: Path,
        content_digest: str,
    ) -> None:
        self._delegate = delegate
        self._cache_directory = Path(cache_directory)
        self._content_digest = content_digest
        self._command_number = 0

    def execute(
        self,
        command: tuple[str, ...],
        target_files: set[str],
        project_root: Path,
        timeout_seconds: float,
    ) -> RuntimeCommandRecord:
        self._command_number += 1
        cache_path = self._cache_path(command, target_files)
        cached = self._read(cache_path, command, target_files)
        if cached is not None:
            print(
                f"  serial command {self._command_number}: cache hit "
                f"{_display_command(command)}",
                flush=True,
            )
            return cached

        print(
            f"  serial command {self._command_number}: run "
            f"{_display_command(command)}",
            flush=True,
        )
        result = self._delegate.execute(
            command,
            target_files,
            project_root,
            timeout_seconds,
        )
        if result.returncode == 0 and not result.report_errors:
            self._write(cache_path, command, target_files, result)
        return result

    def _cache_path(self, command: tuple[str, ...], target_files: set[str]) -> Path:
        identity = json.dumps(
            {
                "content_digest": self._content_digest,
                "command": list(command),
                "target_files": sorted(target_files),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return self._cache_directory / f"{hashlib.sha256(identity).hexdigest()}.json"

    def _read(
        self,
        cache_path: Path,
        command: tuple[str, ...],
        target_files: set[str],
    ) -> RuntimeCommandRecord | None:
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if payload["content_digest"] != self._content_digest:
                return None
            if tuple(payload["command"]) != command:
                return None
            if payload["target_files"] != sorted(target_files):
                return None
            if payload["returncode"] != 0 or payload.get("report_errors"):
                return None
            execution_data = {
                path: RuntimeFileExecution(
                    executed_lines=frozenset(value["executed_lines"]),
                    called_qualnames=frozenset(value["called_qualnames"]),
                )
                for path, value in payload["execution_data"].items()
            }
            return RuntimeCommandRecord(
                command=command,
                returncode=0,
                stdout=payload["stdout"],
                stderr=payload["stderr"],
                execution_data=execution_data,
                report_errors=(),
            )
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _write(
        self,
        cache_path: Path,
        command: tuple[str, ...],
        target_files: set[str],
        result: RuntimeCommandRecord,
    ) -> None:
        payload = {
            "content_digest": self._content_digest,
            "command": list(command),
            "target_files": sorted(target_files),
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "execution_data": {
                path: {
                    "executed_lines": sorted(execution.executed_lines),
                    "called_qualnames": sorted(execution.called_qualnames),
                }
                for path, execution in result.execution_data.items()
            },
            "report_errors": [],
        }
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(f".{os.getpid()}.tmp")
        try:
            temporary.write_text(
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            temporary.replace(cache_path)
        finally:
            temporary.unlink(missing_ok=True)


def _active_manifests(project_root: Path):
    root = Path(project_root).resolve()
    return tuple(get_cached_manifest_chain(root / "manifests", root).active_manifests())


def _fallback_order(manifests, root: Path) -> list[list[object]]:
    order: list[list[object]] = []
    for manifest in manifests:
        if not _coverage_targets(manifest, root):
            continue
        for command_index, command in enumerate(manifest.validate_commands):
            if _pytest_args(command) is not None:
                order.append([manifest.source_path, command_index, list(command)])
    return order


def _normalized_reports(reports: Mapping[str, object], order) -> list[list[object]]:
    normalized = [
        [manifest_path, report.to_dict()] for manifest_path, report in reports.items()
    ]
    normalized.append(["fallback-order", order])
    return normalized


def _normalized_serial_reports(project_root: Path):
    root = Path(project_root).resolve()
    manifests = _active_manifests(root)
    content_digest = _content_digest(root)
    cache_directory = (
        root
        / ".maid"
        / "cache"
        / "artifact-coverage-serial-equivalence"
        / content_digest
    )
    executor = _CheckpointingExecutor(
        SubprocessRuntimeCommandExecutor(), cache_directory, content_digest
    )
    reports = run_artifact_coverage_batch(manifests, root, executor=executor)
    errors = tuple(error for report in reports.values() for error in report.errors)
    return _normalized_reports(reports, _fallback_order(manifests, root)), errors


def _normalized_isolated_reports(project_root: Path, jobs: int, maximum: int):
    root = Path(project_root).resolve()
    manifests = _active_manifests(root)
    deliberately_incomplete = RuntimeEvidenceBundle(
        commands=(),
        content_digest="force-exact-fallback-inventory",
        environment_identities=(),
        worker_ids=(),
        completeness=RuntimeEvidenceCompleteness(complete=False),
    )
    result = evaluate_artifact_coverage_from_evidence(
        manifests,
        root,
        deliberately_incomplete,
        fallback_jobs=jobs,
        max_processes=maximum,
    )
    return _normalized_reports(result.reports, _fallback_order(manifests, root)), result


def _normalized_grouped_reports(project_root: Path, jobs: int, maximum: int):
    root = Path(project_root).resolve()
    manifests = _active_manifests(root)
    evidence = collect_runtime_evidence(
        manifests,
        root,
        pytest_workers=load_config(root).test_execution.pytest_workers,
    ).evidence
    result = evaluate_artifact_coverage_from_evidence(
        manifests,
        root,
        evidence,
        fallback_jobs=jobs,
        max_processes=maximum,
    )
    return _normalized_reports(result.reports, _fallback_order(manifests, root)), result


def compare_serial_and_isolated_fallbacks(
    project_root: Path,
    jobs: int,
    max_processes: int,
    max_parallel_seconds: float,
) -> int:
    """Compare ordered reports before enforcing the isolated-phase budget."""
    print("PHASE serial oracle: start", flush=True)
    serial_started = time.perf_counter()
    serial, serial_errors = _normalized_serial_reports(Path(project_root))
    serial_elapsed = time.perf_counter() - serial_started
    print(f"PHASE serial oracle: complete in {serial_elapsed:.3f}s", flush=True)
    if serial_errors:
        print(
            f"FAIL serial artifact-coverage oracle produced {len(serial_errors)} errors"
        )
        return 1

    elapsed_runs = []
    for repetition in range(1, 4):
        print(f"PHASE isolated fallback {repetition}/3: start", flush=True)
        started = time.monotonic()
        isolated, result = _normalized_grouped_reports(
            Path(project_root), jobs, max_processes
        )
        elapsed = time.monotonic() - started
        elapsed_runs.append(elapsed)
        print(
            f"PHASE isolated fallback {repetition}/3: complete in {elapsed:.3f}s",
            flush=True,
        )
        if result.fallback_identities or result.serial_fallback_identities:
            print("FAIL grouped phase used exact fallback or legacy replay")
            return 1
        if result.isolated_worker_errors:
            print("FAIL isolated phase produced worker diagnostics")
            return 1
        if result.isolated_material_project_writes:
            print("FAIL isolated phase produced material project writes")
            return 1
        if serial != isolated:
            print("FAIL isolated fallback reports or command order differ from serial")
            return 1
        if elapsed > max_parallel_seconds:
            print(
                "FAIL isolated artifact-coverage fallback phase took "
                f"{elapsed:.3f}s (budget {max_parallel_seconds:.3f}s)"
            )
            return 1
    print(
        "PASS serial/isolated artifact-coverage fallback equivalence: "
        f"serial={serial_elapsed:.3f}s parallel="
        f"{','.join(f'{elapsed:.3f}s' for elapsed in elapsed_runs)} "
        f"budget={max_parallel_seconds:.3f}s"
    )
    return 0


def _display_command(command: tuple[str, ...]) -> str:
    display = " ".join(command)
    return display if len(display) <= 120 else f"{display[:117]}..."


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--max-processes", type=int, default=1)
    parser.add_argument("--max-parallel-seconds", type=float, default=270.0)
    args = parser.parse_args(argv)
    if os.environ.get("PYTEST_CURRENT_TEST"):
        print("SKIP recursive repository artifact-coverage acceptance probe")
        return 0
    return compare_serial_and_isolated_fallbacks(
        args.project_root,
        args.jobs,
        args.max_processes,
        args.max_parallel_seconds,
    )


if __name__ == "__main__":
    sys.exit(main())
