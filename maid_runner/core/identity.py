"""Identity-aware artifact matching for the Semantic Reference Index.

Replaces bare-name matching (``artifact.name in ref_names``) with a
match that consults ``module_path`` on definitions and ``import_source``
plus ``alias_of`` on references. Disagreement between two resolved
identities is a true mismatch; name-only fallback applies only when the
reference carries no resolvable import information.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from maid_runner.core.module_paths import resolve_reexport
from maid_runner.validators.base import FoundArtifact


def match_artifact_to_references(
    artifact: FoundArtifact,
    references: Iterable[FoundArtifact],
    project_root: Path,
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
       barrel re-export from a package's ``__init__.py``.
    """
    for ref in references:
        ref_name = ref.alias_of or ref.name
        if ref_name != artifact.name:
            continue

        if ref.import_source is None:
            return True

        if artifact.module_path is None:
            return True

        if ref.import_source == artifact.module_path:
            return True

        reexported = resolve_reexport(ref.import_source, ref_name, Path(project_root))
        if reexported is not None and reexported == artifact.module_path:
            return True

    return False
