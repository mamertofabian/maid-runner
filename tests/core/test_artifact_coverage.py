from __future__ import annotations

from pathlib import Path

from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode


def test_import_only_behavioral_test_reports_unexecuted_artifact(tmp_path: Path):
    from maid_runner.core.artifact_coverage import run_artifact_coverage

    manifest_path = _write_project(
        tmp_path,
        source="""
def target() -> str:
    return "executed"
""",
        test="""
from src.target import target


def test_mentions_target_without_executing_body():
    assert target is not None
""",
        artifacts=[{"kind": "function", "name": "target"}],
    )

    report = run_artifact_coverage(load_manifest(manifest_path), tmp_path)

    assert report.success is False
    assert report.findings[0].artifact_name == "target"
    assert report.findings[0].executed is False
    assert report.errors[0].code == ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS


def test_import_only_one_line_function_reports_unexecuted_artifact(tmp_path: Path):
    from maid_runner.core.artifact_coverage import run_artifact_coverage

    manifest_path = _write_project(
        tmp_path,
        source='def target() -> str: return "executed"\n',
        test="""
from src.target import target


def test_mentions_one_line_target_without_executing_body():
    assert target is not None
""",
        artifacts=[{"kind": "function", "name": "target"}],
    )

    report = run_artifact_coverage(load_manifest(manifest_path), tmp_path)

    assert report.success is False
    assert report.findings[0].executed is False
    assert report.errors[0].code == ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS


def test_test_scoped_import_of_one_line_function_reports_unexecuted_artifact(
    tmp_path: Path,
):
    from maid_runner.core.artifact_coverage import run_artifact_coverage

    manifest_path = _write_project(
        tmp_path,
        source='def target() -> str: return "executed"\n',
        test="""
def test_imports_one_line_target_inside_test_without_executing_body():
    from src.target import target

    assert target is not None
""",
        artifacts=[{"kind": "function", "name": "target"}],
    )

    report = run_artifact_coverage(load_manifest(manifest_path), tmp_path)

    assert report.success is False
    assert report.findings[0].executed is False
    assert report.errors[0].code == ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS


def test_executed_function_artifact_passes(tmp_path: Path):
    from maid_runner.core.artifact_coverage import run_artifact_coverage

    manifest_path = _write_project(
        tmp_path,
        source="""
def target() -> str:
    return "executed"
""",
        test="""
from src.target import target


def test_executes_target_body():
    assert target() == "executed"
""",
        artifacts=[{"kind": "function", "name": "target"}],
    )

    report = run_artifact_coverage(load_manifest(manifest_path), tmp_path)

    assert report.success is True
    assert report.findings[0].executed is True
    assert report.errors == ()


def test_executed_one_line_function_artifact_passes(tmp_path: Path):
    from maid_runner.core.artifact_coverage import run_artifact_coverage

    manifest_path = _write_project(
        tmp_path,
        source='def target() -> str: return "executed"\n',
        test="""
from src.target import target


def test_executes_one_line_target_body():
    assert target() == "executed"
""",
        artifacts=[{"kind": "function", "name": "target"}],
    )

    report = run_artifact_coverage(load_manifest(manifest_path), tmp_path)

    assert report.success is True
    assert report.findings[0].executed is True
    assert report.errors == ()


def test_class_artifact_passes_when_declared_method_body_executes(tmp_path: Path):
    from maid_runner.core.artifact_coverage import run_artifact_coverage

    manifest_path = _write_project(
        tmp_path,
        source="""
class Service:
    def run(self) -> str:
        return "ran"
""",
        test="""
from src.target import Service


def test_executes_declared_method():
    assert Service().run() == "ran"
""",
        artifacts=[
            {"kind": "class", "name": "Service"},
            {"kind": "method", "name": "run", "of": "Service"},
        ],
    )

    report = run_artifact_coverage(load_manifest(manifest_path), tmp_path)

    findings = {finding.artifact_name: finding for finding in report.findings}
    assert report.success is True
    assert findings["Service"].executed is True
    assert findings["run"].parent_class == "Service"
    assert findings["run"].executed is True


def test_one_line_class_artifact_passes_when_declared_method_body_executes(
    tmp_path: Path,
):
    from maid_runner.core.artifact_coverage import run_artifact_coverage

    manifest_path = _write_project(
        tmp_path,
        source="""
class Service:
    def run(self) -> str: return "ran"
""",
        test="""
from src.target import Service


def test_executes_one_line_declared_method():
    assert Service().run() == "ran"
""",
        artifacts=[
            {"kind": "class", "name": "Service"},
            {"kind": "method", "name": "run", "of": "Service"},
        ],
    )

    report = run_artifact_coverage(load_manifest(manifest_path), tmp_path)

    findings = {finding.artifact_name: finding for finding in report.findings}
    assert report.success is True
    assert findings["Service"].executed is True
    assert findings["run"].executed is True


def test_import_only_class_artifact_reports_unexecuted_until_method_runs(
    tmp_path: Path,
):
    from maid_runner.core.artifact_coverage import run_artifact_coverage

    manifest_path = _write_project(
        tmp_path,
        source="""
class Service:
    def run(self) -> str:
        return "ran"
""",
        test="""
from src.target import Service


def test_mentions_service_without_executing_method():
    assert Service is not None
""",
        artifacts=[
            {"kind": "class", "name": "Service"},
            {"kind": "method", "name": "run", "of": "Service"},
        ],
    )

    report = run_artifact_coverage(load_manifest(manifest_path), tmp_path)

    findings = {finding.artifact_name: finding for finding in report.findings}
    assert report.success is False
    assert findings["Service"].executed is False
    assert findings["run"].executed is False
    assert [error.code for error in report.errors] == [
        ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS,
        ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS,
    ]


def test_import_only_one_line_class_method_reports_unexecuted_until_method_runs(
    tmp_path: Path,
):
    from maid_runner.core.artifact_coverage import run_artifact_coverage

    manifest_path = _write_project(
        tmp_path,
        source="""
class Service:
    def run(self) -> str: return "ran"
""",
        test="""
from src.target import Service


def test_mentions_one_line_method_without_executing_body():
    assert Service is not None
""",
        artifacts=[
            {"kind": "class", "name": "Service"},
            {"kind": "method", "name": "run", "of": "Service"},
        ],
    )

    report = run_artifact_coverage(load_manifest(manifest_path), tmp_path)

    findings = {finding.artifact_name: finding for finding in report.findings}
    assert report.success is False
    assert findings["Service"].executed is False
    assert findings["run"].executed is False
    assert [error.code for error in report.errors] == [
        ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS,
        ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS,
    ]


def test_test_scoped_import_of_one_line_class_reports_unexecuted_until_method_runs(
    tmp_path: Path,
):
    from maid_runner.core.artifact_coverage import run_artifact_coverage

    manifest_path = _write_project(
        tmp_path,
        source="""
class Service:
    def run(self) -> str: return "ran"
""",
        test="""
def test_imports_one_line_method_inside_test_without_executing_body():
    from src.target import Service

    assert Service is not None
""",
        artifacts=[
            {"kind": "class", "name": "Service"},
            {"kind": "method", "name": "run", "of": "Service"},
        ],
    )

    report = run_artifact_coverage(load_manifest(manifest_path), tmp_path)

    findings = {finding.artifact_name: finding for finding in report.findings}
    assert report.success is False
    assert findings["Service"].executed is False
    assert findings["run"].executed is False
    assert [error.code for error in report.errors] == [
        ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS,
        ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS,
    ]


def test_attribute_artifacts_are_excluded_from_gate(tmp_path: Path):
    from maid_runner.core.artifact_coverage import run_artifact_coverage

    manifest_path = _write_project(
        tmp_path,
        source='VALUE = "not executable"\n',
        test="""
from src.target import VALUE


def test_reads_attribute():
    assert VALUE == "not executable"
""",
        artifacts=[{"kind": "attribute", "name": "VALUE", "type": "str"}],
    )

    report = run_artifact_coverage(load_manifest(manifest_path), tmp_path)

    assert report.success is True
    assert report.findings == ()
    assert report.errors == ()


def test_missing_quality_extra_fails_closed(monkeypatch, tmp_path: Path):
    from maid_runner.core import artifact_coverage

    manifest_path = _write_project(
        tmp_path,
        source="""
def target() -> str:
    return "executed"
""",
        test="""
from src.target import target


def test_executes_target_body():
    assert target() == "executed"
""",
        artifacts=[{"kind": "function", "name": "target"}],
    )
    monkeypatch.setattr(artifact_coverage, "coverage_is_available", lambda: False)

    report = artifact_coverage.run_artifact_coverage(
        load_manifest(manifest_path),
        tmp_path,
    )

    assert report.success is False
    assert report.errors[0].code == ErrorCode.VALIDATOR_NOT_AVAILABLE
    assert "maid-runner[quality]" in report.errors[0].message


def test_report_to_dict_includes_per_artifact_findings(tmp_path: Path):
    from maid_runner.core.artifact_coverage import (
        ArtifactCoverageFinding,
        ArtifactCoverageReport,
        coverage_is_available,
        run_artifact_coverage,
    )

    manifest_path = _write_project(
        tmp_path,
        source="""
def target() -> str:
    return "executed"
""",
        test="""
from src.target import target


def test_executes_target_body():
    assert target() == "executed"
""",
        artifacts=[{"kind": "function", "name": "target"}],
    )

    payload = run_artifact_coverage(load_manifest(manifest_path), tmp_path).to_dict()
    explicit_finding = ArtifactCoverageFinding(
        artifact_name="target",
        artifact_kind="function",
        parent_class=None,
        file_path="src/target.py",
        executed=True,
    )
    explicit_report = ArtifactCoverageReport(findings=(explicit_finding,), errors=())

    assert coverage_is_available() is True
    assert explicit_report.success is True
    assert explicit_finding.to_dict()["artifact_name"] == "target"
    assert explicit_report.findings[0].artifact_kind == "function"
    assert explicit_report.findings[0].file_path == "src/target.py"
    assert payload["success"] is True
    assert payload["findings"] == [
        {
            "artifact_name": "target",
            "artifact_kind": "function",
            "parent_class": None,
            "file_path": "src/target.py",
            "executed": True,
        }
    ]
    assert payload["errors"] == []


def _write_project(
    root: Path,
    *,
    source: str,
    test: str,
    artifacts: list[dict],
) -> Path:
    src_dir = root / "src"
    tests_dir = root / "tests"
    manifests_dir = root / "manifests"
    src_dir.mkdir()
    tests_dir.mkdir()
    manifests_dir.mkdir()
    (src_dir / "__init__.py").write_text("")
    (src_dir / "target.py").write_text(source.lstrip())
    (tests_dir / "test_target.py").write_text(test.lstrip())
    manifest_path = manifests_dir / "target.manifest.yaml"
    manifest_path.write_text(
        _manifest_text(artifacts),
    )
    return manifest_path


def _manifest_text(artifacts: list[dict]) -> str:
    artifact_lines = []
    for artifact in artifacts:
        artifact_lines.append(f"        - kind: {artifact['kind']}")
        artifact_lines.append(f"          name: {artifact['name']}")
        if "of" in artifact:
            artifact_lines.append(f"          of: {artifact['of']}")
        if "type" in artifact:
            artifact_lines.append(f"          type: {artifact['type']}")
    rendered_artifacts = "\n".join(artifact_lines)
    return f"""schema: "2"
goal: "Cover target"
type: feature
created: "2026-06-10T00:00:00Z"
files:
  edit:
    - path: src/target.py
      artifacts:
{rendered_artifacts}
  read:
    - tests/test_target.py
validate:
  - python -m pytest -q tests/test_target.py
"""
