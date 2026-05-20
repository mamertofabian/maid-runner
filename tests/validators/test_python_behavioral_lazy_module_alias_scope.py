from maid_runner.core.types import ArtifactKind
from maid_runner.validators._python_behavioral_scope import (
    _BehavioralLazyModuleAliasScope,
)
from maid_runner.validators.python import PythonValidator


def test_behavioral_lazy_module_alias_scope_push_pop():
    scope = _BehavioralLazyModuleAliasScope()
    module_import_scopes = []
    module_alias_shadow_scopes = []

    scope.push_to(
        module_import_scopes=module_import_scopes,
        module_alias_shadow_scopes=module_alias_shadow_scopes,
    )

    assert module_import_scopes[-1] is scope.module_imports
    assert module_alias_shadow_scopes[-1] is scope.module_alias_shadows

    scope.pop_from(
        module_import_scopes=module_import_scopes,
        module_alias_shadow_scopes=module_alias_shadow_scopes,
    )

    assert module_import_scopes == []
    assert module_alias_shadow_scopes == []


def test_python_behavioral_lazy_lambda_body_still_does_not_rebind_outer_alias():
    source = """\
import importlib

def test_dynamic_alias_lazy_lambda_body_does_not_rebind_outer_alias():
    module = importlib.import_module("pkg.migrations.0023_split")
    (lambda: (module := importlib.import_module("pkg.migrations.0024_other")))
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
    assert any(
        reference.import_source == "pkg.migrations.0023_split"
        for reference in references
    )
