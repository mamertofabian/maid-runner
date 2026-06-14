from __future__ import annotations

import json
from pathlib import Path

import yaml

from maid_runner.core.failure_packet import (
    build_failure_packet,
    clear_failure_packet,
    write_failure_packet,
)
from maid_runner.core.result import (
    BatchTestResult,
    BatchValidationResult,
    ErrorCode,
    FileTrackingEntry,
    FileTrackingReport,
    FileTrackingStatus,
    Location,
    TestRunResult,
    ValidationError,
    ValidationResult,
    VerificationResult,
    VerificationStageResult,
)
from maid_runner.core.types import TestStream, ValidationMode


def _write_manifest(root: Path, slug: str, *, function: str = "gate") -> Path:
    manifest_dir = root / "manifests"
    manifest_dir.mkdir(exist_ok=True)
    path = manifest_dir / f"{slug}.manifest.yaml"
    path.write_text(
        yaml.dump(
            {
                "schema": "2",
                "goal": f"Add {function}",
                "type": "feature",
                "files": {
                    "create": [
                        {
                            "path": f"src/{function}.py",
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": function,
                                    "returns": "str",
                                }
                            ],
                        }
                    ],
                    "read": [f"tests/test_{function}.py"],
                },
                "validate": [f"python -m pytest tests/test_{function}.py -q"],
            }
        )
    )
    return path


def _validation(manifest_path: Path, code: ErrorCode) -> ValidationResult:
    return ValidationResult(
        success=False,
        manifest_slug=manifest_path.stem.replace(".manifest", ""),
        manifest_path=str(manifest_path),
        mode=ValidationMode.IMPLEMENTATION,
        errors=[
            ValidationError(
                code=code,
                message="Artifact 'gate' not defined",
                location=Location(file="src/gate.py", line=3),
                suggestion="Implement gate.",
            )
        ],
    )


def test_build_failure_packet_uses_exact_top_level_keys_and_next_action(tmp_path):
    manifest_path = _write_manifest(tmp_path, "add-gate")
    validation = _validation(manifest_path, ErrorCode.ARTIFACT_NOT_DEFINED)

    packet = build_failure_packet(
        command=["maid", "validate", str(manifest_path)],
        exit_code=1,
        project_root=tmp_path,
        validation=validation,
    )

    assert set(packet) == {
        "packet_version",
        "command",
        "exit_code",
        "project_root",
        "manifest",
        "diagnostics",
        "test_output",
        "environment",
    }
    assert packet["manifest"][0]["goal"] == "Add gate"
    assert packet["manifest"][0]["declared_files"][0]["artifacts"] == ["gate"]
    assert packet["diagnostics"][0]["code"] == "E300"
    assert packet["diagnostics"][0]["file"] == "src/gate.py"
    assert packet["diagnostics"][0]["line"] == 3
    assert packet["diagnostics"][0]["suggestion"] == "Implement gate."
    assert packet["diagnostics"][0]["next_action"]["kind"] == "edit-implementation"
    assert packet["diagnostics"][0]["next_action"]["target"] == "src/gate.py"


def test_build_failure_packet_emits_null_next_action_for_uncovered_code(tmp_path):
    manifest_path = _write_manifest(tmp_path, "add-gate")
    validation = _validation(manifest_path, ErrorCode.FILE_NOT_FOUND)

    packet = build_failure_packet(
        command=["maid", "validate", str(manifest_path)],
        exit_code=1,
        project_root=tmp_path,
        validation=validation,
    )

    assert packet["diagnostics"][0]["code"] == "E001"
    assert packet["diagnostics"][0]["next_action"] is None


def test_build_failure_packet_truncates_test_output_to_final_50_lines(tmp_path):
    manifest_path = _write_manifest(tmp_path, "add-gate")
    validation = _validation(manifest_path, ErrorCode.ARTIFACT_NOT_DEFINED)
    test_result = TestRunResult(
        manifest_slug="add-gate",
        command=("python", "-m", "pytest", "tests/test_gate.py", "-q"),
        exit_code=1,
        stdout="\n".join(f"stdout-{index}" for index in range(60)),
        stderr="\n".join(f"stderr-{index}" for index in range(10)),
        duration_ms=1.0,
        stream=TestStream.IMPLEMENTATION,
    )
    tests = BatchTestResult(
        results=[test_result],
        total=1,
        passed=0,
        failed=1,
    )

    packet = build_failure_packet(
        command=["maid", "validate", "--run-tests"],
        exit_code=1,
        project_root=tmp_path,
        validation=validation,
        test_results=tests,
    )

    tail = packet["test_output"][0]["output_tail"].splitlines()
    assert len(tail) == 50
    assert tail[0] == "stdout-20"
    assert tail[-1] == "stderr-9"


def test_build_failure_packet_includes_test_chain_errors(tmp_path):
    manifest_path = _write_manifest(tmp_path, "add-gate")
    validation = ValidationResult(
        success=True,
        manifest_slug="add-gate",
        manifest_path=str(manifest_path),
        mode=ValidationMode.IMPLEMENTATION,
    )
    tests = BatchTestResult(
        results=[],
        total=0,
        passed=0,
        failed=0,
        chain_errors=[
            ValidationError(
                code=ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS,
                message="Validate command `echo ok` does not run tests/test_gate.py",
                location=Location(file=str(manifest_path)),
            )
        ],
    )

    packet = build_failure_packet(
        command=["maid", "validate", "--run-tests"],
        exit_code=1,
        project_root=tmp_path,
        validation=validation,
        test_results=tests,
    )

    assert packet["manifest"][0]["path"] == "manifests/add-gate.manifest.yaml"
    assert packet["diagnostics"][0]["code"] == "E230"
    assert packet["diagnostics"][0]["next_action"]["target"] == (
        f"maid plan revise {manifest_path}"
    )


def test_build_failure_packet_includes_verify_coherence_and_file_tracking_failures(
    tmp_path,
):
    from maid_runner.coherence.result import (
        CoherenceIssue,
        CoherenceResult,
        IssueSeverity,
        IssueType,
    )

    _write_manifest(tmp_path, "add-gate")
    result = VerificationResult(
        stages=(
            VerificationStageResult(
                name="coherence",
                success=False,
                _coherence=CoherenceResult(
                    issues=[
                        CoherenceIssue(
                            issue_type=IssueType.DUPLICATE,
                            severity=IssueSeverity.ERROR,
                            message="Duplicate artifact gate",
                            file="src/gate.py",
                            manifests=("add-gate",),
                        )
                    ]
                ),
            ),
            VerificationStageResult(
                name="file_tracking",
                success=False,
                _file_tracking=FileTrackingReport(
                    entries=(
                        FileTrackingEntry(
                            path="src/orphan.py",
                            status=FileTrackingStatus.UNDECLARED,
                        ),
                    )
                ),
            ),
        )
    )

    packet = build_failure_packet(
        command=["maid", "verify", "--packet"],
        exit_code=1,
        project_root=tmp_path,
        validation=result,
    )

    assert packet["manifest"][0]["path"] == "manifests/add-gate.manifest.yaml"
    diagnostics_by_code = {item["code"]: item for item in packet["diagnostics"]}
    assert set(diagnostics_by_code) == {"E400", "E114"}
    assert diagnostics_by_code["E400"]["message"] == "Duplicate artifact gate"
    assert diagnostics_by_code["E114"]["file"] == "src/orphan.py"


def test_build_failure_packet_orders_multi_manifest_failures_deterministically(
    tmp_path,
):
    first = _write_manifest(tmp_path, "b-task", function="bravo")
    second = _write_manifest(tmp_path, "a-task", function="alpha")
    batch = BatchValidationResult(
        results=[
            _validation(first, ErrorCode.ARTIFACT_NOT_DEFINED),
            _validation(second, ErrorCode.FILE_NOT_FOUND),
        ],
        total_manifests=2,
        passed=0,
        failed=2,
        skipped=0,
    )

    packet = build_failure_packet(
        command=["maid", "validate"],
        exit_code=1,
        project_root=tmp_path,
        validation=batch,
    )

    assert [entry["path"] for entry in packet["manifest"]] == [
        "manifests/a-task.manifest.yaml",
        "manifests/b-task.manifest.yaml",
    ]


def test_build_failure_packet_uses_each_diagnostics_manifest_in_next_action(
    tmp_path,
):
    first = _write_manifest(tmp_path, "b-task", function="bravo")
    second = _write_manifest(tmp_path, "a-task", function="alpha")
    batch = BatchValidationResult(
        results=[
            ValidationResult(
                success=False,
                manifest_slug="b-task",
                manifest_path=str(first),
                mode=ValidationMode.BEHAVIORAL,
                errors=[
                    ValidationError(
                        code=ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS,
                        message=(
                            "Validate command `python -m pytest tests/test_bravo.py "
                            "-q` does not run tests/test_bravo.py"
                        ),
                        location=Location(file="tests/test_bravo.py"),
                    )
                ],
            ),
            ValidationResult(
                success=False,
                manifest_slug="a-task",
                manifest_path=str(second),
                mode=ValidationMode.BEHAVIORAL,
                errors=[
                    ValidationError(
                        code=ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS,
                        message=(
                            "Validate command `python -m pytest tests/test_alpha.py "
                            "-q` does not run tests/test_alpha.py"
                        ),
                        location=Location(file="tests/test_alpha.py"),
                    )
                ],
            ),
        ],
        total_manifests=2,
        passed=0,
        failed=2,
        skipped=0,
    )

    packet = build_failure_packet(
        command=["maid", "validate"],
        exit_code=1,
        project_root=tmp_path,
        validation=batch,
    )

    targets = [item["next_action"]["target"] for item in packet["diagnostics"]]
    assert targets == [
        f"maid plan revise {second}",
        f"maid plan revise {first}",
    ]


def test_build_failure_packet_keeps_manifest_path_when_manifest_cannot_load(tmp_path):
    manifest_path = tmp_path / "manifests" / "broken.manifest.yaml"
    manifest_path.parent.mkdir()
    manifest_path.write_text("schema: '2'\ngoal: [broken\n")
    validation = ValidationResult(
        success=False,
        manifest_slug="broken",
        manifest_path=str(manifest_path),
        mode=ValidationMode.SCHEMA,
        errors=[
            ValidationError(
                code=ErrorCode.MANIFEST_PARSE_ERROR,
                message="Manifest cannot be parsed",
                location=Location(file=str(manifest_path)),
            )
        ],
    )

    packet = build_failure_packet(
        command=["maid", "validate", str(manifest_path)],
        exit_code=1,
        project_root=tmp_path,
        validation=validation,
    )

    assert packet["manifest"] == [
        {
            "path": "manifests/broken.manifest.yaml",
            "goal": None,
            "type": None,
            "declared_files": [],
            "validate": [],
        }
    ]


def test_write_failure_packet_is_deterministic_and_clear_failure_packet_removes_stale_file(
    tmp_path,
):
    manifest_path = _write_manifest(tmp_path, "add-gate")
    validation = _validation(manifest_path, ErrorCode.ARTIFACT_NOT_DEFINED)
    packet = build_failure_packet(
        command=["maid", "validate"],
        exit_code=1,
        project_root=tmp_path,
        validation=validation,
    )
    packet_path = tmp_path / ".maid" / "last-failure-packet.json"

    write_failure_packet(packet, packet_path)
    first_bytes = packet_path.read_bytes()
    write_failure_packet(packet, packet_path)
    second_bytes = packet_path.read_bytes()

    assert first_bytes == second_bytes
    assert json.loads(first_bytes)["packet_version"] == 1
    assert clear_failure_packet(packet_path) is True
    assert packet_path.exists() is False
    assert clear_failure_packet(packet_path) is False
