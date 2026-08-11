"""Runtime execution coverage checks for declared Python artifacts."""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from maid_runner.core._runtime_command_executor import (
    RuntimeCommandExecutor,
    RuntimeFileExecution,
    SubprocessRuntimeCommandExecutor,
)
from maid_runner.core.config import load_config
from maid_runner.core.diagnostic_policy import no_validator_severity
from maid_runner.core.result import ErrorCode, Location, ValidationError
from maid_runner.core.types import ArtifactKind, ArtifactSpec, Manifest
from maid_runner.core.runtime_evidence import (
    RuntimeCommandEvidence,
    RuntimeCommandIdentity,
    RuntimeEvidenceBundle,
    runtime_evidence_is_current,
)


_PYTEST_SUMMARY_DURATION = re.compile(
    r"(?m)^(?P<prefix>(?:=+[ \t]*)?(?:\d+[ \t]+(?:failed|passed|skipped|"
    r"xfailed|xpassed|deselected|error|errors|warning|warnings)"
    r"(?:,[ \t]*)?)+[ \t]+in[ \t]+)\d+(?:\.\d+)?s"
    r"(?P<suffix>[ \t]*=+)?(?P<trailing>[ \t]*\r?)$"
)


@dataclass(frozen=True)
class ArtifactCoverageFinding:
    artifact_name: str
    artifact_kind: str
    parent_class: str | None
    file_path: str
    executed: bool

    def to_dict(self) -> dict:
        return {
            "artifact_name": self.artifact_name,
            "artifact_kind": self.artifact_kind,
            "parent_class": self.parent_class,
            "file_path": self.file_path,
            "executed": self.executed,
        }


@dataclass(frozen=True)
class ArtifactCoverageReport:
    findings: tuple[ArtifactCoverageFinding, ...]
    errors: tuple[ValidationError, ...]

    @property
    def success(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "findings": [finding.to_dict() for finding in self.findings],
            "errors": [error.to_dict() for error in self.errors],
        }


@dataclass(frozen=True)
class EvidenceArtifactCoverageResult:
    """Per-manifest reports and exact commands used as safe fallbacks."""

    reports: Mapping[str, ArtifactCoverageReport]
    fallback_identities: tuple[RuntimeCommandIdentity, ...]
    complete: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "reports", MappingProxyType(dict(self.reports)))
        object.__setattr__(self, "fallback_identities", tuple(self.fallback_identities))


def coverage_is_available() -> bool:
    try:
        import coverage  # noqa: F401
    except ImportError:
        return False
    return True


def run_artifact_coverage(
    manifest: Manifest,
    project_root: Path,
    executor: RuntimeCommandExecutor | None = None,
) -> ArtifactCoverageReport:
    if executor is None:
        if not coverage_is_available():
            return _coverage_unavailable_report()
        executor = SubprocessRuntimeCommandExecutor()

    root = Path(project_root)
    timeout_seconds = load_config(root).artifact_coverage.timeout_seconds
    coverage_targets = _coverage_targets(manifest, root)
    if not coverage_targets:
        return ArtifactCoverageReport(findings=(), errors=())

    target_files = {
        str((root / file_path).resolve()) for file_path, _artifact in coverage_targets
    }
    command_errors: list[ValidationError] = []
    report_errors: list[ValidationError] = []
    execution_data: dict[str, RuntimeFileExecution] = {}
    for original_command in manifest.validate_commands:
        pytest_args = _pytest_args(original_command)
        if pytest_args is None:
            continue
        command_run = executor.execute(
            pytest_args,
            target_files,
            root,
            timeout_seconds,
        )
        if command_run.returncode != 0:
            command_errors.append(
                _coverage_command_error(
                    original_command,
                    stdout=command_run.stdout,
                    stderr=command_run.stderr,
                )
            )
        if command_run.report_errors and not report_errors:
            report_errors.extend(command_run.report_errors)
        _merge_execution_data(execution_data, command_run.execution_data)

    if report_errors:
        execution_data = {}

    findings, execution_errors = _evaluate_targets(
        root, coverage_targets, execution_data
    )
    return ArtifactCoverageReport(
        findings=tuple(findings),
        errors=tuple(command_errors + report_errors + execution_errors),
    )


def run_artifact_coverage_batch(
    manifests: Sequence[Manifest],
    project_root: Path,
    executor: RuntimeCommandExecutor | None = None,
) -> dict[str, ArtifactCoverageReport]:
    """Run shared pytest commands once and return per-manifest reports."""
    ordered_manifests = list(manifests)
    if executor is None:
        if not coverage_is_available():
            return {
                manifest.source_path: _coverage_unavailable_report()
                for manifest in ordered_manifests
            }
        executor = SubprocessRuntimeCommandExecutor()

    root = Path(project_root)
    timeout_seconds = load_config(root).artifact_coverage.timeout_seconds
    targets_by_manifest = {
        manifest.source_path: _coverage_targets(manifest, root)
        for manifest in ordered_manifests
    }
    commands_by_manifest: dict[str, list[tuple[tuple[str, ...], tuple[str, ...]]]] = {}
    target_files_by_command: dict[tuple[str, ...], set[str]] = {}

    for manifest in ordered_manifests:
        targets = targets_by_manifest[manifest.source_path]
        command_entries: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
        if targets:
            target_files = {
                str((root / file_path).resolve()) for file_path, _artifact in targets
            }
            for command in manifest.validate_commands:
                pytest_args = _pytest_args(command)
                if pytest_args is None:
                    continue
                command_entries.append((pytest_args, command))
                target_files_by_command.setdefault(pytest_args, set()).update(
                    target_files
                )
        commands_by_manifest[manifest.source_path] = command_entries

    command_runs = {
        pytest_args: executor.execute(
            pytest_args,
            target_files,
            root,
            timeout_seconds,
        )
        for pytest_args, target_files in target_files_by_command.items()
    }

    reports: dict[str, ArtifactCoverageReport] = {}
    for manifest in ordered_manifests:
        manifest_path = manifest.source_path
        targets = targets_by_manifest[manifest_path]
        command_entries = commands_by_manifest[manifest_path]
        if not targets:
            reports[manifest_path] = ArtifactCoverageReport(findings=(), errors=())
            continue
        if not command_entries:
            reports[manifest_path] = run_artifact_coverage(
                manifest,
                root,
                executor=executor,
            )
            continue

        command_errors: list[ValidationError] = []
        report_errors: list[ValidationError] = []
        execution_data: dict[str, RuntimeFileExecution] = {}
        for pytest_args, original_command in command_entries:
            command_run = command_runs[pytest_args]
            if command_run.returncode != 0:
                command_errors.append(
                    _coverage_command_error(
                        original_command,
                        stdout=command_run.stdout,
                        stderr=command_run.stderr,
                    )
                )
            if command_run.report_errors and not report_errors:
                report_errors.extend(command_run.report_errors)
            _merge_execution_data(execution_data, command_run.execution_data)

        if report_errors:
            execution_data = {}
        findings, execution_errors = _evaluate_targets(
            root,
            targets,
            execution_data,
        )
        reports[manifest_path] = ArtifactCoverageReport(
            findings=tuple(findings),
            errors=tuple(command_errors + report_errors + execution_errors),
        )
    return reports


def evaluate_artifact_coverage_from_evidence(
    manifests: Sequence[Manifest],
    project_root: Path,
    evidence: RuntimeEvidenceBundle,
    fallback_executor: RuntimeCommandExecutor | None = None,
) -> EvidenceArtifactCoverageResult:
    """Evaluate exact attributed contexts, falling back per unsafe command."""
    ordered_manifests = list(manifests)
    root = Path(project_root)
    current = runtime_evidence_is_current(
        evidence,
        ordered_manifests,
        root,
        pytest_workers=evidence.pytest_workers,
    )
    evidence_by_identity = {
        (
            command.identity.manifest_path,
            command.identity.command_index,
            command.identity.command,
        ): command
        for command in evidence.commands
    }
    timeout_seconds = load_config(root).artifact_coverage.timeout_seconds
    executor = fallback_executor
    fallback_identities: list[RuntimeCommandIdentity] = []
    reports: dict[str, ArtifactCoverageReport] = {}

    for manifest in ordered_manifests:
        targets = _coverage_targets(manifest, root)
        if not targets:
            reports[manifest.source_path] = ArtifactCoverageReport((), ())
            continue
        target_files = {
            str((root / file_path).resolve()) for file_path, _artifact in targets
        }
        command_errors: list[ValidationError] = []
        report_errors: list[ValidationError] = []
        execution_data: dict[str, RuntimeFileExecution] = {}

        for index, original_command in enumerate(manifest.validate_commands):
            pytest_args = _pytest_args(original_command)
            if pytest_args is None:
                continue
            identity = RuntimeCommandIdentity(
                manifest_path=manifest.source_path,
                command_index=index,
                command=original_command,
            )
            command_evidence = evidence_by_identity.get(
                (manifest.source_path, index, tuple(original_command))
            )
            if not current or not _command_evidence_is_reusable(command_evidence):
                if executor is None:
                    if not coverage_is_available():
                        reports = {
                            item.source_path: _coverage_unavailable_report()
                            for item in ordered_manifests
                        }
                        return EvidenceArtifactCoverageResult(
                            reports=reports,
                            fallback_identities=tuple(fallback_identities),
                            complete=False,
                        )
                    executor = SubprocessRuntimeCommandExecutor()
                command_run = executor.execute(
                    pytest_args,
                    target_files,
                    root,
                    timeout_seconds,
                )
                fallback_identities.append(identity)
                command_execution = command_run.execution_data
            else:
                command_run = command_evidence.result
                command_execution = _execution_from_attributed_contexts(
                    command_evidence
                )

            if command_run.returncode != 0:
                command_errors.append(
                    _coverage_command_error(
                        original_command,
                        stdout=command_run.stdout,
                        stderr=command_run.stderr,
                    )
                )
            if command_run.report_errors and not report_errors:
                report_errors.extend(command_run.report_errors)
            _merge_execution_data(execution_data, command_execution)

        if report_errors:
            execution_data = {}
        findings, execution_errors = _evaluate_targets(root, targets, execution_data)
        reports[manifest.source_path] = ArtifactCoverageReport(
            findings=tuple(findings),
            errors=tuple(command_errors + report_errors + execution_errors),
        )

    return EvidenceArtifactCoverageResult(
        reports=reports,
        fallback_identities=tuple(fallback_identities),
        complete=current and not fallback_identities,
    )


def _command_evidence_is_reusable(
    command: RuntimeCommandEvidence | None,
) -> bool:
    return command is not None and command.completeness.complete


def _execution_from_attributed_contexts(
    command: RuntimeCommandEvidence,
) -> dict[str, RuntimeFileExecution]:
    selected = set(command.selected_nodeids)
    combined: dict[str, RuntimeFileExecution] = {}
    for context in command.contexts:
        if not selected.intersection(context.consuming_nodeids):
            continue
        if context.kind == "fixture" and not (
            context.fixture_scope == "function"
            and not context.autouse
            and context.lifecycle_equivalent
        ):
            continue
        if context.kind not in {"node", "fixture", "collection"}:
            continue
        _union_execution_data(combined, context.execution_data)
    return combined


def _union_execution_data(
    destination: dict[str, RuntimeFileExecution],
    source: Mapping[str, RuntimeFileExecution],
) -> None:
    for file_path, execution in source.items():
        existing = destination.get(file_path)
        destination[file_path] = RuntimeFileExecution(
            executed_lines=(
                execution.executed_lines
                if existing is None
                else existing.executed_lines | execution.executed_lines
            ),
            called_qualnames=(
                execution.called_qualnames
                if existing is None
                else existing.called_qualnames | execution.called_qualnames
            ),
        )


def _coverage_unavailable_report() -> ArtifactCoverageReport:
    return ArtifactCoverageReport(
        findings=(),
        errors=(
            ValidationError(
                code=ErrorCode.VALIDATOR_NOT_AVAILABLE,
                message=(
                    "Artifact coverage requires coverage.py from the quality "
                    "extra; install maid-runner[quality]."
                ),
                severity=no_validator_severity("coverage.py"),
            ),
        ),
    )


def _coverage_command_error(
    command: tuple[str, ...],
    *,
    stdout: str,
    stderr: str,
) -> ValidationError:
    diagnostic_output = _PYTEST_SUMMARY_DURATION.sub(
        r"\g<prefix><duration>\g<suffix>\g<trailing>",
        (stderr or stdout).strip(),
    )
    return ValidationError(
        code=ErrorCode.INTERNAL_ERROR,
        message=f"Artifact coverage validate command failed: {' '.join(command)}",
        suggestion=_bounded_diagnostic_suggestion(diagnostic_output),
    )


def _bounded_diagnostic_suggestion(output: str) -> str | None:
    suggestion_limit = 500
    if len(output) <= suggestion_limit:
        return output or None

    truncation_marker = "...<truncated>..."
    pathological_line_limit = 200
    compacted_lines: list[str] = []
    for line in output.splitlines(keepends=True):
        raw_content = line.rstrip("\r\n")
        line_ending = line[len(raw_content) :]
        content = raw_content
        if len(content) > suggestion_limit:
            retained = pathological_line_limit - len(truncation_marker)
            prefix_length = (retained * 7) // 10
            suffix_length = retained - prefix_length
            content = (
                content[:prefix_length] + truncation_marker + content[-suffix_length:]
            )
        compacted_lines.append(content + line_ending)

    tail_start, tail = _whole_line_tail(compacted_lines, suggestion_limit)
    if tail_start == 0:
        return tail or None

    separator = "...<diagnostic truncated>...\n"
    context_line = _actionable_diagnostic_line(compacted_lines)
    if context_line is None:
        _, bounded_tail = _whole_line_tail(
            compacted_lines,
            suggestion_limit - len(separator),
        )
        if not bounded_tail:
            return tail or None
        return (separator + bounded_tail) or None

    if context_line in tail:
        return tail or None

    minimum_tail_budget = 320
    maximum_context_size = suggestion_limit - len(separator) - minimum_tail_budget
    if len(context_line) > maximum_context_size:
        return tail or None

    remaining = suggestion_limit - len(context_line) - len(separator)
    _, bounded_tail = _whole_line_tail(compacted_lines, remaining)
    if not bounded_tail:
        return tail or None
    return (context_line + separator + bounded_tail) or None


def _whole_line_tail(lines: list[str], limit: int) -> tuple[int, str]:
    start = len(lines)
    size = 0
    for index in range(len(lines) - 1, -1, -1):
        line_size = len(lines[index])
        if size + line_size > limit:
            break
        start = index
        size += line_size
    return start, "".join(lines[start:])


def _actionable_diagnostic_line(lines: list[str]) -> str | None:
    for prefixes in (('"message":',), ('"suggestion":',)):
        for line in reversed(lines):
            if line.lstrip().startswith(prefixes):
                return line
    for line in reversed(lines):
        content = re.sub(r"^E[ \t]+", "", line.lstrip())
        if re.match(r"^[A-Za-z_][\w.]*?(?:Error|Exception):", content):
            return line
    for prefixes in (("> ",), ("E ",), ("FAILED ", "ERROR ")):
        for line in reversed(lines):
            if line.lstrip().startswith(prefixes):
                return line
    return None


def _merge_execution_data(
    destination: dict[str, RuntimeFileExecution],
    source: Mapping[str, RuntimeFileExecution],
) -> None:
    # The single-manifest runner appends line coverage across commands while
    # each command overwrites calls.json. Preserve that behavior so one-line
    # artifacts receive the same result from the batch and legacy paths.
    for file_path, execution in tuple(destination.items()):
        destination[file_path] = RuntimeFileExecution(
            executed_lines=execution.executed_lines,
            called_qualnames=frozenset(),
        )
    for file_path, execution in source.items():
        existing = destination.get(file_path)
        if existing is None:
            destination[file_path] = RuntimeFileExecution(
                executed_lines=frozenset(execution.executed_lines),
                called_qualnames=frozenset(execution.called_qualnames),
            )
            continue
        destination[file_path] = RuntimeFileExecution(
            executed_lines=existing.executed_lines | execution.executed_lines,
            called_qualnames=(existing.called_qualnames | execution.called_qualnames),
        )


def _coverage_targets(manifest: Manifest, root: Path) -> list[tuple[str, ArtifactSpec]]:
    targets: list[tuple[str, ArtifactSpec]] = []
    for file_spec in manifest.all_file_specs:
        if not file_spec.path.endswith(".py"):
            continue
        if not (root / file_spec.path).exists():
            continue
        for artifact in file_spec.artifacts:
            if artifact.kind in (
                ArtifactKind.CLASS,
                ArtifactKind.FUNCTION,
                ArtifactKind.METHOD,
            ):
                targets.append((file_spec.path, artifact))
    return targets


def _pytest_args(command: tuple[str, ...]) -> tuple[str, ...] | None:
    parts = list(command)
    if len(parts) >= 2 and parts[:2] == ["uv", "run"]:
        parts = parts[2:]
    if not parts:
        return None
    executable = Path(parts[0]).name
    if executable in {"pytest", "py.test"}:
        return tuple(parts[1:])
    if (
        executable.startswith("python")
        and len(parts) >= 3
        and parts[1:3] == ["-m", "pytest"]
    ):
        return tuple(parts[3:])
    return None


def _evaluate_targets(
    root: Path,
    targets: list[tuple[str, ArtifactSpec]],
    execution_data_by_file: Mapping[str, RuntimeFileExecution],
) -> tuple[list[ArtifactCoverageFinding], list[ValidationError]]:
    findings: list[ArtifactCoverageFinding] = []
    errors: list[ValidationError] = []
    ast_cache: dict[str, _ArtifactLineIndex] = {}
    executed_cache: dict[str, RuntimeFileExecution] = {}
    class_method_executed: dict[tuple[str, str], bool] = {}

    for file_path, artifact in targets:
        index = ast_cache.setdefault(file_path, _build_line_index(root / file_path))
        execution_data = executed_cache.setdefault(
            file_path,
            _execution_data_for_file(file_path, execution_data_by_file),
        )
        if artifact.kind == ArtifactKind.METHOD:
            span = index.methods.get((artifact.of or "", artifact.name))
            executed = _span_executed(span, execution_data)
            class_method_executed[(file_path, artifact.of or "")] = (
                class_method_executed.get((file_path, artifact.of or ""), False)
                or executed
            )
        elif artifact.kind == ArtifactKind.FUNCTION:
            span = index.functions.get(artifact.name)
            executed = _span_executed(span, execution_data)
        else:
            executed = False
        findings.append(_finding(file_path, artifact, executed))

    corrected_findings: list[ArtifactCoverageFinding] = []
    for finding in findings:
        if finding.artifact_kind == ArtifactKind.CLASS:
            executed = class_method_executed.get(
                (finding.file_path, finding.artifact_name),
                False,
            )
            finding = ArtifactCoverageFinding(
                artifact_name=finding.artifact_name,
                artifact_kind=finding.artifact_kind,
                parent_class=finding.parent_class,
                file_path=finding.file_path,
                executed=executed,
            )
        corrected_findings.append(finding)
        if not finding.executed:
            errors.append(
                ValidationError(
                    code=ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS,
                    message=(
                        "No body line of declared artifact "
                        f"'{_display_artifact_name(finding)}' was executed by tests"
                    ),
                    location=Location(file=finding.file_path),
                    suggestion=(
                        "Strengthen the behavioral test so it executes the "
                        "declared artifact body."
                    ),
                )
            )

    return corrected_findings, errors


def _finding(
    file_path: str,
    artifact: ArtifactSpec,
    executed: bool,
) -> ArtifactCoverageFinding:
    return ArtifactCoverageFinding(
        artifact_name=artifact.name,
        artifact_kind=artifact.kind.value,
        parent_class=artifact.of,
        file_path=file_path,
        executed=executed,
    )


def _display_artifact_name(finding: ArtifactCoverageFinding) -> str:
    if finding.parent_class:
        return f"{finding.parent_class}.{finding.artifact_name}"
    return finding.artifact_name


@dataclass(frozen=True)
class _ArtifactLineIndex:
    functions: dict[str, "_ArtifactLineSpan"]
    methods: dict[tuple[str, str], "_ArtifactLineSpan"]


@dataclass(frozen=True)
class _ArtifactLineSpan:
    body_lines: set[int]
    qualname: str


def _build_line_index(file_path: Path) -> _ArtifactLineIndex:
    tree = ast.parse(file_path.read_text(), filename=str(file_path))
    visitor = _LineIndexVisitor()
    visitor.visit(tree)
    return _ArtifactLineIndex(
        functions=visitor.functions,
        methods=visitor.methods,
    )


class _LineIndexVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.functions: dict[str, _ArtifactLineSpan] = {}
        self.methods: dict[tuple[str, str], _ArtifactLineSpan] = {}
        self._class_stack: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._class_stack.append(node.name)
        for child in node.body:
            self.visit(child)
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._record_function(node)

    def _record_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualname = ".".join([*self._class_stack, node.name])
        lines = _body_lines(node, qualname=qualname)
        if self._class_stack:
            self.methods[(self._class_stack[-1], node.name)] = lines
        else:
            self.functions[node.name] = lines


def _body_lines(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    qualname: str,
) -> _ArtifactLineSpan:
    statements = list(node.body)
    if (
        statements
        and isinstance(statements[0], ast.Expr)
        and isinstance(statements[0].value, ast.Constant)
        and isinstance(statements[0].value.value, str)
    ):
        statements = statements[1:]
    if not statements:
        statements = list(node.body)
    body_lines: set[int] = set()
    for statement in statements:
        end = getattr(statement, "end_lineno", None) or statement.lineno
        start = max(statement.lineno, node.lineno + 1)
        if start <= end:
            body_lines.update(range(start, end + 1))
    return _ArtifactLineSpan(
        body_lines=body_lines,
        qualname=qualname,
    )


def _span_executed(
    span: _ArtifactLineSpan | None,
    execution_data: RuntimeFileExecution,
) -> bool:
    if span is None:
        return False
    return bool(
        span.body_lines.intersection(execution_data.executed_lines)
        or span.qualname in execution_data.called_qualnames
    )


def _execution_data_for_file(
    file_path: str,
    execution_data_by_file: Mapping[str, RuntimeFileExecution],
) -> RuntimeFileExecution:
    target = Path(file_path)
    target_resolved = target.resolve()
    executed_lines: set[int] = set()
    called_qualnames: set[str] = set()
    for covered_path, execution_data in execution_data_by_file.items():
        covered = Path(covered_path)
        is_match = False
        if covered == target:
            is_match = True
        else:
            try:
                is_match = covered.resolve() == target_resolved
            except OSError:
                pass
        if not is_match and covered.as_posix().endswith(target.as_posix()):
            is_match = True
        if is_match:
            executed_lines.update(execution_data.executed_lines)
            called_qualnames.update(execution_data.called_qualnames)
    return RuntimeFileExecution(
        executed_lines=frozenset(executed_lines),
        called_qualnames=frozenset(called_qualnames),
    )
