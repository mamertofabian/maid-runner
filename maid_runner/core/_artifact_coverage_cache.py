"""Private persistent artifact-coverage cache shared by verification consumers."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from maid_runner.core.result import ErrorCode, Location, Severity, ValidationError

if TYPE_CHECKING:
    from maid_runner.core.artifact_coverage import ArtifactCoverageFinding


_ARTIFACT_COVERAGE_CACHE_SCHEMA_VERSION = 2


def _artifact_coverage_cache_key(
    root: Path,
    *,
    manifest_dir: str,
    pytest_workers: int | str | None,
    manifest_paths: Sequence[str] | None,
) -> str:
    from maid_runner import __version__
    from maid_runner.core.config import load_config
    from maid_runner.core.runtime_evidence import (
        _content_digest,
        _environment_identity,
    )

    root = root.resolve()
    environment = _environment_identity(("python", "-m", "pytest"), root)
    manifest_root = _manifest_dir_path(root, manifest_dir).resolve()
    try:
        manifest_identity = manifest_root.relative_to(root.resolve()).as_posix()
    except ValueError:
        manifest_identity = str(manifest_root)
    payload = {
        "content_digest": _content_digest(root),
        "manifest_directory": {
            "identity": manifest_identity,
            "content_digest": _content_digest(manifest_root),
        },
        "runner_version": __version__,
        "evidence_mode": load_config(root).artifact_coverage.evidence_mode,
        "pytest_workers": pytest_workers,
        "manifest_paths": None if manifest_paths is None else list(manifest_paths),
        "environment": {
            "resolved_command_prefix": list(environment.resolved_command_prefix),
            "working_directory": environment.working_directory,
            "python_identity": environment.python_identity,
            "pytest_version": environment.pytest_version,
            "coverage_version": environment.coverage_version,
            "xdist_version": environment.xdist_version,
            "configuration_digest": environment.configuration_digest,
            "dependency_digest": environment.dependency_digest,
            "effective_environment_digest": environment.effective_environment_digest,
        },
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


def _artifact_coverage_cache_path(root: Path, cache_key: str) -> Path:
    return (
        root / ".maid" / "cache" / "artifact-coverage-evidence-v2" / f"{cache_key}.json"
    )


def _load_artifact_coverage_cache(
    root: Path,
    *,
    manifest_dir: str,
    pytest_workers: int | str | None,
    manifest_paths: Sequence[str] | None,
):
    path = _artifact_coverage_cache_path(
        root,
        _artifact_coverage_cache_key(
            root,
            manifest_dir=manifest_dir,
            pytest_workers=pytest_workers,
            manifest_paths=manifest_paths,
        ),
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "report"}
        or payload.get("schema_version") != _ARTIFACT_COVERAGE_CACHE_SCHEMA_VERSION
        or not isinstance(payload.get("report"), dict)
    ):
        return None
    try:
        return _artifact_coverage_report_from_cache(
            payload["report"],
            expected_findings=_expected_artifact_coverage_findings(
                root,
                manifest_dir=manifest_dir,
                manifest_paths=manifest_paths,
            ),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _store_artifact_coverage_cache(
    root: Path,
    report,
    *,
    manifest_dir: str,
    pytest_workers: int | str | None,
    manifest_paths: Sequence[str] | None,
) -> None:
    path = _artifact_coverage_cache_path(
        root,
        _artifact_coverage_cache_key(
            root,
            manifest_dir=manifest_dir,
            pytest_workers=pytest_workers,
            manifest_paths=manifest_paths,
        ),
    )
    _atomic_write_json(
        path,
        {
            "schema_version": _ARTIFACT_COVERAGE_CACHE_SCHEMA_VERSION,
            "report": report.to_dict(),
        },
    )


def _artifact_coverage_report_from_cache(
    payload: dict,
    *,
    expected_findings: Counter[tuple[str, str, str | None, str]],
):
    from maid_runner.core.artifact_coverage import (
        ArtifactCoverageExecutionSummary,
        ArtifactCoverageFinding,
        ArtifactCoverageReport,
    )

    if not _valid_cached_coverage_report_payload(payload):
        raise ValueError("invalid artifact coverage cache report")

    findings = tuple(
        ArtifactCoverageFinding(
            artifact_name=item["artifact_name"],
            artifact_kind=item["artifact_kind"],
            parent_class=item.get("parent_class"),
            file_path=item["file_path"],
            executed=bool(item["executed"]),
        )
        for item in payload["findings"]
    )
    errors = tuple(_validation_error_from_cache(item) for item in payload["errors"])
    execution = None
    raw_execution = payload.get("execution")
    if isinstance(raw_execution, dict):
        execution = ArtifactCoverageExecutionSummary(
            command_count=int(raw_execution["command_count"]),
            isolated_count=int(raw_execution["isolated_count"]),
            serial_count=int(raw_execution["serial_count"]),
            lane_count=int(raw_execution["lane_count"]),
        )
    report = ArtifactCoverageReport(
        findings=findings,
        errors=errors,
        execution=execution,
        provenance=payload.get("provenance"),
        cache_hit=True,
    )
    if payload["success"] is not report.success:
        raise ValueError("cached artifact coverage success is inconsistent")
    actual_findings = Counter(
        (
            finding.artifact_name,
            finding.artifact_kind,
            finding.parent_class,
            finding.file_path,
        )
        for finding in findings
    )
    if actual_findings != expected_findings:
        raise ValueError("cached artifact coverage findings are incomplete")
    expected_e710 = Counter(
        (
            (
                "No body line of declared artifact "
                f"'{_cached_finding_display_name(finding)}' was executed by tests"
            ),
            finding.file_path,
        )
        for finding in findings
        if not finding.executed
    )
    actual_e710 = Counter(
        (
            error.message,
            error.location.file if error.location is not None else None,
        )
        for error in errors
        if error.code == ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS
    )
    if actual_e710 != expected_e710:
        raise ValueError("cached artifact coverage E710 errors are inconsistent")
    return report


def _expected_artifact_coverage_findings(
    root: Path,
    *,
    manifest_dir: str,
    manifest_paths: Sequence[str] | None,
) -> Counter[tuple[str, str, str | None, str]]:
    from maid_runner.core.artifact_coverage import _coverage_targets
    from maid_runner.core.chain import get_cached_manifest_chain

    chain = get_cached_manifest_chain(_manifest_dir_path(root, manifest_dir), root)
    selected = chain.active_manifests()
    if manifest_paths is not None:
        wanted = {Path(path).as_posix() for path in manifest_paths}
        selected = tuple(
            manifest
            for manifest in selected
            if manifest.source_path in wanted
            or Path(manifest.source_path).as_posix() in wanted
        )
    return Counter(
        (
            artifact.name,
            artifact.kind.value,
            artifact.of,
            file_path,
        )
        for manifest in selected
        for file_path, artifact in _coverage_targets(manifest, root)
    )


def _cached_finding_display_name(finding: ArtifactCoverageFinding) -> str:
    if finding.parent_class:
        return f"{finding.parent_class}.{finding.artifact_name}"
    return finding.artifact_name


def _valid_cached_coverage_report_payload(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    required = {"success", "findings", "errors"}
    allowed = required | {"execution", "provenance"}
    if not required.issubset(payload) or not set(payload).issubset(allowed):
        return False
    if not isinstance(payload["success"], bool):
        return False
    if not isinstance(payload["findings"], list) or not all(
        _valid_cached_coverage_finding(item) for item in payload["findings"]
    ):
        return False
    if not isinstance(payload["errors"], list) or not all(
        _valid_cached_validation_error(item) for item in payload["errors"]
    ):
        return False
    execution = payload.get("execution")
    if execution is not None and not _valid_cached_execution_summary(execution):
        return False
    provenance = payload.get("provenance")
    return provenance is None or provenance in {"derived", "exact"}


def _valid_cached_coverage_finding(payload: object) -> bool:
    if not isinstance(payload, dict) or set(payload) != {
        "artifact_name",
        "artifact_kind",
        "parent_class",
        "file_path",
        "executed",
    }:
        return False
    return (
        isinstance(payload["artifact_name"], str)
        and bool(payload["artifact_name"])
        and isinstance(payload["artifact_kind"], str)
        and bool(payload["artifact_kind"])
        and (
            payload["parent_class"] is None or isinstance(payload["parent_class"], str)
        )
        and isinstance(payload["file_path"], str)
        and bool(payload["file_path"])
        and isinstance(payload["executed"], bool)
    )


def _valid_cached_validation_error(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    required = {"code", "message", "severity"}
    allowed = required | {"location", "suggestion"}
    if not required.issubset(payload) or not set(payload).issubset(allowed):
        return False
    try:
        ErrorCode(payload["code"])
        Severity(payload["severity"])
    except (TypeError, ValueError):
        return False
    if not isinstance(payload["message"], str):
        return False
    suggestion = payload.get("suggestion")
    if suggestion is not None and not isinstance(suggestion, str):
        return False
    location = payload.get("location")
    if location is None:
        return True
    if not isinstance(location, dict) or set(location) != {"file", "line", "column"}:
        return False
    return (
        isinstance(location["file"], str)
        and bool(location["file"])
        and (location["line"] is None or isinstance(location["line"], int))
        and (location["column"] is None or isinstance(location["column"], int))
    )


def _valid_cached_execution_summary(payload: object) -> bool:
    if not isinstance(payload, dict) or set(payload) != {
        "command_count",
        "isolated_count",
        "serial_count",
        "lane_count",
    }:
        return False
    return all(
        isinstance(payload[name], int)
        and not isinstance(payload[name], bool)
        and payload[name] >= 0
        for name in payload
    )


def _atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _validation_error_from_cache(payload: dict) -> ValidationError:
    location = None
    raw_location = payload.get("location")
    if isinstance(raw_location, dict) and raw_location.get("file"):
        location = Location(
            file=str(raw_location["file"]),
            line=raw_location.get("line"),
            column=raw_location.get("column"),
        )
    return ValidationError(
        code=ErrorCode(payload["code"]),
        message=str(payload.get("message", "")),
        severity=Severity(payload.get("severity", Severity.ERROR.value)),
        location=location,
        suggestion=payload.get("suggestion"),
    )


def _manifest_dir_path(root: Path, manifest_dir: str) -> Path:
    path = Path(manifest_dir)
    if path.is_absolute():
        return path
    return root / path
