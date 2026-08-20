"""Behavioral contract for owner-topology-independent artifact ordering."""

from __future__ import annotations


FIRST_OWNER = """schema: "2"
goal: "first owner"
type: feature
files:
  edit:
    - path: src/shared.py
      artifacts:
        - kind: function
          name: zeta
          args: []
          returns: str
        - kind: function
          name: alpha
          args: []
          returns: str
created: "2026-01-01T00:00:00Z"
validate:
  - python -m pytest -q tests/test_shared.py
"""

LATEST_OWNER = """schema: "2"
goal: "latest ordinary owner"
type: feature
files:
  edit:
    - path: src/shared.py
      artifacts:
        - kind: function
          name: alpha
          args:
            - name: value
              type: str
          returns: bytes
        - kind: class
          name: Worker
created: "2026-02-01T00:00:00Z"
validate:
  - python -m pytest -q tests/test_latest.py
"""

EXACT_OWNER = """schema: "2"
goal: "exact overload owner"
type: feature
files:
  edit:
    - path: src/parser.signed
      artifacts:
        - kind: method
          name: parse
          of: Parser
          signature: "parse(System.String)"
        - kind: method
          name: parse
          of: Parser
          signature: "parse(System.Int32)"
created: "2026-01-01T00:00:00Z"
validate:
  - python -m pytest -q tests/test_parser.py
"""

TARGET_SOURCE = """def target_alpha():
    return 1


def target_beta():
    return 2
"""

TARGET_OWNER_A = """schema: "2"
goal: "target owner A"
type: feature
files:
  edit:
    - path: src/target.py
      artifacts:
        - kind: function
          name: target_alpha
          args: []
          returns: int
    - path: src/shared.py
      artifacts:
        - kind: function
          name: zeta
          args: []
          returns: str
        - kind: function
          name: alpha
          args: []
          returns: str
created: "2026-01-01T00:00:00Z"
validate:
  - python -m pytest -q tests/test_a.py
"""

SURVIVING_SHARED_OWNER = """schema: "2"
goal: "surviving overlapping owner"
type: feature
files:
  edit:
    - path: src/shared.py
      artifacts:
        - kind: function
          name: omega
          args: []
          returns: str
        - kind: function
          name: alpha
          args:
            - name: value
              type: str
          returns: bytes
created: "2026-01-15T00:00:00Z"
validate:
  - python -m pytest -q tests/test_survivor.py
"""

TARGET_OWNER_B = """schema: "2"
goal: "target owner B"
type: feature
files:
  edit:
    - path: src/target.py
      artifacts:
        - kind: function
          name: target_beta
          args: []
          returns: int
    - path: src/shared.py
      artifacts:
        - kind: function
          name: beta
          args: []
          returns: str
created: "2026-02-01T00:00:00Z"
validate:
  - python -m pytest -q tests/test_b.py
"""


def test_merged_artifacts_use_canonical_contract_key_order(tmp_path):
    from maid_runner.core.chain import ManifestChain

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    (manifest_dir / "first.manifest.yaml").write_text(FIRST_OWNER)
    (manifest_dir / "latest.manifest.yaml").write_text(LATEST_OWNER)

    merged = ManifestChain(manifest_dir).merged_artifacts_for("src/shared.py")

    keys = [artifact.contract_key() for artifact in merged]
    assert keys == sorted(keys)
    alpha = next(artifact for artifact in merged if artifact.name == "alpha")
    assert alpha.returns == "bytes"
    assert [argument.name for argument in alpha.args] == ["value"]


def test_merged_exact_overloads_use_canonical_contract_key_order(tmp_path):
    from maid_runner.core.chain import ManifestChain

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    (manifest_dir / "exact.manifest.yaml").write_text(EXACT_OWNER)

    merged = ManifestChain(manifest_dir).merged_artifacts_for("src/parser.signed")

    keys = [artifact.contract_key() for artifact in merged]
    assert keys == sorted(keys)
    assert {artifact.signature for artifact in merged} == {
        "parse(System.Int32)",
        "parse(System.String)",
    }


def test_apply_keeps_canonical_order_with_surviving_overlapping_owner(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge_apply import apply_chain_merge

    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "target.py").write_text(TARGET_SOURCE)
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    (manifest_dir / "target-a.manifest.yaml").write_text(TARGET_OWNER_A)
    (manifest_dir / "survivor.manifest.yaml").write_text(SURVIVING_SHARED_OWNER)
    (manifest_dir / "target-b.manifest.yaml").write_text(TARGET_OWNER_B)
    before_chain = ManifestChain(manifest_dir)
    before = {
        artifact.contract_key(): artifact
        for artifact in before_chain.merged_artifacts_for("src/shared.py")
    }

    result = apply_chain_merge(
        "src/target.py",
        before_chain,
        project_root=str(tmp_path),
        output_dir=str(manifest_dir),
    )

    assert result.applied is True
    after = ManifestChain(manifest_dir).merged_artifacts_for("src/shared.py")
    assert {artifact.contract_key(): artifact for artifact in after} == before
    after_keys = [artifact.contract_key() for artifact in after]
    assert after_keys == sorted(after_keys)
