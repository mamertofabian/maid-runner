from maid_runner.core.types import ArtifactKind
from maid_runner.validators._python_behavioral_references import (
    _BehavioralReferenceRecorder,
)
from maid_runner.validators.python import PythonValidator


def test_behavioral_reference_recorder_deduplicates_references_and_test_functions():
    artifacts = []
    seen = set()
    seen_test_funcs = set()
    recorder = _BehavioralReferenceRecorder(
        artifacts=artifacts,
        seen=seen,
        seen_test_funcs=seen_test_funcs,
    )

    recorder.add_test_function("test_example", 10)
    recorder.add_test_function("test_example", 20)
    recorder.add_reference(
        "Thing",
        import_source="pkg.alpha",
        reference_context="access",
    )
    recorder.add_reference(
        "Thing",
        import_source="pkg.alpha",
        reference_context="access",
    )
    recorder.add_reference(
        "Thing",
        import_source="pkg.beta",
        reference_context="access",
    )

    assert [
        artifact.name
        for artifact in artifacts
        if artifact.kind == ArtifactKind.TEST_FUNCTION
    ] == ["test_example"]
    thing_references = [
        artifact
        for artifact in artifacts
        if artifact.kind == ArtifactKind.FUNCTION and artifact.name == "Thing"
    ]
    assert [artifact.import_source for artifact in thing_references] == [
        "pkg.alpha",
        "pkg.beta",
    ]


def test_python_behavioral_reference_deduplication_is_unchanged():
    source = """\
from pkg.alpha import Thing

def test_reference_deduplication():
    Thing()
    Thing()
"""

    result = PythonValidator().collect_behavioral_artifacts(
        source,
        "tests/test_references.py",
    )

    test_functions = [
        artifact
        for artifact in result.artifacts
        if artifact.kind == ArtifactKind.TEST_FUNCTION
        and artifact.name == "test_reference_deduplication"
    ]
    call_references = [
        artifact
        for artifact in result.artifacts
        if artifact.kind == ArtifactKind.FUNCTION
        and artifact.name == "Thing"
        and artifact.reference_context == "call"
    ]

    assert len(test_functions) == 1
    assert len(call_references) == 1
    assert call_references[0].import_source == "pkg.alpha"
