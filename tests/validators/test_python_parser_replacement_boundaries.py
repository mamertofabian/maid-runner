"""Boundary characterization for Python parser replacement.

These tests pin current stdlib-ast behavior at four semantic boundaries:
dataclass fields, Protocol methods, star-export expansion, and namespace
package identity. Each test documents what the system does today so that
future replacements (astroid, libcst, import-linter) cannot silently change
the contract without a manifest explicitly evolving it.
"""

from pathlib import Path

import pytest

from maid_runner.core.module_paths import file_to_module_path
from maid_runner.core.types import ArtifactKind
from maid_runner.validators.python import PythonValidator


@pytest.fixture()
def validator():
    return PythonValidator()


def _find(artifacts, name, kind=None, of=None):
    for a in artifacts:
        if a.name != name:
            continue
        if kind is not None and a.kind != kind:
            continue
        if of is not None and a.of != of:
            continue
        return a
    return None


def test_dataclass_annotated_fields_remain_uncollected_until_contract_evolves(
    validator,
):
    """Dataclass-generated semantics are NOT modelled; only source annotations are
    collected.

    The stdlib-ast collector treats @dataclass fields as plain ATTRIBUTE
    entries. It does not inspect field() metadata, does not filter ClassVar or
    InitVar, and does not collect the generated __init__, __repr__, or __eq__
    methods because they have no source-level definitions. This boundary must
    be preserved or explicitly evolved under a new manifest before any
    dataclass-aware library (astroid, libcst) is adopted.
    """
    source = """\
from __future__ import annotations
from dataclasses import dataclass, field
from typing import ClassVar, List

@dataclass
class Config:
    host: str
    port: int = 8080
    tags: List[str] = field(default_factory=list)
    MAX_CONNECTIONS: ClassVar[int] = 100
"""
    result = validator.collect_implementation_artifacts(source, "config.py")
    names = {a.name for a in result.artifacts}

    # Plain annotated fields are collected as ATTRIBUTE entries.
    host = _find(result.artifacts, "host", kind=ArtifactKind.ATTRIBUTE, of="Config")
    port = _find(result.artifacts, "port", kind=ArtifactKind.ATTRIBUTE, of="Config")
    tags = _find(result.artifacts, "tags", kind=ArtifactKind.ATTRIBUTE, of="Config")
    assert host is not None, "host field must be collected as attribute"
    assert port is not None, "port field must be collected as attribute"
    assert tags is not None, "tags field must be collected as attribute"

    # ClassVar fields are collected the same way — no filtering.
    max_conn = _find(
        result.artifacts, "MAX_CONNECTIONS", kind=ArtifactKind.ATTRIBUTE, of="Config"
    )
    assert max_conn is not None, "ClassVar field is collected without filtering"

    # Generated dunder methods are absent — they have no source definitions.
    assert "__init__" not in names, "generated __init__ must not be collected"
    assert "__repr__" not in names, "generated __repr__ must not be collected"
    assert "__eq__" not in names, "generated __eq__ must not be collected"


def test_protocol_methods_follow_current_class_method_collection(validator):
    """Protocol abstract methods are collected identically to regular class methods.

    The stdlib-ast collector has no special handling for typing.Protocol
    subclasses. Protocol methods with stub bodies (``...``) are collected as
    METHOD artifacts with is_stub=True, exactly like a regular abstract base
    class method. Any library replacement that adds Protocol-aware semantics
    must first declare that behavior change in a new manifest.
    """
    source = """\
from typing import Protocol, runtime_checkable

@runtime_checkable
class Drawable(Protocol):
    def draw(self, canvas: str) -> None: ...
    def resize(self, factor: float) -> None: ...
    def get_label(self) -> str: ...
"""
    result = validator.collect_implementation_artifacts(source, "protocols.py")

    drawable = _find(result.artifacts, "Drawable", kind=ArtifactKind.CLASS)
    assert drawable is not None, "Protocol class itself must be collected"
    assert "Protocol" in drawable.bases, "Protocol base must be preserved"

    draw = _find(result.artifacts, "draw", kind=ArtifactKind.METHOD, of="Drawable")
    assert draw is not None, "Protocol method draw must be collected"
    assert draw.is_stub is True, "ellipsis body must be recognized as stub"

    resize = _find(result.artifacts, "resize", kind=ArtifactKind.METHOD, of="Drawable")
    assert resize is not None, "Protocol method resize must be collected"
    assert resize.is_stub is True

    get_label = _find(
        result.artifacts, "get_label", kind=ArtifactKind.METHOD, of="Drawable"
    )
    assert get_label is not None, "Protocol method get_label must be collected"
    assert get_label.returns == "str"


def test_all_reexports_do_not_expand_star_exports_without_manifest_evolution(
    validator,
):
    """Star imports in __init__.py are not expanded — this is an intentional boundary.

    The stdlib-ast collector skips ``from module import *`` in every context.
    A module-level ``__all__`` list is collected as a plain ATTRIBUTE entry
    but its VALUE is not inspected to discover the symbols it re-exports.
    Any library or logic change that begins expanding star exports must do so
    under a dedicated manifest with explicit behavioral tests.
    """
    # Star import in __init__.py produces zero artifacts.
    star_source = """\
from .models import *
from .utils import *
from .constants import *
"""
    star_result = validator.collect_implementation_artifacts(star_source, "__init__.py")
    assert star_result.artifacts == [], (
        "star imports must produce zero artifacts — expansion is out of scope"
    )

    # __all__ is collected as a raw attribute, not expanded.
    all_source = """\
from .models import UserModel, OrderModel
from .utils import format_date

__all__ = ["UserModel", "OrderModel", "format_date"]
"""
    all_result = validator.collect_implementation_artifacts(all_source, "__init__.py")
    all_names = {a.name for a in all_result.artifacts}

    # __all__ itself is present as an attribute.
    assert "__all__" in all_names, "__all__ must be collected as a module attribute"

    # The named re-exports are present (from the explicit ImportFrom).
    assert "UserModel" in all_names
    assert "format_date" in all_names

    # Mixed file: star import alongside named imports — star portion is still skipped.
    mixed_source = """\
from .base import BaseClass
from .extras import *
"""
    mixed_result = validator.collect_implementation_artifacts(
        mixed_source, "__init__.py"
    )
    mixed_names = {a.name for a in mixed_result.artifacts}
    assert "BaseClass" in mixed_names, "named import must still be collected"
    # No artifact should appear whose source is the star import.
    assert len(mixed_result.artifacts) == 1, (
        "star import side must contribute zero artifacts"
    )


def test_namespace_package_identity_remains_file_local(validator):
    """Module path derivation is file-path-based only — __init__.py presence is
    not checked.

    file_to_module_path converts a source path to a dotted module name by
    stripping the .py suffix and joining path components. It does not walk the
    filesystem to verify that each directory contains an __init__.py. This means
    a file inside a Python namespace package (PEP 420 directory without
    __init__.py) receives the same dotted path as one inside a regular package.
    Any import-graph library (grimp, import-linter) that distinguishes namespace
    packages from regular packages must be adopted under a separate manifest
    scoped to package-level dependency queries, not artifact extraction.
    """
    root = Path(".")

    # Regular package path.
    regular = file_to_module_path("mypkg/sub/service.py", root)
    assert regular == "mypkg.sub.service"

    # Namespace package path: same derivation, no filesystem check.
    namespace = file_to_module_path("myns/subpkg/service.py", root)
    assert namespace == "myns.subpkg.service"

    # Deeply nested path inside a namespace structure.
    deep = file_to_module_path("corp/tools/reporting/pdf_exporter.py", root)
    assert deep == "corp.tools.reporting.pdf_exporter"

    # __init__.py in a namespace-style directory collapses to the package name.
    init_path = file_to_module_path("myns/subpkg/__init__.py", root)
    assert init_path == "myns.subpkg"

    # Validator module_path method delegates to the same logic.
    result = validator.collect_implementation_artifacts(
        "def helper(): pass\n", "myns/subpkg/utils.py"
    )
    helper = _find(result.artifacts, "helper", kind=ArtifactKind.FUNCTION)
    assert helper is not None
    assert helper.module_path == "myns.subpkg.utils", (
        "module_path must reflect file-local derivation, not filesystem checks"
    )
