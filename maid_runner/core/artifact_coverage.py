"""Runtime execution coverage checks for declared Python artifacts."""

from __future__ import annotations

import ast
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from maid_runner.core._test_command_execution import _test_command_environment
from maid_runner.core.result import ErrorCode, Location, ValidationError
from maid_runner.core.types import ArtifactKind, ArtifactSpec, Manifest


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


def coverage_is_available() -> bool:
    try:
        import coverage  # noqa: F401
    except ImportError:
        return False
    return True


def run_artifact_coverage(
    manifest: Manifest,
    project_root: Path,
) -> ArtifactCoverageReport:
    if not coverage_is_available():
        return ArtifactCoverageReport(
            findings=(),
            errors=(
                ValidationError(
                    code=ErrorCode.VALIDATOR_NOT_AVAILABLE,
                    message=(
                        "Artifact coverage requires coverage.py from the quality "
                        "extra; install maid-runner[quality]."
                    ),
                ),
            ),
        )

    root = Path(project_root)
    coverage_targets = _coverage_targets(manifest, root)
    if not coverage_targets:
        return ArtifactCoverageReport(findings=(), errors=())

    with tempfile.TemporaryDirectory(prefix="maid-artifact-coverage-") as tmp:
        tmp_path = Path(tmp)
        data_file = tmp_path / ".coverage"
        call_file = tmp_path / "calls.json"
        command_errors = _run_coverage_commands(
            manifest,
            root,
            data_file,
            call_file,
        )
        coverage_json = tmp_path / "coverage.json"
        report_errors = _write_coverage_json(data_file, coverage_json)
        execution_data = (
            _load_execution_data(coverage_json, call_file) if not report_errors else {}
        )

    findings, execution_errors = _evaluate_targets(
        root, coverage_targets, execution_data
    )
    return ArtifactCoverageReport(
        findings=tuple(findings),
        errors=tuple(command_errors + report_errors + execution_errors),
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


def _run_coverage_commands(
    manifest: Manifest,
    root: Path,
    data_file: Path,
    call_file: Path,
) -> list[ValidationError]:
    import subprocess

    errors: list[ValidationError] = []
    env = _test_command_environment()
    runner = _coverage_runner_script(data_file.parent)
    target_file = _coverage_target_file(manifest, root, data_file.parent)
    for command in manifest.validate_commands:
        pytest_args = _pytest_args(command)
        if pytest_args is None:
            continue
        proc = subprocess.run(
            (
                sys.executable,
                "-m",
                "coverage",
                "run",
                "--append",
                "--data-file",
                str(data_file),
                str(runner),
                str(call_file),
                str(target_file),
                *pytest_args,
            ),
            cwd=root,
            capture_output=True,
            text=True,
            env=env,
            timeout=300,
        )
        if proc.returncode != 0:
            errors.append(
                ValidationError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=(
                        "Artifact coverage validate command failed: "
                        f"{' '.join(command)}"
                    ),
                    suggestion=(proc.stderr or proc.stdout).strip()[-500:] or None,
                )
            )
    return errors


def _coverage_target_file(manifest: Manifest, root: Path, tmp_path: Path) -> Path:
    target_file = tmp_path / "target_files.json"
    target_file.write_text(
        json.dumps(
            sorted(
                str((root / file_path).resolve())
                for file_path, _artifact in _coverage_targets(manifest, root)
            )
        )
    )
    return target_file


def _coverage_runner_script(tmp_path: Path) -> Path:
    runner = tmp_path / "artifact_coverage_runner.py"
    runner.write_text(
        """
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

call_output = Path(sys.argv[1])
target_files = set(json.loads(Path(sys.argv[2]).read_text()))
pytest_args = sys.argv[3:]
calls: set[tuple[str, str, str, int]] = set()
exit_code = 1


def profile_calls(frame, event, arg):
    if event == "call":
        code = frame.f_code
        filename = code.co_filename
        if filename not in target_files:
            return profile_calls
        calls.add(
            (
                filename,
                code.co_name,
                getattr(code, "co_qualname", code.co_name),
                code.co_firstlineno,
            )
        )
    return profile_calls


sys.setprofile(profile_calls)
threading.setprofile(profile_calls)

try:
    sys.path.insert(0, str(Path.cwd()))
    import pytest

    exit_code = pytest.main(pytest_args)
finally:
    sys.setprofile(None)
    threading.setprofile(None)
    payload = [
        {"file": file, "name": name, "qualname": qualname, "firstlineno": firstlineno}
        for file, name, qualname, firstlineno in sorted(calls)
    ]
    call_output.write_text(json.dumps(payload))

raise SystemExit(exit_code)
""".lstrip()
    )
    return runner


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


def _write_coverage_json(data_file: Path, output_file: Path) -> list[ValidationError]:
    try:
        import coverage

        cov = coverage.Coverage(data_file=str(data_file))
        cov.load()
        cov.json_report(outfile=str(output_file))
    except Exception as exc:
        return [
            ValidationError(
                code=ErrorCode.INTERNAL_ERROR,
                message=f"Artifact coverage report could not be generated: {exc}",
            )
        ]
    return []


@dataclass(frozen=True)
class _CoverageFileExecution:
    executed_lines: set[int]
    called_qualnames: set[str]


def _load_execution_data(
    report_path: Path,
    call_path: Path,
) -> dict[str, _CoverageFileExecution]:
    data = json.loads(report_path.read_text())
    result: dict[str, _CoverageFileExecution] = {}
    for file_path, file_data in data.get("files", {}).items():
        result[file_path] = _CoverageFileExecution(
            executed_lines=set(file_data.get("executed_lines", [])),
            called_qualnames=set(),
        )
    if call_path.exists():
        for call in json.loads(call_path.read_text() or "[]"):
            file_path = call["file"]
            existing = result.get(file_path)
            if existing is None:
                existing = _CoverageFileExecution(
                    executed_lines=set(),
                    called_qualnames=set(),
                )
            existing.called_qualnames.add(call["qualname"])
            result[file_path] = existing
    return result


def _evaluate_targets(
    root: Path,
    targets: list[tuple[str, ArtifactSpec]],
    execution_data_by_file: dict[str, _CoverageFileExecution],
) -> tuple[list[ArtifactCoverageFinding], list[ValidationError]]:
    findings: list[ArtifactCoverageFinding] = []
    errors: list[ValidationError] = []
    ast_cache: dict[str, _ArtifactLineIndex] = {}
    executed_cache: dict[str, _CoverageFileExecution] = {}
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
    execution_data: _CoverageFileExecution,
) -> bool:
    if span is None:
        return False
    return bool(
        span.body_lines.intersection(execution_data.executed_lines)
        or span.qualname in execution_data.called_qualnames
    )


def _execution_data_for_file(
    file_path: str,
    execution_data_by_file: dict[str, _CoverageFileExecution],
) -> _CoverageFileExecution:
    target = Path(file_path)
    target_resolved = target.resolve()
    matched = _CoverageFileExecution(executed_lines=set(), called_qualnames=set())
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
            matched.executed_lines.update(execution_data.executed_lines)
            matched.called_qualnames.update(execution_data.called_qualnames)
    return matched
