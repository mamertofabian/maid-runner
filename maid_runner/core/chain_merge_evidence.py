"""Recorded detection evidence source for chain-merge (child 2).

A concrete ``DetectionEvidenceSource`` (the child 1 protocol) backed by the
persisted 121-22 knockout evidence cache. It reads already-recorded
detecting-nodeids per artifact and returns ``None`` (UNKNOWN) for anything
unrecorded. It never runs knockout.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from threading import Lock
import time
from typing import Sequence

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from maid_runner.core.chain import ManifestChain
from maid_runner.core.knockout import (
    cached_detecting_nodeids,
    cached_detecting_nodeids_for_file,
)
from maid_runner.core.types import ArtifactKind, Manifest
from maid_runner.core.result import ErrorCode, Location, Severity, ValidationError


class RecordedDetectionEvidenceSource:
    """DetectionEvidenceSource over a merge_key -> detecting-nodeids map."""

    def __init__(self, detection_by_merge_key: dict[str, tuple[str, ...]]) -> None:
        self._by_merge_key = dict(detection_by_merge_key)

    @classmethod
    def from_cache(
        cls,
        manifests: Sequence[Manifest],
        project_root: str,
    ) -> "RecordedDetectionEvidenceSource":
        """Build a source from the persisted knockout evidence cache."""
        return cls(cached_detecting_nodeids(manifests, Path(project_root)))

    def detecting_nodeids_for(self, artifact_key: str) -> tuple[str, ...] | None:
        return self._by_merge_key.get(_merge_key_from_contract_key(artifact_key))


class RecordedCoverageEvidenceSource:
    """File-qualified coverage evidence read from the persisted deep cache."""

    def __init__(
        self,
        coverage_by_artifact: dict[tuple[str, str], bool],
    ) -> None:
        self._by_artifact = dict(coverage_by_artifact)

    @classmethod
    def from_cache(
        cls,
        manifests: Sequence[Manifest],
        project_root: str,
        manifest_dir: str,
    ) -> "RecordedCoverageEvidenceSource":
        """Read current full-repository/default-worker coverage evidence."""
        from maid_runner.core._artifact_coverage_cache import (
            _load_artifact_coverage_cache,
        )

        report = _load_artifact_coverage_cache(
            Path(project_root),
            manifest_dir=manifest_dir,
            pytest_workers=None,
            manifest_paths=None,
        )
        if report is None:
            return cls({})

        paths = {
            file_spec.path
            for manifest in manifests
            for file_spec in manifest.all_file_specs
            if file_spec.artifacts
        }
        indexed: dict[tuple[str, str], bool] = {}
        for finding in report.findings:
            if finding.file_path not in paths:
                continue
            key = (
                finding.file_path,
                _coverage_finding_merge_key(
                    finding.artifact_kind,
                    finding.artifact_name,
                    finding.parent_class,
                ),
            )
            # A fragmented chain may produce duplicate findings. Any E710 must
            # dominate covered evidence so iteration order cannot hide debt.
            indexed[key] = indexed.get(key, True) and finding.executed
        return cls(indexed)

    def coverage_for(self, file_path: str, artifact_key: str) -> bool | None:
        return self._by_artifact.get(
            (file_path, _merge_key_from_contract_key(artifact_key))
        )


@dataclass(frozen=True)
class ChainMergeEvidenceRefreshResult:
    """Live file-scoped evidence and any diagnostics that block baseline use."""

    detection_source: RecordedDetectionEvidenceSource
    coverage_source: RecordedCoverageEvidenceSource
    errors: tuple[ValidationError, ...]

    @property
    def success(self) -> bool:
        return not self.errors


def refresh_chain_merge_evidence(
    chain: ManifestChain,
    file_path: str,
    project_root: str = ".",
) -> ChainMergeEvidenceRefreshResult:
    """Collect live coverage and full-plan, file-filtered knockout evidence."""
    from maid_runner.core.artifact_coverage import (
        evaluate_artifact_coverage_from_evidence,
        merge_artifact_coverage_reports,
    )
    from maid_runner.core._knockout_snapshot import (
        SharedEnvironmentProjectSnapshotBackend,
    )
    from maid_runner.core._artifact_coverage_fallback_worker import (
        _is_non_material,
        _material_state,
        _material_writes,
    )
    from maid_runner.core._runtime_command_executor import (
        SubprocessRuntimeCommandExecutor,
    )
    from maid_runner.core.config import load_config
    from maid_runner.core.knockout import run_knockout_for_file
    from maid_runner.core.runtime_evidence import (
        _content_digest,
        collect_runtime_evidence,
    )

    root = Path(project_root)
    owners = tuple(
        manifest
        for manifest in chain.manifests_for_file(file_path)
        if any(
            file_spec.path == file_path and file_spec.artifacts
            for file_spec in manifest.all_file_specs
        )
    )
    config = load_config(root)
    try:
        source_content_digest = _content_digest(root)
        with SharedEnvironmentProjectSnapshotBackend().create(
            root,
            (file_path,),
            "chain-merge-evidence-refresh",
        ) as snapshot:
            evidence_snapshot_root = snapshot.root
            snapshot_material_state = _material_state(snapshot.root)
            executor = SubprocessRuntimeCommandExecutor(
                environment_overrides=snapshot.environment_overrides,
                environment_removals=snapshot.environment_removals,
            )
            with _PortableMaterialChangeJournal(snapshot.root) as journal:
                evidence_run = collect_runtime_evidence(
                    owners,
                    snapshot.root,
                    executor=executor,
                )
                coverage_evaluation = evaluate_artifact_coverage_from_evidence(
                    owners,
                    snapshot.root,
                    evidence_run.evidence,
                    fallback_executor=executor,
                    fallback_jobs=config.artifact_coverage.fallback_jobs,
                    max_processes=config.test_execution.max_processes,
                )
                changed_paths = journal.changed_paths()
            snapshot_material_state_after = _material_state(snapshot.root)
            changed_paths.update(
                path
                for path in set(snapshot_material_state)
                | set(snapshot_material_state_after)
                if snapshot_material_state.get(path)
                != snapshot_material_state_after.get(path)
            )
            material_writes = _material_writes(
                snapshot.root,
                snapshot_material_state,
                changed_paths,
            )
            transient_writes = {
                path
                for path in changed_paths
                if not _is_non_material(path)
                and not any(
                    part.startswith("pytest-cache-files-") for part in Path(path).parts
                )
            }
            material_writes = tuple(sorted(set(material_writes) | transient_writes))
        if material_writes or _content_digest(root) != source_content_digest:
            return _refresh_harness_failure(
                file_path,
                "Evidence commands changed material project inputs"
                + (f": {', '.join(material_writes)}" if material_writes else "."),
            )
        live_evidence = _rebase_runtime_evidence(
            evidence_run.evidence,
            evidence_snapshot_root,
            root,
            source_content_digest,
        )
    except Exception as exc:
        return _refresh_harness_failure(file_path, str(exc))
    coverage_report = merge_artifact_coverage_reports(
        coverage_evaluation.reports.values()
    )
    knockout_report = run_knockout_for_file(
        chain.active_manifests(),
        root,
        file_path,
        evidence=live_evidence,
        jobs=config.knockout_execution.jobs,
        max_processes=config.test_execution.max_processes,
    )

    detection_by_merge_key: dict[str, set[str]] = {}
    detection_errors: list[ValidationError] = []
    for result in knockout_report.results:
        nodeids = () if result.proof is None else result.proof.detecting_nodeids
        if result.detected and nodeids:
            detection_by_merge_key.setdefault(
                _knockout_result_merge_key(
                    result.artifact_kind,
                    result.artifact_name,
                    result.parent_class,
                ),
                set(),
            ).update(nodeids)
        elif result.detected:
            detection_errors.append(
                ValidationError(
                    code=ErrorCode.ARTIFACT_KNOCKOUT_NOT_DETECTED,
                    message=(
                        "Artifact knockout produced no detecting test nodeids for "
                        f"{result.file_path}:{result.artifact_name}."
                    ),
                    severity=Severity.ERROR,
                    location=Location(file=result.file_path),
                    suggestion=(
                        "Add a focused behavioral test that detects this artifact's "
                        "mutation before capturing a chain-merge baseline."
                    ),
                )
            )

    coverage_by_artifact: dict[tuple[str, str], bool] = {}
    for finding in coverage_report.findings:
        if finding.file_path != file_path:
            continue
        key = (
            finding.file_path,
            _coverage_finding_merge_key(
                finding.artifact_kind,
                finding.artifact_name,
                finding.parent_class,
            ),
        )
        coverage_by_artifact[key] = coverage_by_artifact.get(key, True) and bool(
            finding.executed
        )

    # Artifact coverage measures executable bodies. Structural declarations
    # have no body to execute, so their live evidence comes from the manifest
    # and implementation validation that preceded this refresh. A class is an
    # executable coverage target only when its contract declares methods.
    for manifest in owners:
        for file_spec in manifest.all_file_specs:
            if file_spec.path != file_path:
                continue
            classes_with_methods = {
                artifact.of
                for artifact in file_spec.artifacts
                if artifact.kind == ArtifactKind.METHOD and artifact.of is not None
            }
            for artifact in file_spec.artifacts:
                runtime_target = artifact.kind in {
                    ArtifactKind.FUNCTION,
                    ArtifactKind.METHOD,
                } or (
                    artifact.kind == ArtifactKind.CLASS
                    and artifact.name in classes_with_methods
                )
                if runtime_target:
                    continue
                coverage_by_artifact.setdefault(
                    (file_path, artifact.merge_key()),
                    True,
                )

    return ChainMergeEvidenceRefreshResult(
        detection_source=RecordedDetectionEvidenceSource(
            {
                key: tuple(sorted(nodeids))
                for key, nodeids in detection_by_merge_key.items()
            }
        ),
        coverage_source=RecordedCoverageEvidenceSource(coverage_by_artifact),
        errors=tuple(
            (*coverage_report.errors, *knockout_report.errors, *detection_errors)
        ),
    )


def detection_source_for_file(
    chain: ManifestChain,
    file_path: str,
    project_root: str = ".",
) -> RecordedDetectionEvidenceSource:
    """Build a detection source scoped to one file from the full active plan.

    The cache key is reconstructed from every active manifest before the
    requested file is selected. This preserves repository-wide declaration
    indices while preventing a merge_key shared by another file from leaking
    into this file's acceptance bar.

    Detection is advisory: if knockout specs cannot be built (e.g. a declared
    source file is missing on disk), this degrades to an empty (UNKNOWN) source
    rather than failing the read-only report.
    """
    try:
        return RecordedDetectionEvidenceSource(
            cached_detecting_nodeids_for_file(
                chain.active_manifests(),
                Path(project_root),
                file_path,
            )
        )
    except ValueError:
        return RecordedDetectionEvidenceSource({})


def coverage_source_for_file(
    chain: ManifestChain,
    file_path: str,
    project_root: str = ".",
    manifest_dir: str = "manifests",
) -> RecordedCoverageEvidenceSource:
    """Build a recorded coverage source scoped to one file's manifests."""
    return RecordedCoverageEvidenceSource.from_cache(
        chain.manifests_for_file(file_path),
        project_root,
        manifest_dir,
    )


def _merge_key_from_contract_key(contract_key: str) -> str:
    """Recover the merge_key embedded in a contract_key.

    ``_artifact_contract_key`` returns the merge_key verbatim when there is no
    signature, else ``exact:{len(merge_key)}:{merge_key}{len(sig)}:{sig}``.
    """
    if not contract_key.startswith("exact:"):
        return contract_key
    body = contract_key[len("exact:") :]
    length_str, sep, remainder = body.partition(":")
    if not sep or not length_str.isdigit():
        return contract_key
    return remainder[: int(length_str)]


def _coverage_finding_merge_key(
    artifact_kind: str,
    artifact_name: str,
    parent_class: str | None,
) -> str:
    if parent_class:
        return f"{artifact_kind}:{parent_class}.{artifact_name}"
    return f"{artifact_kind}:{artifact_name}"


def _knockout_result_merge_key(
    artifact_kind: str,
    artifact_name: str,
    parent_class: str | None,
) -> str:
    if parent_class and artifact_kind == "method":
        return f"{artifact_kind}:{parent_class}.{artifact_name}"
    return f"{artifact_kind}:{artifact_name}"


def _rebase_runtime_evidence(
    evidence,
    snapshot_root: Path,
    project_root: Path,
    content_digest: str,
):
    """Bind snapshot-collected evidence to the byte-identical source root."""
    root = str(project_root.resolve())
    environments = {
        item: replace(item, working_directory=root)
        for item in evidence.environment_identities
    }

    def rebase_path(raw: str) -> str:
        path = Path(raw)
        try:
            relative = path.resolve().relative_to(snapshot_root.resolve())
        except ValueError:
            return raw
        return str((project_root.resolve() / relative).resolve())

    def rebase_context(context):
        return replace(
            context,
            execution_data={
                rebase_path(path): execution
                for path, execution in context.execution_data.items()
            },
            fixture_definition_source=(
                rebase_path(context.fixture_definition_source)
                if context.fixture_definition_source is not None
                else None
            ),
        )

    return replace(
        evidence,
        content_digest=content_digest,
        commands=tuple(
            replace(
                command,
                contexts=tuple(rebase_context(item) for item in command.contexts),
                result=replace(
                    command.result,
                    execution_data={
                        rebase_path(path): execution
                        for path, execution in command.result.execution_data.items()
                    },
                ),
                environment_identity=environments.get(
                    command.environment_identity,
                    replace(command.environment_identity, working_directory=root),
                ),
            )
            for command in evidence.commands
        ),
        environment_identities=tuple(
            environments[item] for item in evidence.environment_identities
        ),
    )


def _refresh_harness_failure(
    file_path: str,
    detail: str,
) -> ChainMergeEvidenceRefreshResult:
    error = ValidationError(
        code=ErrorCode.KNOCKOUT_HARNESS_FAILURE,
        message=f"Chain-merge evidence refresh failed: {detail}",
        severity=Severity.ERROR,
        location=Location(file=file_path),
        suggestion=(
            "Resolve the isolated evidence snapshot failure and rerun "
            "--refresh-evidence."
        ),
    )
    return ChainMergeEvidenceRefreshResult(
        detection_source=RecordedDetectionEvidenceSource({}),
        coverage_source=RecordedCoverageEvidenceSource({}),
        errors=(error,),
    )


class _PortableMaterialChangeJournal:
    """Record snapshot writes through watchdog's native platform backends."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root).resolve()
        self._lock = Lock()
        self._paths: set[str] = set()
        self._events: dict[str, set[str]] = {}
        self._observer = Observer()
        journal = self

        class _Handler(FileSystemEventHandler):
            def on_any_event(self, event: FileSystemEvent) -> None:
                if event.is_directory or event.event_type not in {
                    "created",
                    "modified",
                    "deleted",
                    "moved",
                }:
                    return
                journal._record(event.src_path, event.event_type)
                destination = getattr(event, "dest_path", "")
                if destination:
                    journal._record(destination, event.event_type)

        self._observer.schedule(_Handler(), str(self._root), recursive=True)
        self._stopped = False

    def __enter__(self) -> "_PortableMaterialChangeJournal":
        self._observer.start()
        self._synchronize(".maid-journal-ready")
        with self._lock:
            self._paths.clear()
            self._events.clear()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._stop()

    def changed_paths(self) -> set[str]:
        self._synchronize(".maid-journal-flush")
        self._stop()
        with self._lock:
            self._paths.discard(".maid-journal-flush")
            return set(self._paths)

    def _record(self, raw_path: str, event_type: str) -> None:
        try:
            relative = Path(raw_path).resolve().relative_to(self._root).as_posix()
        except (OSError, RuntimeError, ValueError):
            return
        if not relative:
            return
        with self._lock:
            self._paths.add(relative)
            self._events.setdefault(relative, set()).add(event_type)

    def _wait_for_event(self, relative: str, expected: set[str]) -> None:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            with self._lock:
                observed = self._events.get(relative, set())
            if observed.intersection(expected):
                return
            time.sleep(0.01)
        raise RuntimeError(
            "Portable material-write monitor did not become ready for " f"{relative}."
        )

    def _synchronize(self, sentinel_name: str) -> None:
        sentinel = self._root / sentinel_name
        sentinel.write_text("ready", encoding="utf-8")
        self._wait_for_event(sentinel.name, {"created", "modified"})
        sentinel.unlink()
        self._wait_for_event(sentinel.name, {"deleted"})

    def _stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._observer.stop()
        self._observer.join()
