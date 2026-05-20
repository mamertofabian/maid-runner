from maid_runner.core.types import ArtifactKind
from maid_runner.validators._python_behavioral_scope import _BehavioralExpressionScope
from maid_runner.validators.python import PythonValidator


def test_behavioral_expression_scope_push_pop():
    scope = _BehavioralExpressionScope(
        shadowed_imports={"Migration"},
        module_alias_shadows={"module"},
    )
    shadowed_import_scopes = []
    module_alias_shadow_scopes = []

    scope.push_to(
        shadowed_import_scopes=shadowed_import_scopes,
        module_alias_shadow_scopes=module_alias_shadow_scopes,
    )

    assert shadowed_import_scopes[-1] is scope.shadowed_imports
    assert module_alias_shadow_scopes[-1] is scope.module_alias_shadows

    scope.pop_from(
        shadowed_import_scopes=shadowed_import_scopes,
        module_alias_shadow_scopes=module_alias_shadow_scopes,
    )

    assert shadowed_import_scopes == []
    assert module_alias_shadow_scopes == []


def test_python_behavioral_comprehension_target_still_shadows_module_alias():
    source = """\
import importlib

def test_dynamic_alias_comprehension_shadow():
    module = importlib.import_module("pkg.migrations.0023_split")
    assert [module.Migration for module in [object()]]
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
