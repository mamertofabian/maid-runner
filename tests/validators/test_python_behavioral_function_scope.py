from maid_runner.core.types import ArtifactKind
from maid_runner.validators._python_behavioral_scope import _BehavioralFunctionScope
from maid_runner.validators.python import PythonValidator


def test_behavioral_function_scope_push_pop():
    scope = _BehavioralFunctionScope(
        shadowed_imports={"Migration"},
        import_bound_names={"migrations"},
        module_alias_shadows={"module"},
        argument_names={"module"},
    )
    local_import_scopes = []
    module_import_scopes = []
    module_alias_shadow_scopes = []
    local_value_scopes = []
    object_owner_scopes = []
    argument_name_scopes = []
    shadowed_import_scopes = []
    function_import_bound_scopes = []

    scope.push_to(
        local_import_scopes=local_import_scopes,
        module_import_scopes=module_import_scopes,
        module_alias_shadow_scopes=module_alias_shadow_scopes,
        local_value_scopes=local_value_scopes,
        object_owner_scopes=object_owner_scopes,
        argument_name_scopes=argument_name_scopes,
        shadowed_import_scopes=shadowed_import_scopes,
        function_import_bound_scopes=function_import_bound_scopes,
    )

    assert local_import_scopes[-1] is scope.imports
    assert module_import_scopes[-1] is scope.module_imports
    assert module_alias_shadow_scopes[-1] is scope.module_alias_shadows
    assert local_value_scopes[-1] is scope.local_values
    assert object_owner_scopes[-1] is scope.object_owners
    assert argument_name_scopes[-1] is scope.argument_names
    assert shadowed_import_scopes[-1] is scope.shadowed_imports
    assert function_import_bound_scopes[-1] is scope.import_bound_names

    scope.pop_from(
        local_import_scopes=local_import_scopes,
        module_import_scopes=module_import_scopes,
        module_alias_shadow_scopes=module_alias_shadow_scopes,
        local_value_scopes=local_value_scopes,
        object_owner_scopes=object_owner_scopes,
        argument_name_scopes=argument_name_scopes,
        shadowed_import_scopes=shadowed_import_scopes,
        function_import_bound_scopes=function_import_bound_scopes,
    )

    assert local_import_scopes == []
    assert module_import_scopes == []
    assert module_alias_shadow_scopes == []
    assert local_value_scopes == []
    assert object_owner_scopes == []
    assert argument_name_scopes == []
    assert shadowed_import_scopes == []
    assert function_import_bound_scopes == []


def test_python_behavioral_function_parameter_still_shadows_module_alias():
    source = """\
import importlib

module = importlib.import_module("pkg.migrations.0023_split")

def test_dynamic_alias_parameter(module):
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
