"""Behavioral tests for maid_runner.core.chain_merge_apply (chain-merge child 4).

The SUT is imported inside each test body. These exercise the real snapshot
primitive, so they write actual source files into a temp project.
"""

from __future__ import annotations

from pathlib import Path

CODE_FULL = "def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n\n\ndef gamma():\n    return 3\n"
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
      artifacts:
        - kind: function
          name: zeta
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
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


def test_apply_refuses_multi_file_supersession(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge_apply import apply_chain_merge

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text(CODE_FULL)
    (tmp_path / "src" / "bar.py").write_text("def zeta():\n    return 9\n")
    md = tmp_path / "manifests"
    md.mkdir()
    (md / "frag-a.manifest.yaml").write_text(FRAG_A_MULTI)
    (md / "frag-b.manifest.yaml").write_text(FRAG_B)
    chain = ManifestChain(md)
    before = sorted(p.name for p in md.iterdir())

    result = apply_chain_merge(
        "src/foo.py", chain, project_root=str(tmp_path), output_dir=str(md)
    )

    # frag-a also declares src/bar.py:zeta, which a src/foo.py snapshot cannot
    # preserve, so apply must refuse rather than drop it.
    assert result.applied is False
    assert result.refused_reason is not None
    assert "frag-a" in result.refused_reason
    assert sorted(p.name for p in md.iterdir()) == before
