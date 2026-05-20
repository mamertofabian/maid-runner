from maid_runner.core.types import ArtifactKind
from maid_runner.validators._python_behavioral_scope import _BehavioralClassScope
from maid_runner.validators.python import PythonValidator


def test_behavioral_class_scope_push_pop_and_active_check():
    scope = _BehavioralClassScope()
    local_import_scopes = []
    module_import_scopes = []
    module_alias_shadow_scopes = []
    local_value_scopes = []
    object_owner_scopes = []

    scope.push_to(
        local_import_scopes=local_import_scopes,
        module_import_scopes=module_import_scopes,
        module_alias_shadow_scopes=module_alias_shadow_scopes,
        local_value_scopes=local_value_scopes,
        object_owner_scopes=object_owner_scopes,
    )

    assert scope.is_active_on(
        local_import_scopes=local_import_scopes,
        module_import_scopes=module_import_scopes,
        module_alias_shadow_scopes=module_alias_shadow_scopes,
        local_value_scopes=local_value_scopes,
        object_owner_scopes=object_owner_scopes,
    )
    scope.imports["Migration"] = ("pkg.migrations", None)
    scope.module_imports["module"] = "pkg.migrations.0023_split"
    scope.module_alias_shadows.add("module")
    scope.local_values.add("Local")
    scope.object_owners["migration"] = ("pkg.migrations", "Migration")

    scope.pop_from(
        local_import_scopes=local_import_scopes,
        module_import_scopes=module_import_scopes,
        module_alias_shadow_scopes=module_alias_shadow_scopes,
        local_value_scopes=local_value_scopes,
        object_owner_scopes=object_owner_scopes,
    )

    assert local_import_scopes == []
    assert module_import_scopes == []
    assert module_alias_shadow_scopes == []
    assert local_value_scopes == []
    assert object_owner_scopes == []


def test_behavioral_class_scope_is_inactive_when_parallel_stack_tops_do_not_match():
    scope = _BehavioralClassScope()

    assert not scope.is_active_on(
        local_import_scopes=[{}],
        module_import_scopes=[scope.module_imports],
        module_alias_shadow_scopes=[scope.module_alias_shadows],
        local_value_scopes=[scope.local_values],
        object_owner_scopes=[scope.object_owners],
    )


def test_python_behavioral_class_body_dynamic_alias_stays_hidden_from_methods():
    source = """\
import importlib

class TestDynamicAliasClassScope:
    module = importlib.import_module("pkg.migrations.0023_split")

    def test_method_cannot_see_class_body_alias(self):
        assert module.Migration
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
    assert all(reference.import_source is None for reference in references)
