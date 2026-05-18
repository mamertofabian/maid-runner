"""Behavioral tests for Python validator identity-aware collection.

Verifies that PythonValidator populates the new identity fields on
FoundArtifact: module_path, import_source, and alias_of.
"""

from __future__ import annotations

import pytest

from maid_runner.validators.base import FoundArtifact
from maid_runner.validators.python import PythonValidator


@pytest.fixture()
def validator() -> PythonValidator:
    return PythonValidator()


def _ref(artifacts: list[FoundArtifact], name: str) -> FoundArtifact | None:
    for a in artifacts:
        if a.name == name:
            return a
    return None


# ----------------------------------------------------------------------------
# Behavioral collection: import_source and alias_of
# ----------------------------------------------------------------------------


class TestImportSourceFromImport:
    def test_from_import_records_source_module(
        self, validator: PythonValidator
    ) -> None:
        source = "from pkg.mod import Foo\n\ndef test_x():\n    Foo()\n"
        result = validator.collect_behavioral_artifacts(source, "test_x.py")
        foo = _ref(result.artifacts, "Foo")
        assert foo is not None
        assert foo.import_source == "pkg.mod"
        assert foo.alias_of is None

    def test_import_and_call_references_carry_distinct_contexts(
        self, validator: PythonValidator
    ) -> None:
        source = "from pkg.mod import Foo\n\ndef test_x():\n    Foo()\n"
        result = validator.collect_behavioral_artifacts(source, "test_x.py")
        foo_refs = [artifact for artifact in result.artifacts if artifact.name == "Foo"]

        assert any(
            ref.reference_context == "import" and ref.import_source == "pkg.mod"
            for ref in foo_refs
        )
        assert any(ref.reference_context == "call" for ref in foo_refs)

    def test_plain_import_records_module_as_source(
        self, validator: PythonValidator
    ) -> None:
        # `import pkg.mod` — the bound name is `pkg`, the module is `pkg.mod`.
        source = "import pkg.mod\n\ndef test_x():\n    pkg.mod.Foo()\n"
        result = validator.collect_behavioral_artifacts(source, "test_x.py")
        ref = _ref(result.artifacts, "pkg") or _ref(result.artifacts, "pkg.mod")
        assert ref is not None
        assert ref.import_source == "pkg.mod"


class TestAliasTracking:
    def test_from_import_as_records_alias(self, validator: PythonValidator) -> None:
        source = "from pkg.mod import Foo as Bar\n\ndef test_x():\n    Bar()\n"
        result = validator.collect_behavioral_artifacts(source, "test_x.py")
        bar = _ref(result.artifacts, "Bar")
        assert bar is not None
        assert bar.import_source == "pkg.mod"
        assert bar.alias_of == "Foo"

    def test_plain_import_as_records_alias(self, validator: PythonValidator) -> None:
        source = "import pkg.mod as pm\n\ndef test_x():\n    pm.Foo()\n"
        result = validator.collect_behavioral_artifacts(source, "test_x.py")
        pm = _ref(result.artifacts, "pm")
        assert pm is not None
        assert pm.import_source == "pkg.mod"
        assert pm.alias_of == "pkg.mod"


class TestRelativeImportResolution:
    def test_relative_import_resolved_to_absolute_module(
        self, validator: PythonValidator
    ) -> None:
        # Test file lives at maid_runner/sub/test_thing.py — the validator
        # must be told the importer's module path so `from .sibling import X`
        # resolves to `maid_runner.sub.sibling`.
        source = "from .sibling import Foo\n\ndef test_x():\n    Foo()\n"
        result = validator.collect_behavioral_artifacts(
            source, "maid_runner/sub/test_thing.py"
        )
        foo = _ref(result.artifacts, "Foo")
        assert foo is not None
        assert foo.import_source == "maid_runner.sub.sibling"


# ----------------------------------------------------------------------------
# Attribute-chain resolution (regression: prevents cross-module name match)
# ----------------------------------------------------------------------------


class TestAttributeChainResolution:
    def test_module_attribute_call_resolves_to_module(
        self, validator: PythonValidator
    ) -> None:
        source = "import pkg.mod\n\ndef test_x():\n    pkg.mod.Foo()\n"
        result = validator.collect_behavioral_artifacts(source, "test_x.py")
        foo = _ref(result.artifacts, "Foo")
        assert foo is not None
        assert foo.import_source == "pkg.mod"

    def test_aliased_module_attribute_call_resolves_to_module(
        self, validator: PythonValidator
    ) -> None:
        source = "import pkg.mod as pm\n\ndef test_x():\n    pm.Foo()\n"
        result = validator.collect_behavioral_artifacts(source, "test_x.py")
        foo = _ref(result.artifacts, "Foo")
        assert foo is not None
        assert foo.import_source == "pkg.mod"

    def test_chain_call_rejects_wrong_module_artifact(
        self, validator: PythonValidator
    ) -> None:
        # Regression: name-only matching let `pkg.other.Foo` match a test
        # that called `pkg.mod.Foo()`. Identity must reject the wrong module.
        from pathlib import Path

        from maid_runner.core.identity import match_artifact_to_references
        from maid_runner.core.types import ArtifactKind

        source = "import pkg.mod\n\ndef test_x():\n    pkg.mod.Foo()\n"
        result = validator.collect_behavioral_artifacts(source, "test_x.py")

        wrong = FoundArtifact(
            kind=ArtifactKind.FUNCTION, name="Foo", module_path="pkg.other"
        )
        right = FoundArtifact(
            kind=ArtifactKind.FUNCTION, name="Foo", module_path="pkg.mod"
        )
        assert not match_artifact_to_references(wrong, result.artifacts, Path("."))
        assert match_artifact_to_references(right, result.artifacts, Path("."))

    def test_from_import_call_rejects_wrong_module_artifact(
        self, validator: PythonValidator
    ) -> None:
        from pathlib import Path

        from maid_runner.core.identity import match_artifact_to_references
        from maid_runner.core.types import ArtifactKind

        source = "from pkg.other import Foo\n\ndef test_x():\n    Foo()\n"
        result = validator.collect_behavioral_artifacts(source, "test_x.py")

        wrong = FoundArtifact(
            kind=ArtifactKind.FUNCTION, name="Foo", module_path="pkg.mod"
        )
        right = FoundArtifact(
            kind=ArtifactKind.FUNCTION, name="Foo", module_path="pkg.other"
        )
        assert not match_artifact_to_references(wrong, result.artifacts, Path("."))
        assert match_artifact_to_references(right, result.artifacts, Path("."))

    def test_from_import_alias_call_matches_original_artifact_name(
        self, validator: PythonValidator
    ) -> None:
        from pathlib import Path

        from maid_runner.core.identity import match_artifact_to_references
        from maid_runner.core.types import ArtifactKind

        source = "from pkg.mod import Foo as Bar\n\ndef test_x():\n    Bar()\n"
        result = validator.collect_behavioral_artifacts(source, "test_x.py")

        artifact = FoundArtifact(
            kind=ArtifactKind.FUNCTION, name="Foo", module_path="pkg.mod"
        )
        assert match_artifact_to_references(artifact, result.artifacts, Path("."))


class TestDynamicImportModuleIdentity:
    def test_importlib_import_module_attribute_reference_records_literal_module_identity(
        self, validator: PythonValidator
    ) -> None:
        assert callable(PythonValidator.collect_behavioral_artifacts)
        source = (
            "import importlib\n\n"
            "def test_split_scores_migration_declares_dependencies():\n"
            "    module = importlib.import_module(\n"
            "        'pkg.migrations.0023_split_scores_and_cosmo_evidence'\n"
            "    )\n"
            "    Migration = module.Migration\n"
            "    assert Migration.dependencies == []\n"
        )

        result = validator.collect_behavioral_artifacts(source, "test_migration.py")

        assert any(
            ref.name == "Migration"
            and ref.import_source
            == "pkg.migrations.0023_split_scores_and_cosmo_evidence"
            and ref.reference_context == "access"
            for ref in result.artifacts
        )

    def test_importlib_import_module_alias_can_shadow_imported_name(
        self, validator: PythonValidator
    ) -> None:
        assert callable(PythonValidator.collect_behavioral_artifacts)
        source = (
            "from django.db import migrations\n"
            "import importlib\n\n"
            "def test_split_scores_migration_declares_dependencies():\n"
            "    migrations = importlib.import_module(\n"
            "        'pkg.migrations.0023_split_scores_and_cosmo_evidence'\n"
            "    )\n"
            "    Migration = migrations.Migration\n"
            "    assert Migration.dependencies == []\n"
        )

        result = validator.collect_behavioral_artifacts(source, "test_migration.py")

        assert any(
            ref.name == "Migration"
            and ref.import_source
            == "pkg.migrations.0023_split_scores_and_cosmo_evidence"
            and ref.reference_context == "access"
            for ref in result.artifacts
        )

    @pytest.mark.parametrize(
        ("source", "expected_source", "scenario"),
        [
            (
                "import importlib\n\n"
                "def test_dynamic_alias_walrus_import():\n"
                "    if (module := importlib.import_module('pkg.migrations.0023_split')):\n"
                "        assert module.Migration\n",
                "pkg.migrations.0023_split",
                "function-local walrus import",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_if_true_branch():\n"
                "    if True:\n"
                "        module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    assert module.Migration\n",
                "pkg.migrations.0023_split",
                "constant true branch records dynamic alias",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_true_and_walrus_import():\n"
                "    True and (module := importlib.import_module('pkg.migrations.0023_split'))\n"
                "    assert module.Migration\n",
                "pkg.migrations.0023_split",
                "evaluated short-circuit operand records dynamic alias",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_rhs_before_rebind():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    module = module.Migration\n"
                "    assert module\n",
                "pkg.migrations.0023_split",
                "assignment RHS before same-name rebind",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_module_if_walrus_import():\n"
                "    assert module.Migration\n\n"
                "if (module := importlib.import_module('pkg.migrations.0023_split')):\n"
                "    pass\n",
                "pkg.migrations.0023_split",
                "module-level if walrus dynamic import after test definition",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_module_expr_walrus_import():\n"
                "    assert module.Migration\n\n"
                "(module := importlib.import_module('pkg.migrations.0023_split'))\n",
                "pkg.migrations.0023_split",
                "module-level expression walrus dynamic import after test definition",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_walrus_attribute_root():\n"
                "    assert (module := importlib.import_module('pkg.migrations.0023_split')).Migration\n",
                "pkg.migrations.0023_split",
                "walrus importlib alias used as attribute root",
            ),
            (
                "import importlib\n\n"
                "def module():\n"
                "    return object()\n\n"
                "def test_dynamic_alias_final_assignment_after_prior_binding():\n"
                "    assert module.Migration\n\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n",
                "pkg.migrations.0023_split",
                "final dynamic assignment covers test despite prior top-level binding",
            ),
            (
                "import importlib\n\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n"
                "module: object\n\n"
                "def test_dynamic_alias_bare_annotation_preserves_alias():\n"
                "    assert module.Migration\n",
                "pkg.migrations.0023_split",
                "bare annotation preserves dynamic alias",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_local_bare_annotation_preserves_alias():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    module: object\n"
                "    assert module.Migration\n",
                "pkg.migrations.0023_split",
                "function-local bare annotation preserves dynamic alias",
            ),
            (
                "import importlib\n\n"
                "def configure(**kwargs):\n"
                "    return kwargs\n\n"
                "def test_dynamic_alias_call_keyword_walrus_import():\n"
                "    assert module.Migration\n\n"
                "configure(value=(module := importlib.import_module('pkg.migrations.0023_split')))\n",
                "pkg.migrations.0023_split",
                "module-level call keyword dynamic import after test definition",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_function_default_walrus_import():\n"
                "    assert module.Migration\n\n"
                "def helper(value=(module := importlib.import_module('pkg.migrations.0023_split'))):\n"
                "    return value\n",
                "pkg.migrations.0023_split",
                "module-level function default dynamic import after test definition",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_lambda_default_walrus_import():\n"
                "    assert module.Migration\n\n"
                "(lambda value=(module := importlib.import_module('pkg.migrations.0023_split')): value)\n",
                "pkg.migrations.0023_split",
                "module-level lambda default dynamic import after test definition",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_class_base_walrus_import():\n"
                "    assert module.Migration\n\n"
                "class Helper((module := importlib.import_module('pkg.migrations.0023_split')).Base):\n"
                "    pass\n",
                "pkg.migrations.0023_split",
                "module-level class base dynamic import after test definition",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_listcomp_guard_walrus_import():\n"
                "    assert module.Migration\n\n"
                "[value for value in [object()] if (module := importlib.import_module('pkg.migrations.0023_split'))]\n",
                "pkg.migrations.0023_split",
                "module-level list comprehension guard dynamic import after test definition",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_class_body_does_not_escape():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    class Helper:\n"
                "        module = importlib.import_module('pkg.migrations.0024_other')\n"
                "    assert module.Migration\n",
                "pkg.migrations.0023_split",
                "class body dynamic import does not replace outer alias",
            ),
            (
                "import importlib\n\n"
                "class TestDynamicAliasClassBodyRead:\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    Migration = module.Migration\n\n"
                "    def test_class_body_read_records_alias(self):\n"
                "        assert True\n",
                "pkg.migrations.0023_split",
                "class body expression sees class-body dynamic alias",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_for_iterable_before_target():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    for module in [module.Migration]:\n"
                "        assert module\n",
                "pkg.migrations.0023_split",
                "for iterable sees alias before target rebind",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_match_class_pattern():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    match object():\n"
                "        case module.Migration():\n"
                "            assert True\n",
                "pkg.migrations.0023_split",
                "match class pattern records dynamic alias reference",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_same_name_function_default():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    def module(value=module.Migration):\n"
                "        return value\n"
                "    assert module\n",
                "pkg.migrations.0023_split",
                "function default sees alias before function name binding",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_same_name_class_base():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    class module(module.Migration):\n"
                "        pass\n"
                "    assert module\n",
                "pkg.migrations.0023_split",
                "class base sees alias before class name binding",
            ),
            (
                "import importlib\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n"
                "Migration = module.Migration\n"
                "module = importlib.import_module('pkg.migrations.0024_other')\n\n"
                "def test_dynamic_alias_reused_top_level_name():\n"
                "    assert True\n",
                "pkg.migrations.0023_split",
                "reused top-level alias keeps earlier read identity",
            ),
            (
                "import importlib\n"
                "import pkg.migrations as module\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n"
                "Migration = module.Migration\n"
                "module = object()\n\n"
                "def test_dynamic_alias_imported_name_then_later_rebind():\n"
                "    assert True\n",
                "pkg.migrations.0023_split",
                "source-ordered dynamic alias read survives later non-module rebind",
            ),
            (
                "import importlib\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n"
                "module = module.Migration\n\n"
                "def test_dynamic_alias_module_level_rhs_before_rebind():\n"
                "    assert True\n",
                "pkg.migrations.0023_split",
                "module-level assignment RHS sees alias before same-name rebind",
            ),
            (
                "import importlib\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n\n"
                "def module(value=module.Migration):\n"
                "    return value\n\n"
                "def test_dynamic_alias_module_level_function_default():\n"
                "    assert True\n",
                "pkg.migrations.0023_split",
                "module-level function default sees alias before same-name binding",
            ),
            (
                "import importlib\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n\n"
                "class module(module.Migration):\n"
                "    pass\n\n"
                "def test_dynamic_alias_module_level_class_base():\n"
                "    assert True\n",
                "pkg.migrations.0023_split",
                "module-level class base sees alias before same-name binding",
            ),
            (
                "import importlib\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n\n"
                "for module in [module.Migration]:\n"
                "    pass\n\n"
                "def test_dynamic_alias_module_level_for_iterable():\n"
                "    assert True\n",
                "pkg.migrations.0023_split",
                "module-level for iterable sees alias before target binding",
            ),
            (
                "import contextlib\n"
                "import importlib\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n\n"
                "with contextlib.nullcontext(module.Migration) as module:\n"
                "    pass\n\n"
                "def test_dynamic_alias_module_level_with_context():\n"
                "    assert True\n",
                "pkg.migrations.0023_split",
                "module-level with context sees alias before optional target binding",
            ),
            (
                "import importlib\n"
                "import pkg.migrations as module\n"
                "Migration = module.Migration\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n\n"
                "def test_static_alias_before_dynamic_rebind():\n"
                "    assert True\n",
                "pkg.migrations",
                "static alias read before later dynamic rebind",
            ),
            (
                "import importlib\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n"
                "import pkg.migrations as module\n"
                "Migration = module.Migration\n\n"
                "def test_static_alias_after_dynamic_rebind():\n"
                "    assert True\n",
                "pkg.migrations",
                "static alias read after dynamic rebind",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_lambda_default():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    assert (lambda module=module.Migration: module)()\n",
                "pkg.migrations.0023_split",
                "lambda default sees alias before parameter binding",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_comprehension_outer_iterable():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    assert [module for module in [module.Migration]]\n",
                "pkg.migrations.0023_split",
                "comprehension outer iterable sees alias before target binding",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_lazy_lambda_body_does_not_rebind_outer_alias():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    (lambda: (module := importlib.import_module('pkg.migrations.0024_other')))\n"
                "    assert module.Migration\n",
                "pkg.migrations.0023_split",
                "lazy lambda body does not rebind outer dynamic alias",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_lazy_generator_body_does_not_rebind_outer_alias():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    ((module := importlib.import_module('pkg.migrations.0024_other')) for _ in [object()])\n"
                "    assert module.Migration\n",
                "pkg.migrations.0023_split",
                "lazy generator body does not rebind outer dynamic alias",
            ),
        ],
    )
    def test_importlib_import_module_alias_records_runtime_ordered_identity(
        self,
        validator: PythonValidator,
        source: str,
        expected_source: str,
        scenario: str,
    ) -> None:
        assert callable(PythonValidator.collect_behavioral_artifacts)

        result = validator.collect_behavioral_artifacts(source, "test_migration.py")

        assert any(
            ref.name == "Migration"
            and ref.import_source == expected_source
            and ref.reference_context == "access"
            for ref in result.artifacts
        ), scenario

    @pytest.mark.parametrize(
        ("source", "scenario"),
        [
            (
                "import importlib\n\n"
                "def test_dynamic_alias_for_target():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    for module in [object()]:\n"
                "        assert module.Migration\n",
                "function-local for target",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_if_false_branch():\n"
                "    if False:\n"
                "        module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    assert module.Migration\n",
                "constant false branch does not bind dynamic alias",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_false_and_walrus_import():\n"
                "    False and (module := importlib.import_module('pkg.migrations.0023_split'))\n"
                "    assert module.Migration\n",
                "short-circuited function expression does not bind dynamic alias",
            ),
            (
                "import importlib\n"
                "if False:\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n\n"
                "def test_dynamic_alias_module_if_false_branch():\n"
                "    assert module.Migration\n",
                "module-level constant false branch does not bind dynamic alias",
            ),
            (
                "import importlib\n"
                "False and (module := importlib.import_module('pkg.migrations.0023_split'))\n\n"
                "def test_dynamic_alias_module_false_and_walrus_import():\n"
                "    assert module.Migration\n",
                "short-circuited module expression does not bind dynamic alias",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_nested_function():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    def module():\n"
                "        return object()\n"
                "    assert module.Migration\n",
                "function-local nested function",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_nested_class():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    class module:\n"
                "        pass\n"
                "    assert module.Migration\n",
                "function-local nested class",
            ),
            (
                "import contextlib\n"
                "import importlib\n\n"
                "def test_dynamic_alias_with_target():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    with contextlib.nullcontext(object()) as module:\n"
                "        assert module.Migration\n",
                "function-local with target",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_delete_target():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    del module\n"
                "    assert module.Migration\n",
                "function-local delete target",
            ),
            (
                "import importlib\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n"
                "import other as module\n\n"
                "def test_dynamic_alias_module_import_rebind():\n"
                "    assert module.Migration\n",
                "module-level import rebind",
            ),
            (
                "import importlib\n"
                "(module := importlib.import_module('pkg.migrations.0023_split'))\n\n"
                "def test_dynamic_alias_stale_top_level_expression_rebind():\n"
                "    assert module.Migration\n\n"
                "module = object()\n",
                "final top-level rebind after dynamic expression removes alias",
            ),
            (
                "import importlib\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n\n"
                "def test_dynamic_alias_parameter(module):\n"
                "    assert module.Migration\n",
                "module-level alias shadowed by test parameter",
            ),
            (
                "import importlib\n\n"
                "class Local:\n"
                "    Migration = object()\n\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n\n"
                "def test_dynamic_alias_local_assignment():\n"
                "    module = Local()\n"
                "    assert module.Migration\n",
                "module-level alias shadowed by local assignment",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_nested_parameter():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    def helper(module):\n"
                "        return module.Migration\n"
                "    assert helper(object())\n",
                "outer local alias shadowed by nested parameter",
            ),
            (
                "import importlib\n\n"
                "class Local:\n"
                "    Migration = object()\n\n"
                "def test_dynamic_alias_named_expression():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    (module := Local())\n"
                "    assert module.Migration\n",
                "function-local named expression",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_match_capture():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    match object():\n"
                "        case module:\n"
                "            assert module.Migration\n",
                "function-local match capture",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_exception_binding():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    try:\n"
                "        raise RuntimeError()\n"
                "    except RuntimeError as module:\n"
                "        assert module.Migration\n",
                "function-local exception binding",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_exception_target_cleanup():\n"
                "    try:\n"
                "        raise RuntimeError()\n"
                "    except RuntimeError as module:\n"
                "        module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    assert module.Migration\n",
                "function-local exception target cleanup",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_augassign():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    module += object()\n"
                "    assert module.Migration\n",
                "function-local augmented assignment",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_tuple_dynamic_rebind():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    (module,) = importlib.import_module('pkg.migrations.0024_other')\n"
                "    assert module.Migration\n",
                "function-local tuple dynamic import target",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_lambda_shadow():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    assert (lambda module: module.Migration)(object())\n",
                "lambda parameter shadows dynamic alias",
            ),
            (
                "import importlib\n\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n\n"
                "def test_dynamic_alias_lambda_default_late_shadow():\n"
                "    assert module.Migration\n"
                "    (lambda value=(module := object()): value)\n",
                "lambda default walrus shadows earlier function access",
            ),
            (
                "import importlib\n\n"
                "def configure(**kwargs):\n"
                "    return kwargs\n\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n\n"
                "def test_dynamic_alias_keyword_late_shadow():\n"
                "    assert module.Migration\n"
                "    configure(value=(module := object()))\n",
                "call keyword walrus shadows earlier function access",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_comprehension_shadow():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    assert [module.Migration for module in [object()]]\n",
                "comprehension target shadows dynamic alias",
            ),
            (
                "import importlib\n\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n\n"
                "def test_dynamic_alias_comprehension_guard_late_shadow():\n"
                "    assert module.Migration\n"
                "    [value for value in [object()] if (module := object())]\n",
                "comprehension guard walrus shadows earlier function access",
            ),
            (
                "import importlib\n\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n\n"
                "def test_dynamic_alias_generator_body_late_shadow():\n"
                "    assert module.Migration\n"
                "    ((module := object()) for _ in [object()])\n",
                "generator expression body walrus shadows earlier function access",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_comprehension_later_iterable_shadow():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    assert [module for _ in [object()] for module in [module.Migration]]\n",
                "later comprehension target shadows its iterable in comprehension scope",
            ),
            (
                "import importlib\n\n"
                "def test_dynamic_alias_generator_expr_body_not_evaluated():\n"
                "    assert module.Migration\n\n"
                "((module := importlib.import_module('pkg.migrations.0023_split')) for _ in [object()])\n",
                "module-level generator expression body not evaluated at creation",
            ),
            (
                "import importlib\n\n"
                "(lambda: (module := importlib.import_module('pkg.migrations.0023_split')))\n\n"
                "def test_dynamic_alias_lambda_body_not_evaluated():\n"
                "    assert module.Migration\n",
                "module-level lambda body not evaluated at definition",
            ),
            (
                "import importlib\n\n"
                "((module := importlib.import_module('pkg.migrations.0023_split')) for _ in [object()])\n\n"
                "def test_dynamic_alias_generator_body_before_test_not_evaluated():\n"
                "    assert module.Migration\n",
                "module-level generator expression body before test not evaluated",
            ),
            (
                "import importlib\n\n"
                "def ctx(value=None):\n"
                "    return value\n\n"
                "def test_dynamic_alias_with_later_context_shadow():\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    with ctx() as module, ctx(module.Migration):\n"
                "        assert True\n",
                "with target shadows dynamic alias before later context expression",
            ),
            (
                "import importlib\n\n"
                "class TestDynamicAliasClassScope:\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n\n"
                "    def test_method_cannot_see_class_body_alias(self):\n"
                "        assert module.Migration\n",
                "class body alias does not leak into method scope",
            ),
            (
                "import importlib\n\n"
                "class TestDynamicAliasClassScope:\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n\n"
                "    if True:\n"
                "        def test_nested_method_cannot_see_class_body_alias(self):\n"
                "            assert module.Migration\n",
                "class body alias does not leak into nested method scope",
            ),
            (
                "import importlib\n\n"
                "class TestDynamicAliasClassScope:\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    test_lambda_cannot_see_class_body_alias = (\n"
                "        lambda self: module.Migration\n"
                "    )\n",
                "class body alias does not leak into lambda body",
            ),
            (
                "import importlib\n\n"
                "class TestDynamicAliasClassScope:\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    values = [module.Migration for _ in [object()]]\n\n"
                "    def test_class_body_listcomp_alias_escape(self):\n"
                "        assert True\n",
                "class body alias does not leak into list comprehension body",
            ),
            (
                "import importlib\n\n"
                "class TestDynamicAliasClassScope:\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n"
                "    values = (module.Migration for _ in [object()])\n\n"
                "    def test_class_body_generator_alias_escape(self):\n"
                "        assert True\n",
                "class body alias does not leak into generator expression body",
            ),
            (
                "import importlib\n\n"
                "class TestDynamicAliasOuterClassScope:\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n\n"
                "    class Inner:\n"
                "        Migration = module.Migration\n",
                "outer class body alias does not leak into nested class body",
            ),
            (
                "import importlib\n\n"
                "class Local:\n"
                "    Migration = object()\n\n"
                "module = Local()\n"
                "Migration = module.Migration\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n\n"
                "def test_dynamic_alias_future_module_binding():\n"
                "    assert True\n",
                "module-level read before future dynamic alias binding",
            ),
            (
                "import importlib\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n\n"
                "def test_dynamic_alias_module_if_walrus():\n"
                "    assert module.Migration\n\n"
                "if (module := object()):\n"
                "    pass\n",
                "module-level if walrus after test definition",
            ),
            (
                "import importlib\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n\n"
                "def test_dynamic_alias_module_while_walrus():\n"
                "    assert module.Migration\n\n"
                "while (module := object()):\n"
                "    break\n",
                "module-level while walrus after test definition",
            ),
            (
                "import importlib\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n\n"
                "def test_dynamic_alias_function_default_walrus():\n"
                "    assert module.Migration\n\n"
                "def helper(value=(module := object())):\n"
                "    return value\n",
                "module-level function default walrus after test definition",
            ),
            (
                "import importlib\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n\n"
                "def test_dynamic_alias_class_decorator_walrus():\n"
                "    assert module.Migration\n\n"
                "@((module := lambda cls: cls))\n"
                "class Helper:\n"
                "    pass\n",
                "module-level class decorator walrus after test definition",
            ),
            (
                "import importlib\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n\n"
                "for module in [object()]:\n"
                "    Migration = module.Migration\n\n"
                "def test_dynamic_alias_module_for_body_shadow():\n"
                "    assert True\n",
                "module-level for body sees target binding",
            ),
            (
                "import contextlib\n"
                "import importlib\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n\n"
                "with contextlib.nullcontext(object()) as module:\n"
                "    Migration = module.Migration\n\n"
                "def test_dynamic_alias_module_with_body_shadow():\n"
                "    assert True\n",
                "module-level with body sees optional target binding",
            ),
            (
                "import importlib\n"
                "module = importlib.import_module('pkg.migrations.0023_split')\n\n"
                "match object():\n"
                "    case module:\n"
                "        Migration = module.Migration\n\n"
                "def test_dynamic_alias_module_match_capture_body_shadow():\n"
                "    assert True\n",
                "module-level match capture body sees capture binding",
            ),
            (
                "import importlib\n\n"
                "try:\n"
                "    raise RuntimeError()\n"
                "except RuntimeError as module:\n"
                "    module = importlib.import_module('pkg.migrations.0023_split')\n\n"
                "def test_dynamic_alias_module_exception_cleanup():\n"
                "    assert module.Migration\n",
                "module-level exception target cleanup",
            ),
        ],
    )
    def test_importlib_import_module_alias_rebindings_do_not_retain_literal_module_identity(
        self, validator: PythonValidator, source: str, scenario: str
    ) -> None:
        assert callable(PythonValidator.collect_behavioral_artifacts)

        result = validator.collect_behavioral_artifacts(source, "test_migration.py")

        assert not any(
            ref.name == "Migration"
            and ref.import_source == "pkg.migrations.0023_split"
            and ref.reference_context == "access"
            for ref in result.artifacts
        ), scenario


# ----------------------------------------------------------------------------
# Implementation collection: module_path on defined artifacts
# ----------------------------------------------------------------------------


class TestModulePathOnImplementation:
    def test_collected_artifact_carries_module_path(
        self, validator: PythonValidator
    ) -> None:
        source = "class Foo:\n    pass\n\ndef bar():\n    pass\n"
        result = validator.collect_implementation_artifacts(source, "pkg/sub/mod.py")
        foo = _ref(result.artifacts, "Foo")
        bar = _ref(result.artifacts, "bar")
        assert foo is not None and foo.module_path == "pkg.sub.mod"
        assert bar is not None and bar.module_path == "pkg.sub.mod"

    def test_init_file_module_path_collapses_to_package(
        self, validator: PythonValidator
    ) -> None:
        source = "from .submod import Foo\n"
        result = validator.collect_implementation_artifacts(source, "pkg/__init__.py")
        foo = _ref(result.artifacts, "Foo")
        # Re-exported via __init__ — its module_path should be the package
        # (pkg), not the original `pkg.submod`. Identity matching uses
        # resolve_reexport to reconcile these.
        assert foo is not None
        assert foo.module_path == "pkg"


# ----------------------------------------------------------------------------
# Backward compatibility: identity fields default to None
# ----------------------------------------------------------------------------


class TestIdentityFieldsAreOptional:
    def test_found_artifact_constructible_without_identity_fields(self) -> None:
        from maid_runner.core.types import ArtifactKind

        a = FoundArtifact(kind=ArtifactKind.FUNCTION, name="Foo")
        assert a.module_path is None
        assert a.import_source is None
        assert a.alias_of is None
