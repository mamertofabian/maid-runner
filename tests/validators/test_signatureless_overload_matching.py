"""Regression coverage for an unsigned declaration with C#-style overloads."""

from maid_runner.core._implementation_validation import (
    _check_stub_artifacts,
    compare_artifacts,
)
from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ArgSpec, ArtifactKind, ArtifactSpec
from maid_runner.validators.base import FoundArtifact


def test_unsigned_declaration_accepts_earlier_matching_overload() -> None:
    expected = ArtifactSpec(
        kind=ArtifactKind.METHOD,
        name="AddAssignment",
        of="ScheduleManagerService",
        args=(ArgSpec(name="congregationId", type="int"),),
        returns="Task",
    )
    found = [
        FoundArtifact(
            kind=ArtifactKind.METHOD,
            name="AddAssignment",
            of="ScheduleManagerService",
            args=(ArgSpec(name="congregationId", type="int"),),
            returns="Task",
            signature="AddAssignment(System.Int32)",
            line=104,
        ),
        FoundArtifact(
            kind=ArtifactKind.METHOD,
            name="AddAssignment",
            of="ScheduleManagerService",
            args=(ArgSpec(name="shift", type="ShiftDto"),),
            returns="Task",
            signature="AddAssignment(ShiftDto)",
            line=321,
        ),
    ]

    assert compare_artifacts([expected], found, "ScheduleManagerService.cs", True) == []


def test_unsigned_declaration_rejects_all_mismatching_overloads() -> None:
    expected = ArtifactSpec(
        kind=ArtifactKind.METHOD,
        name="AddAssignment",
        of="ScheduleManagerService",
        args=(ArgSpec(name="congregationId", type="int"),),
    )
    found = [
        FoundArtifact(
            kind=ArtifactKind.METHOD,
            name="AddAssignment",
            of="ScheduleManagerService",
            args=(ArgSpec(name="tenantId", type="int"),),
            signature="AddAssignment(System.Int32)",
            line=104,
        ),
        FoundArtifact(
            kind=ArtifactKind.METHOD,
            name="AddAssignment",
            of="ScheduleManagerService",
            args=(ArgSpec(name="shift", type="ShiftDto"),),
            signature="AddAssignment(ShiftDto)",
            line=321,
        ),
    ]

    errors = compare_artifacts([expected], found, "ScheduleManagerService.cs", False)

    assert [error.code for error in errors] == [ErrorCode.SIGNATURE_MISMATCH]
    assert errors[0].location is not None
    assert errors[0].location.line == 321


def test_signed_declaration_still_requires_exact_overload() -> None:
    expected = ArtifactSpec(
        kind=ArtifactKind.METHOD,
        name="AddAssignment",
        of="ScheduleManagerService",
        signature="AddAssignment(System.Int32)",
        args=(ArgSpec(name="congregationId", type="int"),),
    )
    found = [
        FoundArtifact(
            kind=ArtifactKind.METHOD,
            name="AddAssignment",
            of="ScheduleManagerService",
            signature="AddAssignment(System.Boolean)",
            args=(ArgSpec(name="congregationId", type="int"),),
        )
    ]

    errors = compare_artifacts([expected], found, "ScheduleManagerService.cs", False)

    assert [error.code for error in errors] == [ErrorCode.ARTIFACT_NOT_DEFINED]


def test_stub_check_uses_matching_unsigned_overload() -> None:
    expected = ArtifactSpec(
        kind=ArtifactKind.METHOD,
        name="AddAssignment",
        of="ScheduleManagerService",
        args=(ArgSpec(name="congregationId", type="int"),),
    )
    found = [
        FoundArtifact(
            kind=ArtifactKind.METHOD,
            name="AddAssignment",
            of="ScheduleManagerService",
            args=(ArgSpec(name="congregationId", type="int"),),
            signature="AddAssignment(System.Int32)",
            is_stub=True,
            line=104,
        ),
        FoundArtifact(
            kind=ArtifactKind.METHOD,
            name="AddAssignment",
            of="ScheduleManagerService",
            args=(ArgSpec(name="shift", type="ShiftDto"),),
            signature="AddAssignment(ShiftDto)",
            line=321,
        ),
    ]

    errors = _check_stub_artifacts([expected], found, "ScheduleManagerService.cs")

    assert [error.code for error in errors] == [ErrorCode.STUB_FUNCTION_DETECTED]
    assert errors[0].location is not None
    assert errors[0].location.line == 104


def test_unsigned_same_name_definitions_keep_last_runtime_definition() -> None:
    expected = ArtifactSpec(
        kind=ArtifactKind.FUNCTION,
        name="convert",
        args=(ArgSpec(name="value", type="int"),),
        returns="int",
    )
    found = [
        FoundArtifact(
            kind=ArtifactKind.FUNCTION,
            name="convert",
            args=(ArgSpec(name="value", type="int"),),
            returns="int",
            line=1,
        ),
        FoundArtifact(
            kind=ArtifactKind.FUNCTION,
            name="convert",
            args=(ArgSpec(name="value", type="str"),),
            returns="str",
            line=4,
        ),
    ]

    errors = compare_artifacts([expected], found, "convert.py", False)

    assert [error.code for error in errors] == [
        ErrorCode.TYPE_MISMATCH,
        ErrorCode.TYPE_MISMATCH,
    ]
    assert all(
        error.location is not None and error.location.line == 4 for error in errors
    )
