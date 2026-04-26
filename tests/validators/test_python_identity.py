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
