from maid_runner.core.types import ArtifactKind
from maid_runner.validators._python_behavioral_scope import _BehavioralModuleAliasEvents
from maid_runner.validators.python import PythonValidator


def test_behavioral_module_alias_events_record_source_ordered_lookup():
    events = _BehavioralModuleAliasEvents()

    events.record("module", "pkg.migrations.0024_other", (5, 0))
    events.record("module", "pkg.migrations.0023_split", (2, 0))
    events.record("module", None, (8, 0))

    assert events.source_at("module", (1, 0)) == (True, None)
    assert events.source_at("module", (3, 0)) == (
        True,
        "pkg.migrations.0023_split",
    )
    assert events.source_at("module", (6, 0)) == (
        True,
        "pkg.migrations.0024_other",
    )
    assert events.source_at("module", (9, 0)) == (True, None)
    assert events.source_at("other", (9, 0)) == (False, None)

    events.clear()

    assert events.source_at("module", (9, 0)) == (False, None)


def test_python_behavioral_top_level_dynamic_alias_read_still_uses_source_order():
    source = """\
import importlib

module = importlib.import_module("pkg.migrations.0023_split")
Migration = module.Migration
module = importlib.import_module("pkg.migrations.0024_other")

def test_dynamic_alias_reused_top_level_name():
    assert True
"""

    result = PythonValidator().collect_behavioral_artifacts(
        source,
        "tests/test_dynamic_alias.py",
    )

    references = [
        artifact
        for artifact in result.artifacts
        if artifact.kind == ArtifactKind.FUNCTION and artifact.name == "Migration"
    ]
    assert references
    assert any(
        reference.import_source == "pkg.migrations.0023_split"
        for reference in references
    )
