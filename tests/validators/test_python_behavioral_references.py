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


def test_behavioral_reference_recorder_records_keyword_references():
    import ast

    artifacts = []
    recorder = _BehavioralReferenceRecorder(
        artifacts=artifacts,
        seen=set(),
        seen_test_funcs=set(),
    )
    call = ast.parse("Factory(alpha=1, **options, beta=2)").body[0].value

    recorder.add_keyword_references(
        call.keywords,
        import_source="pkg.models",
        owner="Factory",
    )

    keyword_references = [
        artifact
        for artifact in artifacts
        if artifact.kind == ArtifactKind.FUNCTION
        and artifact.reference_context == "keyword"
    ]
    assert [artifact.name for artifact in keyword_references] == ["alpha", "beta"]
    assert {artifact.import_source for artifact in keyword_references} == {"pkg.models"}
    assert {artifact.of for artifact in keyword_references} == {"Factory"}


def test_python_behavioral_keyword_reference_owner_is_unchanged():
    source = """\
from pkg.models import Report

def test_report_keyword_reference(options):
    Report(captured=5, **options)
"""

    result = PythonValidator().collect_behavioral_artifacts(
        source,
        "tests/test_references.py",
    )

    keyword_references = [
        artifact
        for artifact in result.artifacts
        if artifact.kind == ArtifactKind.FUNCTION
        and artifact.reference_context == "keyword"
    ]
    assert [
        (artifact.name, artifact.import_source, artifact.of)
        for artifact in keyword_references
    ] == [("captured", "pkg.models", "Report")]


def test_behavioral_reference_recorder_records_import_references():
    artifacts = []
    recorder = _BehavioralReferenceRecorder(
        artifacts=artifacts,
        seen=set(),
        seen_test_funcs=set(),
    )

    recorder.add_import_from_references(
        [
            ("Thing", "pkg.alpha", None),
            ("AliasThing", "pkg.beta", "Thing"),
        ]
    )
    recorder.add_import_references(
        [
            ("pkg", "pkg.mod", None, "pkg"),
            ("pm", "pkg.mod", "pkg.mod", "pkg.mod"),
        ]
    )

    import_references = [
        artifact
        for artifact in artifacts
        if artifact.kind == ArtifactKind.FUNCTION
        and artifact.reference_context == "import"
    ]
    assert [
        (artifact.name, artifact.import_source, artifact.alias_of)
        for artifact in import_references
    ] == [
        ("Thing", "pkg.alpha", None),
        ("AliasThing", "pkg.beta", "Thing"),
        ("pkg", "pkg.mod", None),
        ("pm", "pkg.mod", "pkg.mod"),
    ]


def test_python_behavioral_import_reference_recording_is_unchanged():
    source = """\
from pkg.alpha import Thing
from pkg.beta import Thing as AliasThing
import pkg.mod
import pkg.other as po

def test_import_reference_recording():
    assert Thing and AliasThing and pkg and po
"""

    result = PythonValidator().collect_behavioral_artifacts(
        source,
        "tests/test_references.py",
    )

    import_references = [
        artifact
        for artifact in result.artifacts
        if artifact.kind == ArtifactKind.FUNCTION
        and artifact.reference_context == "import"
    ]
    assert [
        (artifact.name, artifact.import_source, artifact.alias_of)
        for artifact in import_references
    ] == [
        ("Thing", "pkg.alpha", None),
        ("AliasThing", "pkg.beta", "Thing"),
        ("pkg", "pkg.mod", None),
        ("po", "pkg.other", "pkg.other"),
    ]
