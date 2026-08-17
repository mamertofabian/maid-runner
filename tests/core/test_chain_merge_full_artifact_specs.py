"""Regression contract for full carried ArtifactSpec preservation."""

from __future__ import annotations

from pathlib import Path


TARGET_SOURCE = """def alpha():
    return 1


def beta():
    return 2
"""

OLDER_MULTI_FILE_OWNER = """schema: "2"
goal: "older multi-file owner"
type: feature
files:
  edit:
    - path: src/target.py
      artifacts:
        - kind: function
          name: alpha
          args: []
          returns: int
    - path: src/service.py
      artifacts:
        - kind: function
          name: zeta
          signature: "(value, options=None)"
          args:
            - name: value
              type: int
          returns: int
          description: "older partial zeta contract"
        - kind: function
          name: eta
          args: []
          returns: int
        - kind: function
          name: omega
          args: []
          returns: bool
          description: "superseded-owner-only artifact"
        - kind: class
          name: Worker
          bases: [LegacyBase]
        - kind: method
          name: process
          of: Worker
          args:
            - name: value
              type: int
          returns: int
        - kind: attribute
          name: state
          of: Worker
          type: int
    - path: tests/test_service.py
      artifacts:
        - kind: test_function
          name: test_process
          args: []
          returns: None
          source_scenario: "older scenario"
          tags: [legacy]
validate:
  - python -m pytest -q tests/test_old.py
created: "2026-01-01T00:00:00Z"
"""

SECOND_TARGET_OWNER = """schema: "2"
goal: "second target owner"
type: feature
files:
  edit:
    - path: src/target.py
      artifacts:
        - kind: function
          name: beta
          args: []
          returns: int
validate:
  - python -m pytest -q tests/test_target.py
created: "2026-02-01T00:00:00Z"
"""

LATEST_UNRELATED_OWNER = """schema: "2"
goal: "latest complete unrelated contracts"
type: feature
files:
  edit:
    - path: src/service.py
      artifacts:
        - kind: function
          name: zeta
          signature: "(value, options=None)"
          args:
            - name: value
              type: str
            - name: options
              type: Mapping[str, bool] | None
              default: "None"
          returns: str
          raises: [TypeError, ValueError]
          async: true
          default_hook: true
          description: "latest complete zeta contract"
        - kind: function
          name: eta
          args:
            - name: token
              type: str
          returns: bytes
          raises: [LookupError]
          description: "latest complete eta contract"
        - kind: class
          name: Worker
          bases: [CurrentBase, Protocol]
          type_parameters: [T]
          description: "latest generic worker contract"
        - kind: method
          name: process
          of: Worker
          args:
            - name: value
              type: str
            - name: strict
              type: bool
              default: "True"
          returns: bytes
          raises: [RuntimeError]
          async: true
          description: "latest worker operation"
        - kind: attribute
          name: state
          of: Worker
          type: str | None
          description: "latest worker state"
    - path: tests/test_service.py
      artifacts:
        - kind: test_function
          name: test_process
          args: []
          returns: None
          source_scenario: "latest observable scenario"
          tags: [contract, regression]
          setup:
            auth_required: true
            test_data:
              account: primary
            setup_actions:
              - type: seed
                target: account
          actions:
            - type: api_call
              subject:
                module: src/service.py
                export: zeta
              method: POST
              endpoint: /zeta
          expected:
            result: canonical
          dependencies:
            environment: isolated
validate:
  - python -m pytest -q tests/test_latest.py
created: "2026-03-01T00:00:00Z"
"""

THIRD_TARGET_OWNER = """schema: "2"
goal: "target change after first materialization"
type: feature
files:
  edit:
    - path: src/target.py
      artifacts:
        - kind: function
          name: alpha
          args: []
          returns: int
validate:
  - python -m pytest -q tests/test_target_followup.py
created: "2027-01-01T00:00:00Z"
"""


def test_apply_preserves_latest_complete_specs_for_every_carried_artifact(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge_apply import (
        ChainMergeApplyResult,
        apply_chain_merge,
    )

    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "target.py").write_text(TARGET_SOURCE)
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    (manifest_dir / "older.manifest.yaml").write_text(OLDER_MULTI_FILE_OWNER)
    (manifest_dir / "target.manifest.yaml").write_text(SECOND_TARGET_OWNER)
    (manifest_dir / "latest.manifest.yaml").write_text(LATEST_UNRELATED_OWNER)

    before_chain = ManifestChain(manifest_dir)
    assert before_chain.load_errors == []
    before = {
        path: tuple(before_chain.merged_artifacts_for(path))
        for path in ("src/service.py", "tests/test_service.py")
    }
    assert [artifact.name for artifact in before["src/service.py"]] == [
        "state",
        "Worker",
        "zeta",
        "eta",
        "omega",
        "process",
    ]

    result = apply_chain_merge(
        "src/target.py",
        before_chain,
        project_root=str(tmp_path),
        output_dir=str(manifest_dir),
    )

    assert isinstance(result, ChainMergeApplyResult)
    assert result.applied is True
    assert result.snapshot_path is not None
    assert Path(result.snapshot_path).exists()
    assert result.refused_reason is None
    assert result.missing_artifacts == ()

    from maid_runner.core.manifest import load_manifest

    replacement = load_manifest(result.snapshot_path)
    for path, expected in before.items():
        replacement_spec = replacement.file_spec_for(path)
        assert replacement_spec is not None
        assert replacement_spec.artifacts == expected

    after_chain = ManifestChain(manifest_dir)
    after = {
        path: {
            artifact.contract_key(): artifact
            for artifact in after_chain.merged_artifacts_for(path)
        }
        for path in ("src/service.py", "tests/test_service.py")
    }
    expected_by_key = {
        path: {artifact.contract_key(): artifact for artifact in artifacts}
        for path, artifacts in before.items()
    }
    assert after == expected_by_key
    assert after_chain.audit_supersession_artifacts() == []

    (manifest_dir / "target-followup.manifest.yaml").write_text(THIRD_TARGET_OWNER)
    second_before_chain = ManifestChain(manifest_dir)
    second_before = {
        path: tuple(second_before_chain.merged_artifacts_for(path))
        for path in ("src/service.py", "tests/test_service.py")
    }
    second = apply_chain_merge(
        "src/target.py",
        second_before_chain,
        project_root=str(tmp_path),
        output_dir=str(manifest_dir),
    )
    assert second.applied is True
    assert second.snapshot_path is not None
    second_replacement = load_manifest(second.snapshot_path)
    for path, expected in second_before.items():
        replacement_spec = second_replacement.file_spec_for(path)
        assert replacement_spec is not None
        assert replacement_spec.artifacts == expected

    final_chain = ManifestChain(manifest_dir)
    assert {
        path: {
            artifact.contract_key(): artifact
            for artifact in final_chain.merged_artifacts_for(path)
        }
        for path in ("src/service.py", "tests/test_service.py")
    } == expected_by_key
    assert final_chain.audit_supersession_artifacts() == []
