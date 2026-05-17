"""Identity-aware artifact matching for the Semantic Reference Index.

Replaces bare-name matching (``artifact.name in ref_names``) with a
match that consults ``module_path`` on definitions and ``import_source``
plus ``alias_of`` on references. Disagreement between two resolved
identities is a true mismatch; name-only fallback applies only when the
reference carries no resolvable import information.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, Optional

from maid_runner.core.module_paths import resolve_reexport as _python_resolve_reexport
from maid_runner.core.types import ArtifactKind
from maid_runner.validators.base import FoundArtifact


_ReexportResolver = Callable[[str, str, Path], Optional[tuple[str, str]]]


def _reference_can_cover_artifact(
    reference: FoundArtifact,
    artifact: FoundArtifact,
) -> bool:
    if reference.kind == ArtifactKind.TEST_FUNCTION:
        return False
    if reference.reference_context in {"import", "local"}:
        return False
    if reference.reference_context == "type" and artifact.kind not in {
        ArtifactKind.INTERFACE,
        ArtifactKind.TYPE,
    }:
        return False
    if reference.reference_context == "keyword":
        return (
            artifact.kind == ArtifactKind.ATTRIBUTE
            and reference.import_source is not None
            and (artifact.of is None or reference.of == artifact.of)
        )
    return True


def _module_identity_matches(reference_module: str, artifact_module: str) -> bool:
    if reference_module == artifact_module:
        return True
    if "/" in reference_module or "/" not in artifact_module:
        return False
    if "." in Path(artifact_module).name:
        return False
    return reference_module.replace(".", "/") == artifact_module


def _reference_identity_can_represent_artifact(
    reference: FoundArtifact,
    artifact: FoundArtifact,
    project_root: Path,
    resolver: _ReexportResolver,
) -> bool:
    ref_name = reference.alias_of or reference.name
    if ref_name != artifact.name:
        return False
    if reference.import_source is None or artifact.module_path is None:
        return False
    if _module_identity_matches(reference.import_source, artifact.module_path):
        return True
    reexported = resolver(reference.import_source, ref_name, project_root)
    if reexported is None:
        return False
    resolved_module, original_name = reexported
    return resolved_module == artifact.module_path and original_name == artifact.name


def _reference_module_can_represent_artifact(
    reference: FoundArtifact,
    artifact: FoundArtifact,
    project_root: Path,
    resolver: _ReexportResolver,
) -> bool:
    if reference.import_source is None or artifact.module_path is None:
        return False
    if _module_identity_matches(reference.import_source, artifact.module_path):
        return True

    reexported = resolver(reference.import_source, artifact.name, project_root)
    if reexported is None:
        return False
    resolved_module, original_name = reexported
    return resolved_module == artifact.module_path and original_name == artifact.name


def _module_import_should_block_name_fallback(artifact: FoundArtifact) -> bool:
    return artifact.of is None and artifact.kind in {
        ArtifactKind.CLASS,
        ArtifactKind.FUNCTION,
    }


def _reference_can_block_name_fallback(
    reference: FoundArtifact,
    artifact: FoundArtifact,
) -> bool:
    return reference.reference_context == "import" or _reference_can_cover_artifact(
        reference,
        artifact,
    )


def match_artifact_to_references(
    artifact: FoundArtifact,
    references: Iterable[FoundArtifact],
    project_root: Path,
    *,
    reexport_resolver: Optional[_ReexportResolver] = None,
) -> bool:
    """Return True if any reference matches ``artifact`` by identity.

    Match rules, in order:

    1. The reference's effective name (``alias_of`` if set, else
       ``name``) must equal ``artifact.name``.
    2. If the reference has no ``import_source``, fall back to a
       name-only match so currently-passing manifests do not regress.
    3. If the artifact has no ``module_path``, the name match is
       accepted (no identity to compare against).
    4. Otherwise the reference's ``import_source`` must equal the
       artifact's ``module_path``, OR resolve to it through a one-level
       barrel re-export.

    Aliased-barrel bridge: when no reference's effective name matches
    the artifact's name directly, the matcher additionally asks each
    barrel-rooted reference whether the barrel re-exports a name equal
    to the artifact's name under that reference's bound name (the case
    of ``export { Foo as Bar } from './y'`` paired with
    ``import { Bar } from './pkg-barrel'``).
    """
    refs = list(references)
    resolver = reexport_resolver or _python_resolve_reexport
    root = Path(project_root)
    has_artifact_identity_import = any(
        _reference_can_block_name_fallback(ref, artifact)
        and (
            _reference_identity_can_represent_artifact(ref, artifact, root, resolver)
            or (
                _module_import_should_block_name_fallback(artifact)
                and _reference_module_can_represent_artifact(
                    ref,
                    artifact,
                    root,
                    resolver,
                )
            )
        )
        for ref in refs
    )

    for ref in refs:
        if not _reference_can_cover_artifact(ref, artifact):
            continue
        ref_name = ref.alias_of or ref.name
        if ref_name != artifact.name:
            continue

        if ref.import_source is None:
            if has_artifact_identity_import:
                continue
            return True

        if artifact.module_path is None:
            return True

        if _module_identity_matches(ref.import_source, artifact.module_path):
            return True

        reexported = resolver(ref.import_source, ref_name, root)
        if reexported is not None:
            resolved_module, original_name = reexported
            if (
                resolved_module == artifact.module_path
                and original_name == artifact.name
            ):
                return True

    if artifact.module_path is None:
        return False

    for ref in refs:
        if not _reference_can_cover_artifact(ref, artifact):
            continue
        if ref.import_source is None:
            continue
        ref_name = ref.alias_of or ref.name
        if ref_name == artifact.name:
            continue
        reexported = resolver(ref.import_source, ref_name, root)
        if reexported is None:
            continue
        resolved_module, original_name = reexported
        if resolved_module == artifact.module_path and original_name == artifact.name:
            return True

    return False
