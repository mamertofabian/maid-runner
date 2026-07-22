"""Behavioral coverage for ownerless module-attribute removals."""

from __future__ import annotations

from pathlib import Path

from maid_runner.core.chain import ManifestChain
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode
from maid_runner.core.supersession_audit import SupersessionAuditor
from maid_runner.core.validate import ValidationEngine


def _write_removed_attribute_manifest(
    project_root: Path,
    *,
    source_path: str = "src/constants.ts",
) -> Path:
    manifest_path = project_root / "removed.manifest.yaml"
    manifest_path.write_text(
        f"""schema: "2"
goal: "Remove a module constant"
type: fix
removed_artifacts:
  - kind: attribute
    name: CREATE_TOKEN_URL
    file: {source_path}
    reason: "The legacy link is gone"
files:
  scope:
    - path: {source_path}
      reason: "Remove the legacy module constant"
validate:
  - pytest
"""
    )
    return manifest_path


def _write_manifest(path: Path, content: str) -> None:
    path.write_text(content)


def test_absent_typescript_module_attribute_is_verified_removed(
    tmp_path: Path,
) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "constants.ts").write_text("export const ACTIVE_LINK = 'kept';\n")
    manifest = load_manifest(_write_removed_attribute_manifest(tmp_path))

    errors = ValidationEngine(project_root=tmp_path).validate_removed_artifacts(
        manifest
    )

    assert errors == []


def test_present_typescript_module_attribute_reports_e311(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "constants.ts").write_text(
        "export const CREATE_TOKEN_URL = 'still-present';\n"
    )
    manifest = load_manifest(_write_removed_attribute_manifest(tmp_path))

    errors = ValidationEngine(project_root=tmp_path).validate_removed_artifacts(
        manifest
    )

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.REMOVED_ARTIFACT_STILL_PRESENT
    assert "still defined in the source" in errors[0].message
    assert "owner" not in errors[0].message


def test_supersession_accepts_verified_module_attribute_removal(
    tmp_path: Path,
) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "constants.ts").write_text("export const ACTIVE_LINK = 'kept';\n")
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    _write_manifest(
        manifests_dir / "original.manifest.yaml",
        """schema: "2"
goal: "Declare the legacy module constant"
type: feature
files:
  create:
    - path: src/constants.ts
      artifacts:
        - kind: attribute
          name: CREATE_TOKEN_URL
          type: string
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
""",
    )
    _write_manifest(
        manifests_dir / "replacement.manifest.yaml",
        """schema: "2"
goal: "Remove the legacy module constant"
type: fix
supersedes: [original]
removed_artifacts:
  - kind: attribute
    name: CREATE_TOKEN_URL
    file: src/constants.ts
    reason: "The legacy link is gone"
files:
  scope:
    - path: src/constants.ts
      reason: "Remove the legacy module constant"
validate:
  - pytest
created: "2026-02-01T00:00:00Z"
""",
    )
    chain = ManifestChain(manifests_dir, project_root=tmp_path)

    violations = SupersessionAuditor(project_root=tmp_path).find_violations(chain)

    assert violations == ()


def test_ownerless_removal_does_not_exempt_owned_attribute(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "constants.ts").write_text(
        "export class Links {\n  CREATE_TOKEN_URL: string = 'owned-member';\n}\n"
    )
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    _write_manifest(
        manifests_dir / "original.manifest.yaml",
        """schema: "2"
goal: "Declare the owned link"
type: feature
files:
  create:
    - path: src/constants.ts
      artifacts:
        - kind: attribute
          name: CREATE_TOKEN_URL
          of: Links
          type: string
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
""",
    )
    _write_manifest(
        manifests_dir / "replacement.manifest.yaml",
        """schema: "2"
goal: "Attempt an ownerless removal"
type: fix
supersedes: [original]
removed_artifacts:
  - kind: attribute
    name: CREATE_TOKEN_URL
    file: src/constants.ts
    reason: "Only a module binding was intended to be removed"
files:
  scope:
    - path: src/constants.ts
      reason: "Remove a module binding"
validate:
  - pytest
created: "2026-02-01T00:00:00Z"
""",
    )
    chain = ManifestChain(manifests_dir, project_root=tmp_path)

    violations = SupersessionAuditor(project_root=tmp_path).find_violations(chain)

    assert len(violations) == 1
    assert violations[0].artifact_key == "attribute:Links.CREATE_TOKEN_URL"


def test_owned_attribute_removal_with_of_exempts_exact_owner(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "types.ts").write_text(
        "export interface ContactInsert {}\n"
        "export interface ExternalTicketTokenRow {\n  created_by: string;\n}\n"
    )
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    _write_manifest(
        manifests_dir / "original.manifest.yaml",
        """schema: "2"
goal: "Declare ContactInsert and a surviving row type"
type: feature
files:
  create:
    - path: src/types.ts
      artifacts:
        - kind: interface
          name: ContactInsert
        - kind: attribute
          name: created_by
          of: ContactInsert
          type: string
        - kind: attribute
          name: first_name
          of: ContactInsert
          type: string
        - kind: interface
          name: ExternalTicketTokenRow
        - kind: attribute
          name: created_by
          of: ExternalTicketTokenRow
          type: string
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
""",
    )
    _write_manifest(
        manifests_dir / "replacement.manifest.yaml",
        """schema: "2"
goal: "Remove ContactInsert members with of"
type: fix
supersedes: [original]
removed_artifacts:
  - kind: attribute
    name: created_by
    of: ContactInsert
    file: src/types.ts
    reason: "Removed with ContactInsert"
  - kind: attribute
    name: first_name
    of: ContactInsert
    file: src/types.ts
    reason: "Removed with ContactInsert"
files:
  edit:
    - path: src/types.ts
      artifacts:
        - kind: interface
          name: ContactInsert
        - kind: interface
          name: ExternalTicketTokenRow
validate:
  - pytest
created: "2026-02-01T00:00:00Z"
""",
    )
    chain = ManifestChain(manifests_dir, project_root=tmp_path)

    violations = SupersessionAuditor(project_root=tmp_path).find_violations(chain)

    assert len(violations) == 1
    assert violations[0].artifact_key == "attribute:ExternalTicketTokenRow.created_by"


def test_verified_owner_type_removal_cascades_to_owned_attributes(
    tmp_path: Path,
) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "types.ts").write_text(
        "export interface ExternalTicketTokenRow {\n  created_by: string;\n}\n"
    )
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    _write_manifest(
        manifests_dir / "original.manifest.yaml",
        """schema: "2"
goal: "Declare ContactInsert fields"
type: feature
files:
  create:
    - path: src/types.ts
      artifacts:
        - kind: interface
          name: ContactInsert
        - kind: attribute
          name: first_name
          of: ContactInsert
          type: string
        - kind: attribute
          name: created_by
          of: ContactInsert
          type: string
        - kind: interface
          name: ExternalTicketTokenRow
        - kind: attribute
          name: created_by
          of: ExternalTicketTokenRow
          type: string
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
""",
    )
    _write_manifest(
        manifests_dir / "replacement.manifest.yaml",
        """schema: "2"
goal: "Remove only the ContactInsert owner type"
type: fix
supersedes: [original]
removed_artifacts:
  - kind: interface
    name: ContactInsert
    file: src/types.ts
    reason: "Obsolete insert contract"
files:
  edit:
    - path: src/types.ts
      artifacts:
        - kind: interface
          name: ExternalTicketTokenRow
        - kind: attribute
          name: created_by
          of: ExternalTicketTokenRow
          type: string
validate:
  - pytest
created: "2026-02-01T00:00:00Z"
""",
    )
    chain = ManifestChain(manifests_dir, project_root=tmp_path)

    violations = SupersessionAuditor(project_root=tmp_path).find_violations(chain)

    assert violations == ()


def test_owner_cascade_does_not_exempt_same_named_attribute_on_other_owner(
    tmp_path: Path,
) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "types.ts").write_text(
        "export interface ExternalTicketTokenRow {\n  created_by: string;\n}\n"
    )
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    _write_manifest(
        manifests_dir / "original.manifest.yaml",
        """schema: "2"
goal: "Declare both owners' created_by"
type: feature
files:
  create:
    - path: src/types.ts
      artifacts:
        - kind: interface
          name: ContactInsert
        - kind: attribute
          name: created_by
          of: ContactInsert
          type: string
        - kind: interface
          name: ExternalTicketTokenRow
        - kind: attribute
          name: created_by
          of: ExternalTicketTokenRow
          type: string
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
""",
    )
    _write_manifest(
        manifests_dir / "replacement.manifest.yaml",
        """schema: "2"
goal: "Remove ContactInsert without re-declaring the surviving created_by"
type: fix
supersedes: [original]
removed_artifacts:
  - kind: interface
    name: ContactInsert
    file: src/types.ts
    reason: "Obsolete insert contract"
files:
  edit:
    - path: src/types.ts
      artifacts:
        - kind: interface
          name: ExternalTicketTokenRow
validate:
  - pytest
created: "2026-02-01T00:00:00Z"
""",
    )
    chain = ManifestChain(manifests_dir, project_root=tmp_path)

    violations = SupersessionAuditor(project_root=tmp_path).find_violations(chain)

    assert len(violations) == 1
    assert violations[0].artifact_key == ("attribute:ExternalTicketTokenRow.created_by")


def test_owner_cascade_requires_owner_name_absent_across_structural_kinds(
    tmp_path: Path,
) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "types.ts").write_text(
        "export class ContactInsert {\n  created_by: string = 'kept';\n}\n"
    )
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    _write_manifest(
        manifests_dir / "original.manifest.yaml",
        """schema: "2"
goal: "Declare the original ContactInsert interface and member"
type: feature
files:
  create:
    - path: src/types.ts
      artifacts:
        - kind: interface
          name: ContactInsert
        - kind: attribute
          name: created_by
          of: ContactInsert
          type: string
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
""",
    )
    _write_manifest(
        manifests_dir / "replacement.manifest.yaml",
        """schema: "2"
goal: "Replace the interface with a same-named class"
type: fix
supersedes: [original]
removed_artifacts:
  - kind: interface
    name: ContactInsert
    file: src/types.ts
    reason: "Interface replaced by a class"
files:
  edit:
    - path: src/types.ts
      artifacts:
        - kind: class
          name: ContactInsert
validate:
  - pytest
created: "2026-02-01T00:00:00Z"
""",
    )
    chain = ManifestChain(manifests_dir, project_root=tmp_path)

    violations = SupersessionAuditor(project_root=tmp_path).find_violations(chain)

    assert len(violations) == 1
    assert violations[0].artifact_key == "attribute:ContactInsert.created_by"


def test_e110_suggestion_names_of_for_owned_attribute_drop(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "types.ts").write_text("export interface Keeper {\n  kept: string;\n}\n")
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    _write_manifest(
        manifests_dir / "original.manifest.yaml",
        """schema: "2"
goal: "Declare an owned attribute"
type: feature
files:
  create:
    - path: src/types.ts
      artifacts:
        - kind: interface
          name: ContactInsert
        - kind: attribute
          name: created_by
          of: ContactInsert
          type: string
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
""",
    )
    _write_manifest(
        manifests_dir / "replacement.manifest.yaml",
        """schema: "2"
goal: "Drop owned attribute without accounting for it"
type: fix
supersedes: [original]
files:
  create:
    - path: src/other.ts
      artifacts:
        - kind: function
          name: keep
          args: []
          returns: void
validate:
  - pytest
created: "2026-02-01T00:00:00Z"
""",
    )
    chain = ManifestChain(manifests_dir, project_root=tmp_path)

    errors = SupersessionAuditor(project_root=tmp_path).audit(chain)

    owned = [
        e
        for e in errors
        if e.code == ErrorCode.ARTIFACT_DROPPED_BY_SUPERSESSION
        and "created_by" in e.message
    ]
    assert len(owned) == 1
    assert owned[0].suggestion is not None
    assert "of: ContactInsert" in owned[0].suggestion
