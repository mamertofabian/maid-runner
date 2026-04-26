"""Behavioral tests for the Semantic Reference Index.

Covers maid_runner.core.module_paths and maid_runner.core.identity:
    - file_to_module_path: dotted module from a project-relative file path
    - resolve_relative_import: convert `from .x import Y` to absolute module
    - resolve_reexport: one-level barrel resolution through __init__.py
    - match_artifact_to_references: strict identity match with name-only
      fallback when the reference has no resolvable import_source
"""

from __future__ import annotations

from pathlib import Path


from maid_runner.core.identity import match_artifact_to_references
from maid_runner.core.module_paths import (
    file_to_module_path,
    resolve_relative_import,
    resolve_reexport,
)
from maid_runner.core.types import ArtifactKind
from maid_runner.validators.base import FoundArtifact


# ----------------------------------------------------------------------------
# file_to_module_path
# ----------------------------------------------------------------------------


class TestFileToModulePath:
    def test_converts_nested_py_to_dotted(self, tmp_path: Path) -> None:
        target = tmp_path / "pkg" / "sub" / "mod.py"
        target.parent.mkdir(parents=True)
        target.write_text("")
        assert file_to_module_path(target, tmp_path) == "pkg.sub.mod"

    def test_strips_init_to_package_path(self, tmp_path: Path) -> None:
        target = tmp_path / "pkg" / "__init__.py"
        target.parent.mkdir(parents=True)
        target.write_text("")
        assert file_to_module_path(target, tmp_path) == "pkg"

    def test_accepts_string_path(self, tmp_path: Path) -> None:
        target = tmp_path / "a" / "b.py"
        target.parent.mkdir(parents=True)
        target.write_text("")
        assert file_to_module_path(str(target), tmp_path) == "a.b"


# ----------------------------------------------------------------------------
# resolve_relative_import
# ----------------------------------------------------------------------------


class TestResolveRelativeImport:
    def test_level_one_resolves_within_same_package(self) -> None:
        # `from .submod import X` inside pkg.mod_a -> pkg.submod
        assert resolve_relative_import("submod", 1, "pkg.mod_a") == "pkg.submod"

    def test_level_two_walks_up_one_package(self) -> None:
        # `from ..other import X` inside pkg.sub.mod_a -> pkg.other
        assert resolve_relative_import("other", 2, "pkg.sub.mod_a") == "pkg.other"

    def test_level_one_with_no_module_returns_package(self) -> None:
        # `from . import X` inside pkg.mod -> pkg
        assert resolve_relative_import(None, 1, "pkg.mod") == "pkg"

    def test_level_zero_returns_module_unchanged(self) -> None:
        # Absolute import: level=0 means the module is already absolute.
        assert resolve_relative_import("pkg.x", 0, "anywhere.y") == "pkg.x"


# ----------------------------------------------------------------------------
# resolve_reexport (one-level barrel)
# ----------------------------------------------------------------------------


class TestResolveReexport:
    def test_one_level_reexport_resolves_to_defining_module(
        self, tmp_path: Path
    ) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("from .submod import Foo\n")
        (pkg / "submod.py").write_text("class Foo: ...\n")

        assert resolve_reexport("pkg", "Foo", tmp_path) == ("pkg.submod", "Foo")

    def test_returns_none_when_name_not_reexported(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("from .submod import Bar\n")
        (pkg / "submod.py").write_text("class Bar: ...\n")

        assert resolve_reexport("pkg", "Foo", tmp_path) is None

    def test_returns_none_when_module_has_no_init(self, tmp_path: Path) -> None:
        # Plain module file, not a package — no __init__.py to inspect.
        (tmp_path / "lonely.py").write_text("class Foo: ...\n")
        assert resolve_reexport("lonely", "Foo", tmp_path) is None

    def test_aliased_reexport_returns_original_source_name(
        self, tmp_path: Path
    ) -> None:
        # __init__.py: from .submod import Foo as Bar
        # Looking up "Bar" resolves to (pkg.submod, "Foo") — the source
        # module's identifier, before aliasing. The matcher needs this
        # to bridge a test importing `Bar` to an artifact named `Foo`.
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("from .submod import Foo as Bar\n")
        (pkg / "submod.py").write_text("class Foo: ...\n")

        assert resolve_reexport("pkg", "Bar", tmp_path) == ("pkg.submod", "Foo")

    def test_does_not_recurse_through_second_level(self, tmp_path: Path) -> None:
        # pkg.__init__ re-exports from pkg.mid; pkg.mid.__init__ re-exports
        # from pkg.mid.deep. One-level resolution should stop at pkg.mid,
        # NOT walk through to pkg.mid.deep.
        pkg = tmp_path / "pkg"
        mid = pkg / "mid"
        mid.mkdir(parents=True)
        (pkg / "__init__.py").write_text("from .mid import Foo\n")
        (mid / "__init__.py").write_text("from .deep import Foo\n")
        (mid / "deep.py").write_text("class Foo: ...\n")

        # One level only: pkg -> pkg.mid (not pkg.mid.deep).
        assert resolve_reexport("pkg", "Foo", tmp_path) == ("pkg.mid", "Foo")


# ----------------------------------------------------------------------------
# match_artifact_to_references
# ----------------------------------------------------------------------------


def _ref(name: str, import_source: str | None = None) -> FoundArtifact:
    return FoundArtifact(
        kind=ArtifactKind.FUNCTION,
        name=name,
        import_source=import_source,
    )


def _artifact(name: str, module_path: str | None = None) -> FoundArtifact:
    return FoundArtifact(
        kind=ArtifactKind.FUNCTION,
        name=name,
        module_path=module_path,
    )


class TestMatchArtifactToReferences:
    def test_match_when_import_source_equals_module_path(self, tmp_path: Path) -> None:
        artifact = _artifact("Foo", module_path="pkg.mod")
        references = [_ref("Foo", import_source="pkg.mod")]
        assert match_artifact_to_references(artifact, references, tmp_path)

    def test_no_match_when_modules_disagree(self, tmp_path: Path) -> None:
        # Both sides have resolved identity AND they disagree.
        # This is the bug name-matching let through; identity must reject.
        artifact = _artifact("Foo", module_path="pkg.real")
        references = [_ref("Foo", import_source="pkg.other")]
        assert not match_artifact_to_references(artifact, references, tmp_path)

    def test_fallback_to_name_when_reference_has_no_import_source(
        self, tmp_path: Path
    ) -> None:
        # Reference has no resolvable import_source — fallback to name match
        # so currently-passing manifests do not regress.
        artifact = _artifact("Foo", module_path="pkg.mod")
        references = [_ref("Foo", import_source=None)]
        assert match_artifact_to_references(artifact, references, tmp_path)

    def test_no_match_when_names_differ(self, tmp_path: Path) -> None:
        artifact = _artifact("Foo", module_path="pkg.mod")
        references = [_ref("Bar", import_source="pkg.mod")]
        assert not match_artifact_to_references(artifact, references, tmp_path)

    def test_match_through_one_level_reexport(self, tmp_path: Path) -> None:
        # __init__ re-exports Foo from .submod; test imports `from pkg import Foo`.
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("from .submod import Foo\n")
        (pkg / "submod.py").write_text("class Foo: ...\n")

        artifact = _artifact("Foo", module_path="pkg.submod")
        references = [_ref("Foo", import_source="pkg")]
        assert match_artifact_to_references(artifact, references, tmp_path)

    def test_match_against_aliased_reference(self, tmp_path: Path) -> None:
        # Test does `from pkg.mod import Foo as Bar`.
        # Reference is recorded as name=Bar, alias_of=Foo, import_source=pkg.mod.
        # The artifact is named Foo in pkg.mod — must match via alias_of.
        artifact = _artifact("Foo", module_path="pkg.mod")
        aliased = FoundArtifact(
            kind=ArtifactKind.FUNCTION,
            name="Bar",
            import_source="pkg.mod",
            alias_of="Foo",
        )
        assert match_artifact_to_references(artifact, [aliased], tmp_path)

    def test_empty_reference_list_does_not_match(self, tmp_path: Path) -> None:
        artifact = _artifact("Foo", module_path="pkg.mod")
        assert not match_artifact_to_references(artifact, [], tmp_path)

    def test_aliased_barrel_bridges_alias_back_to_artifact_name(
        self, tmp_path: Path
    ) -> None:
        # __init__.py: from .submod import Foo as Bar
        # Test imports `Bar` from the barrel `pkg`. The artifact in the
        # manifest is named `Foo` and lives in pkg.submod. The matcher
        # must consult the barrel's alias mapping to bridge Bar -> Foo.
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("from .submod import Foo as Bar\n")
        (pkg / "submod.py").write_text("class Foo: ...\n")

        artifact = _artifact("Foo", module_path="pkg.submod")
        # Reference is what a test would produce after `from pkg import Bar`:
        # name=Bar, import_source=pkg, alias_of=None.
        ref = FoundArtifact(
            kind=ArtifactKind.FUNCTION,
            name="Bar",
            import_source="pkg",
        )
        assert match_artifact_to_references(artifact, [ref], tmp_path)
