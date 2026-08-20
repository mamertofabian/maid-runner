"""Behavioral tests for maid_runner.core.chain_merge_apply (chain-merge child 4).

The SUT is imported inside each test body. These exercise the real snapshot
primitive, so they write actual source files into a temp project.
"""

from __future__ import annotations

from pathlib import Path

CODE_FULL = "def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n\n\ndef gamma():\n    return 3\n"
CODE_WITH_UNDECLARED_PUBLIC = CODE_FULL + "\n\ndef delta():\n    return 4\n"
CODE_MISSING_GAMMA = "def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n"

FRAG_A = """schema: "2"
goal: "frag a"
type: feature
files:
  create:
    - path: src/foo.py
      artifacts:
        - kind: function
          name: alpha
        - kind: function
          name: beta
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
"""

FRAG_B = """schema: "2"
goal: "frag b"
type: feature
files:
  edit:
    - path: src/foo.py
      artifacts:
        - kind: function
          name: beta
        - kind: function
          name: gamma
validate:
  - pytest
created: "2026-02-01T00:00:00Z"
"""

FRAG_C = """schema: "2"
goal: "frag c after snapshot"
type: feature
files:
  edit:
    - path: src/foo.py
      artifacts:
        - kind: function
          name: alpha
validate:
  - pytest tests/test_frag_c.py
created: "2026-03-01T00:00:00Z"
"""

SINGLE = """schema: "2"
goal: "single"
type: feature
files:
  create:
    - path: src/foo.py
      artifacts:
        - kind: function
          name: alpha
        - kind: function
          name: beta
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
"""


# frag-a declares artifacts in TWO files: src/foo.py and src/bar.py.
FRAG_A_MULTI = """schema: "2"
goal: "frag a multi"
type: feature
files:
  create:
    - path: src/foo.py
      artifacts:
        - kind: function
          name: alpha
        - kind: function
          name: beta
    - path: src/bar.py
      imports: [typing.Iterable, collections.abc.Sequence]
      artifacts:
        - kind: function
          name: zeta
          args:
            - name: value
              type: int
              default: "1"
          returns: int
          raises: [ValueError]
        - kind: function
          name: _private_bar
          args: []
          returns: int
  snapshot:
    - path: src/snap.py
      imports: [typing.Mapping]
      artifacts:
        - kind: function
          name: theta
          args: []
          returns: int
acceptance:
  tests:
    - python -m pytest -q tests/acceptance/test_shared.py
  immutable: false
removed_artifacts:
  - kind: function
    name: retired_bar
    file: src/bar.py
    reason: removed by frag a
validate:
  - python -m pytest -q tests/test_frag_a.py
  - python -m pytest -q tests/test_shared.py
created: "2026-01-01T00:00:00Z"
"""

FRAG_B_MULTI = """schema: "2"
goal: "frag b multi"
type: feature
files:
  edit:
    - path: src/foo.py
      imports: [typing.Callable]
      artifacts:
        - kind: function
          name: beta
        - kind: function
          name: gamma
    - path: src/bar.py
      imports: [collections.abc.Sequence, pathlib.Path]
      artifacts:
        - kind: function
          name: zeta
          args:
            - name: value
              type: int
              default: "1"
          returns: int
          raises: [ValueError]
        - kind: function
          name: eta
          args: []
          returns: str
    - path: src/snap.py
      imports: [typing.Mapping, typing.Sequence]
      artifacts:
        - kind: function
          name: theta
          args: []
          returns: int
        - kind: function
          name: iota
          args: []
          returns: str
acceptance:
  tests:
    - python -m pytest -q tests/acceptance/test_shared.py
    - python -m pytest -q tests/acceptance/test_frag_b.py
  immutable: true
removed_artifacts:
  - kind: function
    name: retired_bar
    file: src/bar.py
    reason: duplicate reason loses
  - kind: function
    name: retired_other
    file: src/bar.py
    reason: removed by frag b
validate:
  - python -m pytest -q tests/test_shared.py
  - python -m pytest -q tests/test_frag_b.py
created: "2026-02-01T00:00:00Z"
"""

FRAG_WITH_NONARTIFACT_PATHS = """schema: "2"
goal: "frag with nonartifact paths"
type: feature
files:
  edit:
    - path: src/foo.py
      artifacts:
        - kind: function
          name: alpha
  scope:
    - path: config/runtime.toml
      reason: preserve runtime wiring
    - path: config/shared.toml
      reason: first scope reason
    - path: docs/scope-wins.md
      reason: scope outranks read
    - path: src/bar.py
      reason: artifact outranks scope
    - path: src/retired.py
      reason: delete outranks scope
  read:
    - docs/runtime.md
    - docs/runtime.md
    - docs/scope-wins.md
    - src/bar.py
    - src/retired.py
  delete:
    - path: src/retired.py
      reason: retired by the original owner
validate:
  - python -m pytest -q tests/test_scope.py
created: "2026-01-15T00:00:00Z"
"""

FRAG_WITH_OVERLAPPING_PATHS = """schema: "2"
goal: "overlapping nonartifact paths"
type: feature
files:
  edit:
    - path: src/foo.py
      artifacts:
        - kind: function
          name: beta
    - path: src/bar.py
      artifacts:
        - kind: function
          name: path_owned_bar
  scope:
    - path: config/runtime.toml
      reason: later duplicate reason
    - path: config/shared.toml
      reason: later shared reason
  read:
    - docs/runtime.md
    - docs/other.md
validate:
  - python -m pytest -q tests/test_scope.py
created: "2026-01-20T00:00:00Z"
"""

FRAG_ARTIFACT_DELETE_CONFLICT = """schema: "2"
goal: "conflicting path intent"
type: feature
files:
  edit:
    - path: src/foo.py
      artifacts:
        - kind: function
          name: gamma
  delete:
    - path: src/bar.py
      reason: conflicts with another owner's live contract
validate:
  - pytest
created: "2026-03-01T00:00:00Z"
"""

TSX_A = """schema: "2"
goal: "tsx a"
type: feature
files:
  create:
    - path: src/Card.tsx
      artifacts:
        - kind: function
          name: Card
validate:
  - pytest tests/test_card_a.py
created: "2026-01-01T00:00:00Z"
"""

TSX_B = """schema: "2"
goal: "tsx b"
type: feature
files:
  edit:
    - path: src/Card.tsx
      artifacts:
        - kind: function
          name: Card
validate:
  - pytest tests/test_card_b.py
created: "2026-02-01T00:00:00Z"
"""

FRAG_PRIVATE_A = """schema: "2"
goal: "legacy private a"
type: feature
files:
  edit:
    - path: src/foo.py
      artifacts:
        - kind: function
          name: alpha
        - kind: function
          name: _legacy_helper
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
"""

FRAG_PRIVATE_B = """schema: "2"
goal: "legacy private b"
type: feature
files:
  edit:
    - path: src/foo.py
      artifacts:
        - kind: function
          name: alpha
validate:
  - pytest
created: "2026-02-01T00:00:00Z"
"""


def _project(tmp_path, code, manifests):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text(code)
    md = tmp_path / "manifests"
    md.mkdir()
    for name, content in manifests.items():
        (md / name).write_text(content)
    return md


def test_apply_writes_snapshot_superseding_chain(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge_apply import (
        ChainMergeApplyResult,
        apply_chain_merge,
    )

    md = _project(
        tmp_path,
        CODE_FULL,
        {"frag-a.manifest.yaml": FRAG_A, "frag-b.manifest.yaml": FRAG_B},
    )
    chain = ManifestChain(md)
    expected_slugs = {m.slug for m in chain.manifests_for_file("src/foo.py")}

    result = apply_chain_merge(
        "src/foo.py", chain, project_root=str(tmp_path), output_dir=str(md)
    )

    assert isinstance(result, ChainMergeApplyResult)
    assert result.applied is True
    assert result.snapshot_path is not None
    assert Path(result.snapshot_path).exists()
    assert set(result.superseded_slugs) == expected_slugs
    assert "supersedes" in Path(result.snapshot_path).read_text()


def test_apply_refuses_when_snapshot_drops_declared_artifact(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge_apply import apply_chain_merge

    md = _project(
        tmp_path,
        CODE_MISSING_GAMMA,
        {"frag-a.manifest.yaml": FRAG_A, "frag-b.manifest.yaml": FRAG_B},
    )
    chain = ManifestChain(md)
    before = sorted(p.name for p in md.iterdir())

    result = apply_chain_merge(
        "src/foo.py", chain, project_root=str(tmp_path), output_dir=str(md)
    )

    assert result.applied is False
    assert result.missing_artifacts
    assert result.snapshot_path is None
    assert sorted(p.name for p in md.iterdir()) == before


def test_apply_refuses_lean_file(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge_apply import apply_chain_merge

    md = _project(tmp_path, CODE_MISSING_GAMMA, {"single.manifest.yaml": SINGLE})
    chain = ManifestChain(md)

    result = apply_chain_merge(
        "src/foo.py", chain, project_root=str(tmp_path), output_dir=str(md)
    )

    assert result.applied is False
    assert result.refused_reason is not None
    assert "lean" in result.refused_reason.lower()


def test_apply_leaves_source_unchanged(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge_apply import apply_chain_merge

    md = _project(
        tmp_path,
        CODE_FULL,
        {"frag-a.manifest.yaml": FRAG_A, "frag-b.manifest.yaml": FRAG_B},
    )
    src = tmp_path / "src" / "foo.py"
    before = src.read_bytes()
    chain = ManifestChain(md)

    apply_chain_merge(
        "src/foo.py", chain, project_root=str(tmp_path), output_dir=str(md)
    )

    assert src.read_bytes() == before


def test_apply_repeatedly_uses_noncolliding_snapshot_slug(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge_apply import apply_chain_merge
    from maid_runner.core.manifest import load_manifest

    md = _project(
        tmp_path,
        CODE_FULL,
        {"frag-a.manifest.yaml": FRAG_A, "frag-b.manifest.yaml": FRAG_B},
    )
    first = apply_chain_merge(
        "src/foo.py",
        ManifestChain(md),
        project_root=str(tmp_path),
        output_dir=str(md),
    )
    assert first.applied is True
    first_path = Path(first.snapshot_path)
    first_bytes = first_path.read_bytes()
    (md / "frag-c.manifest.yaml").write_text(FRAG_C)

    second = apply_chain_merge(
        "src/foo.py",
        ManifestChain(md),
        project_root=str(tmp_path),
        output_dir=str(md),
    )

    assert second.applied is True
    assert Path(second.snapshot_path) != first_path
    assert first_path.read_bytes() == first_bytes
    assert load_manifest(second.snapshot_path).slug not in second.superseded_slugs
    refreshed = ManifestChain(md, project_root=tmp_path)
    assert refreshed.validate_supersession_integrity() == []
    assert refreshed.audit_supersession_artifacts() == []
    assert [
        artifact.contract_key()
        for artifact in refreshed.merged_artifacts_for("src/foo.py")
    ] == ["function:alpha", "function:beta", "function:gamma"]


def test_apply_preserves_multi_file_contract_and_validation_union(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge_apply import apply_chain_merge
    from maid_runner.core.manifest import load_manifest

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text(CODE_WITH_UNDECLARED_PUBLIC)
    (tmp_path / "src" / "bar.py").write_text(
        "def zeta(value: int = 1) -> int:\n"
        "    if value < 0:\n"
        "        raise ValueError(value)\n"
        "    return value\n\n"
        "def _private_bar() -> int:\n"
        "    return 8\n\n"
        "def eta() -> str:\n"
        "    return 'eta'\n"
    )
    (tmp_path / "src" / "snap.py").write_text(
        "def theta() -> int:\n    return 1\n\n"
        "def iota() -> str:\n    return 'iota'\n"
    )
    md = tmp_path / "manifests"
    md.mkdir()
    (md / "frag-a.manifest.yaml").write_text(FRAG_A_MULTI)
    (md / "frag-b.manifest.yaml").write_text(FRAG_B_MULTI)
    chain = ManifestChain(md)
    result = apply_chain_merge(
        "src/foo.py", chain, project_root=str(tmp_path), output_dir=str(md)
    )

    assert result.applied is True
    replacement = load_manifest(result.snapshot_path)
    assert [artifact.name for artifact in replacement.artifacts_for("src/foo.py")] == [
        "alpha",
        "beta",
        "gamma",
        "delta",
    ]
    bar_artifacts = replacement.artifacts_for("src/bar.py")
    assert [artifact.contract_key() for artifact in bar_artifacts] == [
        "function:eta",
        "function:zeta",
    ]
    assert bar_artifacts[0].args == ()
    assert bar_artifacts[0].returns == "str"
    assert bar_artifacts[1].args[0].name == "value"
    assert bar_artifacts[1].args[0].type == "int"
    assert bar_artifacts[1].args[0].default == "1"
    assert bar_artifacts[1].returns == "int"
    assert bar_artifacts[1].raises == ("ValueError",)
    assert [spec.path for spec in replacement.files_create] == ["src/bar.py"]
    assert [spec.path for spec in replacement.files_snapshot] == [
        "src/foo.py",
        "src/snap.py",
    ]
    bar_spec = replacement.file_spec_for("src/bar.py")
    assert bar_spec is not None
    assert bar_spec.imports == (
        "typing.Iterable",
        "collections.abc.Sequence",
        "pathlib.Path",
    )
    snap_spec = replacement.file_spec_for("src/snap.py")
    assert snap_spec is not None
    assert [artifact.contract_key() for artifact in snap_spec.artifacts] == [
        "function:iota",
        "function:theta",
    ]
    assert snap_spec.imports == ("typing.Mapping", "typing.Sequence")
    assert replacement.validate_commands == (
        ("python", "-m", "pytest", "-q", "tests/test_frag_a.py"),
        ("python", "-m", "pytest", "-q", "tests/test_shared.py"),
        ("python", "-m", "pytest", "-q", "tests/test_frag_b.py"),
    )
    assert replacement.acceptance is not None
    assert replacement.acceptance.tests == (
        ("python", "-m", "pytest", "-q", "tests/acceptance/test_shared.py"),
        ("python", "-m", "pytest", "-q", "tests/acceptance/test_frag_b.py"),
    )
    assert replacement.acceptance.immutable is True
    assert [
        (removed.file, removed.kind.value, removed.name, removed.reason)
        for removed in replacement.removed_artifacts
    ] == [
        ("src/bar.py", "function", "retired_bar", "removed by frag a"),
        ("src/bar.py", "function", "retired_other", "removed by frag b"),
    ]

    refreshed = ManifestChain(md, project_root=tmp_path)
    assert [
        artifact.contract_key()
        for artifact in refreshed.merged_artifacts_for("src/bar.py")
    ] == ["function:eta", "function:zeta"]
    assert refreshed.audit_supersession_artifacts() == []


def test_apply_omits_legacy_private_artifacts(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge_apply import apply_chain_merge
    from maid_runner.core.manifest import load_manifest

    code = "def alpha():\n    return 1\n\n\ndef _legacy_helper():\n    return 2\n"
    md = _project(
        tmp_path,
        code,
        {
            "private-a.manifest.yaml": FRAG_PRIVATE_A,
            "private-b.manifest.yaml": FRAG_PRIVATE_B,
        },
    )

    result = apply_chain_merge(
        "src/foo.py",
        ManifestChain(md),
        project_root=str(tmp_path),
        output_dir=str(md),
    )

    assert result.applied is True
    replacement = load_manifest(result.snapshot_path)
    assert [artifact.name for artifact in replacement.artifacts_for("src/foo.py")] == [
        "alpha"
    ]
    refreshed = ManifestChain(md, project_root=tmp_path)
    assert refreshed.audit_supersession_artifacts() == []


def test_apply_preserves_scope_read_and_delete_paths(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge_apply import apply_chain_merge
    from maid_runner.core.manifest import load_manifest

    md = _project(
        tmp_path,
        CODE_FULL,
        {
            "paths.manifest.yaml": FRAG_WITH_NONARTIFACT_PATHS,
            "overlaps.manifest.yaml": FRAG_WITH_OVERLAPPING_PATHS,
        },
    )

    result = apply_chain_merge(
        "src/foo.py",
        ManifestChain(md),
        project_root=str(tmp_path),
        output_dir=str(md),
    )

    assert result.applied is True
    replacement = load_manifest(result.snapshot_path)
    assert replacement.files_read == ("docs/runtime.md", "docs/other.md")
    assert [(scope.path, scope.reason) for scope in replacement.files_scope] == [
        ("config/runtime.toml", "preserve runtime wiring"),
        ("config/shared.toml", "first scope reason"),
        ("docs/scope-wins.md", "scope outranks read"),
    ]
    assert [(deleted.path, deleted.reason) for deleted in replacement.files_delete] == [
        ("src/retired.py", "retired by the original owner")
    ]
    assert replacement.validate_commands == (
        ("python", "-m", "pytest", "-q", "tests/test_scope.py"),
    )


def test_apply_keeps_snapshot_inferred_companion_reads(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge_apply import apply_chain_merge
    from maid_runner.core.manifest import load_manifest

    src = tmp_path / "src"
    src.mkdir()
    (src / "Card.tsx").write_text(
        "import './Card.css';\n\n"
        "export function Card(): JSX.Element {\n"
        "  return <section />;\n"
        "}\n"
    )
    (src / "Card.css").write_text("section { display: block; }\n")
    md = tmp_path / "manifests"
    md.mkdir()
    (md / "tsx-a.manifest.yaml").write_text(TSX_A)
    (md / "tsx-b.manifest.yaml").write_text(TSX_B)

    result = apply_chain_merge(
        "src/Card.tsx",
        ManifestChain(md),
        project_root=str(tmp_path),
        output_dir=str(md),
    )

    assert result.applied is True
    replacement = load_manifest(result.snapshot_path)
    assert replacement.files_read == ("src/Card.css",)


def test_apply_refuses_artifact_delete_path_conflict_atomically(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge_apply import apply_chain_merge

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text(CODE_FULL)
    (tmp_path / "src" / "bar.py").write_text(
        "def zeta(value: int = 1) -> int:\n    return value\n"
    )
    md = tmp_path / "manifests"
    md.mkdir()
    (md / "multi.manifest.yaml").write_text(FRAG_A_MULTI)
    (md / "conflict.manifest.yaml").write_text(FRAG_ARTIFACT_DELETE_CONFLICT)
    before = sorted(path.name for path in md.iterdir())

    result = apply_chain_merge(
        "src/foo.py",
        ManifestChain(md),
        project_root=str(tmp_path),
        output_dir=str(md),
    )

    assert result.applied is False
    assert result.snapshot_path is None
    assert result.refused_reason is not None
    assert "src/bar.py" in result.refused_reason
    assert "delete" in result.refused_reason.lower()
    assert sorted(path.name for path in md.iterdir()) == before
