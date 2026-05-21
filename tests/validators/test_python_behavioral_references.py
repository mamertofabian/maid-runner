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


def test_behavioral_reference_recorder_records_discoverable_test_function_reference():
    artifacts = []
    recorder = _BehavioralReferenceRecorder(
        artifacts=artifacts,
        seen=set(),
        seen_test_funcs=set(),
    )

    recorder.add_test_function_reference("test_example", 12)
    recorder.add_test_function_reference("test_example", 18)

    assert [
        (artifact.name, artifact.line)
        for artifact in artifacts
        if artifact.kind == ArtifactKind.TEST_FUNCTION
    ] == [("test_example", 12)]
    assert [
        (artifact.name, artifact.reference_context)
        for artifact in artifacts
        if artifact.kind == ArtifactKind.FUNCTION
    ] == [("test_example", "access")]


def test_python_behavioral_test_function_reference_recording_is_unchanged():
    source = """\
def helper():
    return True

def test_sync_reference_recording():
    def test_nested_reference_recording():
        return helper()
    return test_nested_reference_recording()

async def test_async_reference_recording():
    return helper()
"""

    result = PythonValidator().collect_behavioral_artifacts(
        source,
        "tests/test_references.py",
    )

    test_functions = [
        artifact
        for artifact in result.artifacts
        if artifact.kind == ArtifactKind.TEST_FUNCTION
    ]
    access_references = [
        artifact
        for artifact in result.artifacts
        if artifact.kind == ArtifactKind.FUNCTION
        and artifact.reference_context == "access"
        and artifact.name.startswith("test_")
    ]
    assert [(artifact.name, artifact.line) for artifact in test_functions] == [
        ("test_sync_reference_recording", 4),
        ("test_async_reference_recording", 9),
    ]
    assert [artifact.name for artifact in access_references] == [
        "test_sync_reference_recording",
        "test_async_reference_recording",
    ]


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


def test_behavioral_reference_recorder_records_bound_reference_precedence():
    artifacts = []
    recorder = _BehavioralReferenceRecorder(
        artifacts=artifacts,
        seen=set(),
        seen_test_funcs=set(),
    )

    recorder.add_bound_reference(
        "Thing",
        reference_context="access",
        lexically_shadowed_import=True,
        imported_identity=("pkg.module", None),
    )
    recorder.add_bound_reference(
        "Other",
        reference_context="call",
        local_import=("pkg.local", "Original"),
        imported_identity=("pkg.module", None),
    )
    recorder.add_bound_reference(
        "Local",
        reference_context="access",
        local_value_without_import=True,
        imported_identity=("pkg.module", None),
    )
    recorder.add_bound_reference(
        "Bound",
        reference_context="access",
        function_import_bound=True,
        imported_identity=("pkg.module", None),
    )
    recorder.add_bound_reference(
        "Shadowed",
        reference_context="access",
        module_shadowed=True,
        imported_identity=("pkg.module", None),
    )
    recorder.add_bound_reference(
        "Imported",
        reference_context="call",
        imported_identity=("pkg.module", "Alias"),
    )

    references = [
        artifact
        for artifact in artifacts
        if artifact.kind == ArtifactKind.FUNCTION
        and artifact.reference_context in {"access", "call", "local"}
    ]
    assert [
        (
            artifact.name,
            artifact.reference_context,
            artifact.import_source,
            artifact.alias_of,
        )
        for artifact in references
    ] == [
        ("Thing", "local", None, None),
        ("Other", "call", "pkg.local", "Original"),
        ("Local", "local", None, None),
        ("Bound", "local", None, None),
        ("Shadowed", "local", None, None),
        ("Imported", "call", "pkg.module", "Alias"),
    ]


def test_python_behavioral_bound_reference_recording_is_unchanged():
    source = """\
from pkg.module import Thing

def test_bound_reference_local_import():
    from pkg.local import Thing
    Thing()
"""

    result = PythonValidator().collect_behavioral_artifacts(
        source,
        "tests/test_references.py",
    )

    call_references = [
        artifact
        for artifact in result.artifacts
        if artifact.kind == ArtifactKind.FUNCTION
        and artifact.name == "Thing"
        and artifact.reference_context == "call"
    ]
    assert len(call_references) == 1
    assert call_references[0].import_source == "pkg.local"


def test_behavioral_reference_recorder_records_attribute_reference_precedence():
    artifacts = []
    recorder = _BehavioralReferenceRecorder(
        artifacts=artifacts,
        seen=set(),
        seen_test_funcs=set(),
    )

    recorder.add_attribute_reference(
        "field",
        object_owner_identity=("pkg.models", "Report"),
        resolved_attribute=None,
        root_is_local_context=False,
    )
    recorder.add_attribute_reference(
        "Migration",
        object_owner_identity=None,
        resolved_attribute=("Migration", "pkg.migrations.0023_split"),
        root_is_local_context=False,
    )
    recorder.add_attribute_reference(
        "value",
        object_owner_identity=None,
        resolved_attribute=None,
        root_is_local_context=True,
    )
    recorder.add_attribute_reference(
        "name",
        object_owner_identity=None,
        resolved_attribute=None,
        root_is_local_context=False,
    )

    references = [
        artifact
        for artifact in artifacts
        if artifact.kind == ArtifactKind.FUNCTION
        and artifact.reference_context in {"access", "local"}
    ]
    assert [
        (
            artifact.name,
            artifact.import_source,
            artifact.of,
            artifact.reference_context,
        )
        for artifact in references
    ] == [
        ("field", "pkg.models", "Report", "access"),
        ("Migration", "pkg.migrations.0023_split", None, "access"),
        ("value", None, None, "local"),
        ("name", None, None, "access"),
    ]


def test_python_behavioral_attribute_reference_recording_is_unchanged():
    source = """\
import importlib

class Local:
    value = object()

def test_attribute_reference_recording():
    module = importlib.import_module("pkg.migrations.0023_split")
    local = Local()
    assert module.Migration and local.value
"""

    result = PythonValidator().collect_behavioral_artifacts(
        source,
        "tests/test_references.py",
    )

    migration_references = [
        artifact
        for artifact in result.artifacts
        if artifact.kind == ArtifactKind.FUNCTION
        and artifact.name == "Migration"
        and artifact.reference_context == "access"
    ]
    local_references = [
        artifact
        for artifact in result.artifacts
        if artifact.kind == ArtifactKind.FUNCTION
        and artifact.name == "value"
        and artifact.reference_context == "local"
    ]
    assert len(migration_references) == 1
    assert migration_references[0].import_source == "pkg.migrations.0023_split"
    assert len(local_references) == 1


def test_behavioral_reference_recorder_records_call_attribute_reference_precedence():
    artifacts = []
    recorder = _BehavioralReferenceRecorder(
        artifacts=artifacts,
        seen=set(),
        seen_test_funcs=set(),
    )

    resolved_keyword_identity = recorder.add_call_attribute_reference(
        "Migration",
        resolved_attribute=("Migration", "pkg.migrations.0023_split"),
        root_is_local_context=False,
    )
    local_keyword_identity = recorder.add_call_attribute_reference(
        "run",
        resolved_attribute=None,
        root_is_local_context=True,
    )
    call_keyword_identity = recorder.add_call_attribute_reference(
        "build",
        resolved_attribute=None,
        root_is_local_context=False,
    )

    references = [
        artifact
        for artifact in artifacts
        if artifact.kind == ArtifactKind.FUNCTION
        and artifact.reference_context in {"call", "local"}
    ]
    assert resolved_keyword_identity == ("pkg.migrations.0023_split", "Migration")
    assert local_keyword_identity is None
    assert call_keyword_identity is None
    assert [
        (
            artifact.name,
            artifact.import_source,
            artifact.reference_context,
        )
        for artifact in references
    ] == [
        ("Migration", "pkg.migrations.0023_split", "call"),
        ("run", None, "local"),
        ("build", None, "call"),
    ]


def test_python_behavioral_call_attribute_reference_recording_is_unchanged():
    source = """\
import importlib

class Local:
    def run(self):
        return True

def test_call_attribute_reference_recording():
    module = importlib.import_module("pkg.migrations.0023_split")
    local = Local()
    assert module.Migration(option=1) and local.run()
"""

    result = PythonValidator().collect_behavioral_artifacts(
        source,
        "tests/test_references.py",
    )

    migration_references = [
        artifact
        for artifact in result.artifacts
        if artifact.kind == ArtifactKind.FUNCTION
        and artifact.name == "Migration"
        and artifact.reference_context == "call"
    ]
    keyword_references = [
        artifact
        for artifact in result.artifacts
        if artifact.kind == ArtifactKind.FUNCTION
        and artifact.name == "option"
        and artifact.reference_context == "keyword"
    ]
    local_references = [
        artifact
        for artifact in result.artifacts
        if artifact.kind == ArtifactKind.FUNCTION
        and artifact.name == "run"
        and artifact.reference_context == "local"
    ]
    assert len(migration_references) == 1
    assert migration_references[0].import_source == "pkg.migrations.0023_split"
    assert [
        (artifact.import_source, artifact.of) for artifact in keyword_references
    ] == [("pkg.migrations.0023_split", "Migration")]
    assert len(local_references) == 1
