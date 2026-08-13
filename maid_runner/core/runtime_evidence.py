"""Fixture-aware runtime evidence for compatible pytest command groups."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
import hashlib
import importlib.metadata
import inspect
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import MappingProxyType
from typing import Union

from maid_runner.core._pytest_command_normalization import (
    _looks_like_pytest_invocation,
    _normalize_pytest_command,
)
from maid_runner.core._runtime_command_executor import (
    RuntimeCommandExecutor,
    RuntimeCommandRecord,
    RuntimeFileExecution,
    SubprocessRuntimeCommandExecutor,
)
from maid_runner.core._test_command_execution import _test_command_environment
from maid_runner.core._test_command_batching import (
    _batch_compatible_test_commands,
    _batch_group_key,
)
from maid_runner.core.config import load_config
from maid_runner.core.result import (
    BatchTestResult,
    TestRunResult,
    ValidationError,
)
from maid_runner.core.test_runner import _resolve_command
from maid_runner.core.types import Manifest


@dataclass(frozen=True)
class RuntimeCommandIdentity:
    """Stable declaring-manifest and command-index identity."""

    manifest_path: str
    command_index: int
    command: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", tuple(self.command))


@dataclass(frozen=True)
class RuntimeEnvironmentIdentity:
    """Privacy-preserving identity for one resolved pytest environment."""

    resolved_command_prefix: tuple[str, ...]
    working_directory: str
    python_identity: str
    pytest_version: str
    coverage_version: str
    xdist_version: str | None
    configuration_digest: str
    dependency_digest: str
    effective_environment_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "resolved_command_prefix", tuple(self.resolved_command_prefix)
        )


@dataclass(frozen=True)
class RuntimeEvidenceCompleteness:
    """Explicit completeness state and fail-closed diagnostics."""

    complete: bool
    missing_worker_ids: tuple[str, ...] = ()
    unsupported_selectors: tuple[str, ...] = ()
    unresolved_context_ids: tuple[str, ...] = ()
    unproven_fixture_lifecycles: tuple[str, ...] = ()
    diagnostics: tuple[ValidationError, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "missing_worker_ids",
            "unsupported_selectors",
            "unresolved_context_ids",
            "unproven_fixture_lifecycles",
            "diagnostics",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))


@dataclass(frozen=True)
class RuntimeContextEvidence:
    """Attributed node, fixture, collection, or session execution context."""

    context_id: str
    kind: str
    consuming_nodeids: tuple[str, ...]
    execution_data: Mapping[str, RuntimeFileExecution]
    fixture_scope: str | None = None
    autouse: bool = False
    lifecycle_equivalent: bool = False
    fixture_definition_source: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "consuming_nodeids", tuple(self.consuming_nodeids))
        immutable = {
            path: RuntimeFileExecution(
                executed_lines=frozenset(value.executed_lines),
                called_qualnames=frozenset(value.called_qualnames),
            )
            for path, value in self.execution_data.items()
        }
        object.__setattr__(self, "execution_data", MappingProxyType(immutable))


@dataclass(frozen=True)
class RuntimeGroupEvidence:
    """One physical compatible-group execution before exact projection."""

    command: tuple[str, ...]
    selected_nodeids: tuple[str, ...]
    selector_nodeids: Mapping[str, tuple[str, ...]]
    contexts: tuple[RuntimeContextEvidence, ...]
    result: RuntimeCommandRecord
    worker_ids: tuple[str, ...]
    completeness: RuntimeEvidenceCompleteness

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", tuple(self.command))
        object.__setattr__(self, "selected_nodeids", tuple(self.selected_nodeids))
        object.__setattr__(
            self,
            "selector_nodeids",
            MappingProxyType(
                {key: tuple(value) for key, value in self.selector_nodeids.items()}
            ),
        )
        object.__setattr__(self, "contexts", tuple(self.contexts))
        object.__setattr__(self, "worker_ids", tuple(self.worker_ids))


@dataclass(frozen=True)
class RuntimeCommandEvidence:
    """Evidence projected to one immutable original command identity."""

    identity: RuntimeCommandIdentity
    behavior_group_key: tuple[str, tuple[str, ...], tuple[str, ...]]
    selected_nodeids: tuple[str, ...]
    contexts: tuple[RuntimeContextEvidence, ...]
    result: RuntimeCommandRecord
    completeness: RuntimeEvidenceCompleteness
    environment_identity: RuntimeEnvironmentIdentity

    def __post_init__(self) -> None:
        object.__setattr__(self, "selected_nodeids", tuple(self.selected_nodeids))
        object.__setattr__(self, "contexts", tuple(self.contexts))


@dataclass(frozen=True)
class RuntimeEvidenceBundle:
    """Invocation evidence bound to current source, config, and environments."""

    commands: tuple[RuntimeCommandEvidence, ...]
    content_digest: str
    environment_identities: tuple[RuntimeEnvironmentIdentity, ...]
    worker_ids: tuple[str, ...]
    completeness: RuntimeEvidenceCompleteness
    pytest_workers: int | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "commands", tuple(self.commands))
        object.__setattr__(
            self, "environment_identities", tuple(self.environment_identities)
        )
        object.__setattr__(self, "worker_ids", tuple(self.worker_ids))


@dataclass(frozen=True)
class RuntimeEvidenceRun:
    """Ordinary physical-run results plus exact projected evidence."""

    test_result: BatchTestResult
    evidence: RuntimeEvidenceBundle
    executed_identities: tuple[RuntimeCommandIdentity, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "executed_identities", tuple(self.executed_identities))


def combine_runtime_contexts(
    contexts: Sequence[RuntimeContextEvidence],
) -> RuntimeContextEvidence:
    """Combine same-ID worker contexts without losing execution evidence."""
    if not contexts:
        raise ValueError("runtime contexts cannot be empty")
    first = contexts[0]
    if any(
        item.context_id != first.context_id
        or item.kind != first.kind
        or item.fixture_scope != first.fixture_scope
        or item.autouse != first.autouse
        or item.lifecycle_equivalent != first.lifecycle_equivalent
        or item.fixture_definition_source != first.fixture_definition_source
        for item in contexts[1:]
    ):
        raise ValueError("runtime contexts do not describe the same lifecycle")
    nodeids: list[str] = []
    execution: dict[str, RuntimeFileExecution] = {}
    for context in contexts:
        for nodeid in context.consuming_nodeids:
            if nodeid not in nodeids:
                nodeids.append(nodeid)
        for path, value in context.execution_data.items():
            current = execution.get(path)
            execution[path] = RuntimeFileExecution(
                executed_lines=(
                    value.executed_lines
                    if current is None
                    else current.executed_lines | value.executed_lines
                ),
                called_qualnames=(
                    value.called_qualnames
                    if current is None
                    else current.called_qualnames | value.called_qualnames
                ),
            )
    return RuntimeContextEvidence(
        context_id=first.context_id,
        kind=first.kind,
        consuming_nodeids=tuple(nodeids),
        execution_data=execution,
        fixture_scope=first.fixture_scope,
        autouse=first.autouse,
        lifecycle_equivalent=first.lifecycle_equivalent,
        fixture_definition_source=first.fixture_definition_source,
    )


def collect_runtime_evidence(
    manifests: Sequence[Manifest],
    project_root: Path,
    executor: RuntimeCommandExecutor | None = None,
    pytest_workers: Union[int, str, None] = None,
) -> RuntimeEvidenceRun:
    """Execute each compatible pytest group once and project exact evidence."""
    root = Path(project_root).resolve()
    runner = executor or SubprocessRuntimeCommandExecutor()
    entries = _runtime_command_entries(manifests, root)
    grouped: OrderedDict[
        tuple[str, tuple[str, ...], tuple[str, ...]], list[_RuntimeCommandEntry]
    ] = OrderedDict()
    for entry in entries:
        grouped.setdefault(entry.group_key, []).append(entry)

    timeout = load_config(root).artifact_coverage.timeout_seconds
    coverage_config = load_config(root).artifact_coverage
    approved_fixture_sources: dict[str, str] = {}
    for approval in coverage_config.fixture_lifecycle_approvals:
        source = (root / approval.conftest_path).resolve()
        try:
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
        except OSError:
            continue
        if digest == approval.sha256:
            approved_fixture_sources[approval.context_id] = str(source)
    for approval in coverage_config.distribution_fixture_lifecycle_approvals:
        try:
            distribution = importlib.metadata.distribution(approval.distribution)
            source = Path(distribution.locate_file(approval.module_path)).resolve(
                strict=True
            )
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
        except (importlib.metadata.PackageNotFoundError, OSError):
            continue
        if digest == approval.sha256:
            approved_fixture_sources[approval.context_id] = str(source)
    target_files = _runtime_target_files(manifests, root)
    physical_results: list[TestRunResult] = []
    command_evidence: list[RuntimeCommandEvidence] = []
    executed_identities: list[RuntimeCommandIdentity] = []
    environments: list[RuntimeEnvironmentIdentity] = []
    worker_ids: list[str] = []
    group_completeness: list[RuntimeEvidenceCompleteness] = []
    projected_completeness: list[RuntimeEvidenceCompleteness] = []

    for group_key, group_entries in grouped.items():
        command = _group_command(group_key, group_entries, root)
        logical_selectors = tuple(
            dict.fromkeys(
                selector for entry in group_entries for selector in entry.selectors
            )
        )
        environment = _environment_identity(command, root)
        if environment not in environments:
            environments.append(environment)
        executor_parameters = inspect.signature(runner.execute_with_contexts).parameters
        logical_arguments = (
            {"logical_selectors": logical_selectors}
            if "logical_selectors" in executor_parameters
            or any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in executor_parameters.values()
            )
            else {}
        )
        group = runner.execute_with_contexts(
            command,
            target_files,
            root,
            timeout,
            pytest_workers=pytest_workers,
            **logical_arguments,
        )
        collection = next(
            (
                context
                for context in group.contexts
                if context.context_id == "collection:global"
            ),
            None,
        )
        if (
            len(group_entries) > 1
            and collection is not None
            and collection.execution_data
            and "collection:global" not in group.completeness.unresolved_context_ids
        ):
            unresolved = (
                *group.completeness.unresolved_context_ids,
                "collection:global",
            )
            group = replace(
                group,
                completeness=replace(
                    group.completeness,
                    complete=False,
                    unresolved_context_ids=unresolved,
                ),
            )
        remaining_unproven = tuple(
            context_id
            for context_id in group.completeness.unproven_fixture_lifecycles
            if not _fixture_context_is_approved(
                context_id, group.contexts, approved_fixture_sources
            )
        )
        if remaining_unproven != group.completeness.unproven_fixture_lifecycles:
            completeness = replace(
                group.completeness,
                complete=not (
                    group.completeness.missing_worker_ids
                    or group.completeness.unsupported_selectors
                    or group.completeness.unresolved_context_ids
                    or remaining_unproven
                    or group.completeness.diagnostics
                ),
                unproven_fixture_lifecycles=remaining_unproven,
            )
            group = replace(group, completeness=completeness)
        group_completeness.append(group.completeness)
        physical_results.append(_test_result_from_group(group, group_entries))
        for worker_id in group.worker_ids:
            if worker_id not in worker_ids:
                worker_ids.append(worker_id)
        for entry in group_entries:
            selected = _selected_for_entry(entry, group.selector_nodeids)
            projected = _project_contexts(group.contexts, selected)
            completeness = _project_completeness(group, entry, selected, projected)
            projected_completeness.append(completeness)
            command_evidence.append(
                RuntimeCommandEvidence(
                    identity=entry.identity,
                    behavior_group_key=group_key,
                    selected_nodeids=selected,
                    contexts=projected,
                    result=group.result,
                    completeness=completeness,
                    environment_identity=environment,
                )
            )
            executed_identities.append(entry.identity)

    passed = sum(result.success for result in physical_results)
    combined = _combine_completeness((*group_completeness, *projected_completeness))
    bundle = RuntimeEvidenceBundle(
        commands=tuple(command_evidence),
        content_digest=_content_digest(root),
        environment_identities=tuple(environments),
        worker_ids=tuple(worker_ids),
        completeness=combined,
        pytest_workers=pytest_workers,
    )
    return RuntimeEvidenceRun(
        test_result=BatchTestResult(
            results=physical_results,
            total=len(physical_results),
            passed=passed,
            failed=len(physical_results) - passed,
        ),
        evidence=bundle,
        executed_identities=tuple(executed_identities),
    )


def runtime_evidence_is_current(
    bundle: RuntimeEvidenceBundle,
    manifests: Sequence[Manifest],
    project_root: Path,
    pytest_workers: int | str | None = None,
) -> bool:
    """Reject evidence after content or resolved-environment identity changes."""
    root = Path(project_root).resolve()
    if bundle.content_digest != _content_digest(root):
        return False
    if bundle.pytest_workers != pytest_workers:
        return False
    entries = _runtime_command_entries(manifests, root)
    expected_commands = tuple((entry.identity, entry.group_key) for entry in entries)
    actual_commands = tuple(
        (command.identity, command.behavior_group_key) for command in bundle.commands
    )
    if actual_commands != expected_commands:
        return False
    group_commands: OrderedDict[
        tuple[str, tuple[str, ...], tuple[str, ...]], list[tuple[str, ...]]
    ] = OrderedDict()
    for entry in entries:
        group_commands.setdefault(entry.group_key, []).append(entry.resolved_command)
    current = tuple(
        _environment_identity(
            (
                commands[0]
                if group_key[0] == "pytest-exact"
                else _batch_compatible_test_commands(
                    commands,
                    cwd=root,
                    resolve_command=lambda value, **_: value,
                    is_uv_project=lambda _: (root / "uv.lock").exists(),
                )
            ),
            root,
        )
        for group_key, commands in group_commands.items()
    )
    return current == bundle.environment_identities


@dataclass(frozen=True)
class _RuntimeCommandEntry:
    identity: RuntimeCommandIdentity
    resolved_command: tuple[str, ...]
    selectors: tuple[str, ...]
    group_key: tuple[str, tuple[str, ...], tuple[str, ...]]


def _runtime_command_entries(
    manifests: Sequence[Manifest], root: Path
) -> list[_RuntimeCommandEntry]:
    entries: list[_RuntimeCommandEntry] = []
    for manifest in manifests:
        for index, original in enumerate(manifest.validate_commands):
            command = tuple(original)
            resolved = _resolve_command(command, cwd=root)
            normalized = _normalize_pytest_command(resolved)
            group_key = _batch_group_key(
                resolved,
                cwd=root,
                resolve_command=lambda value, **_: value,
                is_uv_project=lambda _: (root / "uv.lock").exists(),
            )
            if normalized is None and not _looks_like_pytest_invocation(resolved):
                continue
            if normalized is None or group_key is None:
                selectors = _lenient_pytest_targets(resolved)
                if not selectors:
                    continue
                group_key = ("pytest-exact", resolved, ())
            else:
                selectors = normalized[1]
            entries.append(
                _RuntimeCommandEntry(
                    identity=RuntimeCommandIdentity(
                        manifest_path=manifest.source_path,
                        command_index=index,
                        command=command,
                    ),
                    resolved_command=resolved,
                    selectors=selectors,
                    group_key=group_key,
                )
            )
    return entries


def _group_command(
    group_key: tuple[str, tuple[str, ...], tuple[str, ...]],
    entries: Sequence[_RuntimeCommandEntry],
    root: Path,
) -> tuple[str, ...]:
    if group_key[0] == "pytest-exact":
        return entries[0].resolved_command
    return _batch_compatible_test_commands(
        [entry.resolved_command for entry in entries],
        cwd=root,
        resolve_command=lambda value, **_: value,
        is_uv_project=lambda _: (root / "uv.lock").exists(),
    )


def _lenient_pytest_targets(command: tuple[str, ...]) -> tuple[str, ...]:
    inner = command[2:] if command[:2] == ("uv", "run") else command
    if inner[:3] and len(inner) >= 3 and inner[1:3] == ("-m", "pytest"):
        args = inner[3:]
    else:
        args = inner[1:]
    targets: list[str] = []
    skip_value = False
    for part in args:
        if skip_value:
            skip_value = False
            continue
        if part in {
            "-k",
            "-m",
            "--maxfail",
            "--tb",
            "--rootdir",
            "-c",
            "-n",
            "--numprocesses",
            "--dist",
        }:
            skip_value = True
            continue
        if part.startswith("-"):
            continue
        targets.append(part)
    return tuple(targets)


def _runtime_target_files(manifests: Sequence[Manifest], root: Path) -> set[str]:
    declared = {
        str((root / spec.path).resolve())
        for manifest in manifests
        for spec in manifest.all_file_specs
        if spec.path.endswith(".py") and (root / spec.path).is_file()
    }
    lifecycle_sources = {
        str(path.resolve())
        for path in root.rglob("conftest.py")
        if path.is_file() and not _excluded_content_path(path.relative_to(root))
    }
    return declared | lifecycle_sources


def _selected_for_entry(
    entry: _RuntimeCommandEntry,
    selector_nodeids: Mapping[str, tuple[str, ...]],
) -> tuple[str, ...]:
    selected: list[str] = []
    for selector in entry.selectors:
        for nodeid in selector_nodeids.get(selector, ()):
            if nodeid not in selected:
                selected.append(nodeid)
    return tuple(selected)


def _fixture_definition_context_id(context_id: str) -> str:
    """Remove only the per-node suffix from a function fixture identity."""
    parts = context_id.split(":", 4)
    if len(parts) == 5 and parts[0] == "fixture" and parts[3] == "function":
        return ":".join(parts[:4])
    return context_id


def _fixture_context_is_approved(
    context_id: str,
    contexts: Sequence[RuntimeContextEvidence],
    approved_sources: Mapping[str, str],
) -> bool:
    definition_id = _fixture_definition_context_id(context_id)
    expected_source = approved_sources.get(definition_id)
    if expected_source is None:
        return False
    return any(
        context.context_id == context_id
        and context.fixture_definition_source == expected_source
        for context in contexts
    )


def _project_contexts(
    contexts: Sequence[RuntimeContextEvidence], selected: tuple[str, ...]
) -> tuple[RuntimeContextEvidence, ...]:
    selected_set = set(selected)
    return tuple(
        context for context in contexts if set(context.consuming_nodeids) & selected_set
    )


def _project_completeness(
    group: RuntimeGroupEvidence,
    entry: _RuntimeCommandEntry,
    selected: tuple[str, ...],
    contexts: tuple[RuntimeContextEvidence, ...],
) -> RuntimeEvidenceCompleteness:
    context_ids = {context.context_id for context in contexts}
    unsupported = tuple(
        selector
        for selector in group.completeness.unsupported_selectors
        if selector in entry.selectors
    )
    unresolved = tuple(group.completeness.unresolved_context_ids)
    unproven = tuple(
        context_id
        for context_id in group.completeness.unproven_fixture_lifecycles
        if context_id in context_ids
    )
    if not selected:
        unsupported = tuple(
            selector
            for selector in dict.fromkeys((*unsupported, *entry.selectors))
            if not any(
                other != selector and other.startswith(selector + "::")
                for other in entry.selectors
            )
        )
    complete = (
        group.completeness.complete
        and not unsupported
        and not unresolved
        and not unproven
        and bool(selected)
    )
    return RuntimeEvidenceCompleteness(
        complete=complete,
        missing_worker_ids=group.completeness.missing_worker_ids,
        unsupported_selectors=unsupported,
        unresolved_context_ids=unresolved,
        unproven_fixture_lifecycles=unproven,
        diagnostics=group.completeness.diagnostics,
    )


def _combine_completeness(
    items: Sequence[RuntimeEvidenceCompleteness],
) -> RuntimeEvidenceCompleteness:
    def merged(name: str):
        return tuple(
            dict.fromkeys(value for item in items for value in getattr(item, name))
        )

    return RuntimeEvidenceCompleteness(
        complete=all(item.complete for item in items),
        missing_worker_ids=merged("missing_worker_ids"),
        unsupported_selectors=merged("unsupported_selectors"),
        unresolved_context_ids=merged("unresolved_context_ids"),
        unproven_fixture_lifecycles=merged("unproven_fixture_lifecycles"),
        diagnostics=merged("diagnostics"),
    )


def _test_result_from_group(
    group: RuntimeGroupEvidence, entries: Sequence[_RuntimeCommandEntry]
) -> TestRunResult:
    return TestRunResult(
        manifest_slug=",".join(
            Path(item.identity.manifest_path).stem for item in entries
        ),
        command=group.result.command,
        exit_code=group.result.returncode,
        stdout=group.result.stdout,
        stderr=group.result.stderr,
        duration_ms=0.0,
    )


def _environment_identity(
    command: tuple[str, ...], root: Path
) -> RuntimeEnvironmentIdentity:
    normalized = _normalize_pytest_command(command)
    prefix = normalized[0] if normalized is not None else command
    versions = _probe_resolved_versions(prefix, root)
    return RuntimeEnvironmentIdentity(
        resolved_command_prefix=prefix,
        working_directory=str(root),
        python_identity=versions["python"],
        pytest_version=versions["pytest"],
        coverage_version=versions["coverage"],
        xdist_version=versions["xdist"],
        configuration_digest=_named_files_digest(
            root,
            (
                ".maidrc.yaml",
                "pyproject.toml",
                "pytest.ini",
                ".pytest.ini",
                "tox.ini",
                "setup.cfg",
            ),
        ),
        dependency_digest=_named_files_digest(
            root,
            (
                "uv.lock",
                "requirements.txt",
                "poetry.lock",
                "Pipfile.lock",
                "pylock.toml",
            ),
        ),
        effective_environment_digest=_mapping_digest(_test_command_environment()),
    )


def _probe_resolved_versions(
    prefix: tuple[str, ...], root: Path
) -> dict[str, str | None]:
    script = (
        "import importlib.metadata,json,sys;"
        "v=lambda n: importlib.metadata.version(n) "
        "if _has(n) else None;"
        "print(json.dumps({'python':sys.version,'pytest':v('pytest'),"
        "'coverage':v('coverage'),'xdist':v('pytest-xdist')}))"
    )
    script = (
        "def _has(n):\n try:\n  importlib.metadata.version(n); return True\n except importlib.metadata.PackageNotFoundError:\n  return False\n"
        + script
    )
    command = _resolved_python_probe_command(prefix, script)
    returncode = -1
    try:
        completed = subprocess.run(
            command,
            cwd=str(root),
            env=_test_command_environment(),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        returncode = completed.returncode
        payload = json.loads(completed.stdout.strip())
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        payload = {}
    if returncode != 0:
        payload = {}
    return {
        "python": str(payload.get("python") or "unavailable"),
        "pytest": str(payload.get("pytest") or "unavailable"),
        "coverage": str(payload.get("coverage") or "unavailable"),
        "xdist": (
            str(payload["xdist"]) if isinstance(payload.get("xdist"), str) else None
        ),
    }


def _resolved_python_probe_command(
    prefix: tuple[str, ...], script: str
) -> tuple[str, ...]:
    if prefix[:2] == ("uv", "run"):
        return ("uv", "run", "python", "-c", script)
    if len(prefix) >= 3 and prefix[1:3] == ("-m", "pytest"):
        return (prefix[0], "-c", script)
    executable = shutil.which(prefix[0]) if prefix else None
    if executable:
        try:
            first_line = Path(executable).read_text(encoding="utf-8").splitlines()[0]
        except (OSError, UnicodeError, IndexError):
            first_line = ""
        if first_line.startswith("#!"):
            interpreter = first_line[2:].strip().split()
            if (
                interpreter
                and Path(interpreter[0]).name == "env"
                and len(interpreter) > 1
            ):
                resolved = shutil.which(interpreter[-1])
                if resolved:
                    return (resolved, "-c", script)
            if interpreter and Path(interpreter[0]).is_file():
                return (interpreter[0], "-c", script)
    return (sys.executable, "-c", script)


def _named_files_digest(root: Path, names: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for name in names:
        path = root / name
        if path.is_file():
            _digest_file(digest, path, root)
    return digest.hexdigest()


def _mapping_digest(values: Mapping[str, str]) -> str:
    digest = hashlib.sha256()
    for key, value in sorted(values.items()):
        digest.update(key.encode())
        digest.update(b"\0")
        digest.update(value.encode())
        digest.update(b"\0")
    return digest.hexdigest()


def _content_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if _excluded_content_path(relative):
            continue
        _digest_file(digest, path, root)
    return digest.hexdigest()


def _digest_file(digest, path: Path, root: Path) -> None:
    digest.update(path.relative_to(root).as_posix().encode())
    digest.update(b"\0")
    digest.update(path.read_bytes())
    digest.update(b"\0")


def _excluded_content_path(relative: Path) -> bool:
    parts = relative.parts
    if parts[:2] == (".maid", "cache"):
        return True
    return any(
        part
        in {
            ".git",
            ".pytest_cache",
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
        }
        for part in parts
    )
