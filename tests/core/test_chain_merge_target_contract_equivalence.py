"""Regression contract for target-file and path equivalence during chain merge."""

from __future__ import annotations

TARGET_SOURCE = """async def alpha(value: str, *, strict: bool = True) -> bytes:
    return value.encode() if strict else b""


def beta() -> int:
    return 2


class Worker:
    state: str | None = None

    async def process(self, value: str) -> bytes:
        return value.encode()


def zulu_new() -> str:
    return "zulu"


def gamma_new() -> str:
    return "gamma"
"""

OLDER_OWNER = """schema: "2"
goal: "older target and private-only path owner"
type: feature
files:
  create:
    - path: src/private_helpers.py
      artifacts:
        - kind: function
          name: _hidden
          args: []
          returns: str
  edit:
    - path: src/target.py
      imports: [legacy.target]
      artifacts:
        - kind: function
          name: beta
          args: []
          returns: int
          description: "stable beta behavior"
  scope:
    - path: docs/operations.md
      reason: "operational behavior remains in the replacement scope"
validate:
  - python -m pytest -q tests/test_target.py
created: "2026-01-01T00:00:00Z"
"""

LATEST_OWNER = """schema: "2"
goal: "complete target contract"
type: feature
files:
  edit:
    - path: src/target.py
      imports: [latest.target]
      artifacts:
        - kind: function
          name: alpha
          args:
            - name: value
              type: str
            - name: strict
              type: bool
              default: "True"
          returns: bytes
          raises: [UnicodeEncodeError]
          async: true
          default_hook: true
          description: "complete alpha behavior"
        - kind: class
          name: Worker
          bases: [Protocol]
          type_parameters: [T]
          description: "complete generic worker"
        - kind: method
          name: process
          of: Worker
          args:
            - name: value
              type: str
          returns: bytes
          raises: [UnicodeEncodeError]
          async: true
          description: "complete worker operation"
        - kind: attribute
          name: state
          of: Worker
          type: str | None
          description: "complete worker state"
    - path: src/private_helpers.py
      artifacts:
        - kind: function
          name: _hidden
          args: []
          returns: str
validate:
  - python -m pytest -q tests/test_alpha.py
created: "2026-02-01T00:00:00Z"
"""

FOLLOWUP_OWNER = """schema: "2"
goal: "target owner after first materialization"
type: feature
files:
  edit:
    - path: src/target.py
      artifacts:
        - kind: function
          name: beta
          args: []
          returns: int
          description: "stable beta behavior"
validate:
  - python -m pytest -q tests/test_followup.py
created: "2027-01-01T00:00:00Z"
"""

TEST_SOURCE = """def test_observable_contract():
    assert True
"""

OLDER_TEST_OWNER = """schema: "2"
goal: "older test owner"
type: feature
files:
  edit:
    - path: tests/test_observable.py
      artifacts:
        - kind: test_function
          name: test_observable_contract
          args: []
          returns: None
          source_scenario: "older scenario"
validate:
  - python -m pytest -q tests/test_observable.py
created: "2026-01-01T00:00:00Z"
"""

LATEST_TEST_OWNER = """schema: "2"
goal: "complete test details"
type: feature
files:
  edit:
    - path: tests/test_observable.py
      artifacts:
        - kind: test_function
          name: test_observable_contract
          args: []
          returns: None
          source_scenario: "complete observable scenario"
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
                function: test_observable_contract
          expected:
            result: accepted
          dependencies:
            environment: isolated
validate:
  - python -m pytest -q tests/test_observable.py
created: "2026-02-01T00:00:00Z"
"""

EXACT_SIGNATURE_OWNER = """schema: "2"
goal: "exact target signature unsupported by structural evidence"
type: feature
files:
  edit:
    - path: src/target.py
      artifacts:
        - kind: function
          name: alpha
          signature: "alpha(System.String)"
          args:
            - name: value
              type: str
          returns: bytes
validate:
  - python -m pytest -q tests/test_exact.py
created: "2026-02-01T00:00:00Z"
"""

OLDER_OVERLOAD_OWNER = """schema: "2"
goal: "older overload owner"
type: feature
files:
  edit:
    - path: src/parser.signed
      artifacts:
        - kind: class
          name: Parser
validate:
  - python -m pytest -q tests/test_parser.py
created: "2026-01-01T00:00:00Z"
"""

LATEST_OVERLOAD_OWNER = """schema: "2"
goal: "exact overload owner"
type: feature
files:
  edit:
    - path: src/parser.signed
      artifacts:
        - kind: method
          name: parse
          of: Parser
          signature: "parse(System.Int32)"
          args:
            - name: value
              type: int
          returns: str
validate:
  - python -m pytest -q tests/test_parser_int.py
created: "2026-02-01T00:00:00Z"
"""


def _signature_artifacts():
    from maid_runner.core.types import ArtifactKind
    from maid_runner.validators.base import FoundArtifact

    int_overload = FoundArtifact(
        kind=ArtifactKind.METHOD,
        name="parse",
        of="Parser",
        signature="parse(System.Int32)",
        args=(),
        returns="str",
    )
    string_overload = FoundArtifact(
        kind=ArtifactKind.METHOD,
        name="parse",
        of="Parser",
        signature="parse(System.String)",
        args=(),
        returns="str",
    )
    return (
        FoundArtifact(kind=ArtifactKind.CLASS, name="Parser"),
        int_overload,
        int_overload,
        string_overload,
        string_overload,
    )


def _signature_registry():
    from maid_runner.validators.base import BaseValidator, CollectionResult
    from maid_runner.validators.registry import ValidatorRegistry

    class _SignatureValidator(BaseValidator):
        @classmethod
        def supported_extensions(cls):
            return (".signed",)

        def collect_implementation_artifacts(self, source, file_path):
            return CollectionResult(
                artifacts=_signature_artifacts(),
                language="signed",
                file_path=str(file_path),
            )

        def collect_behavioral_artifacts(self, source, file_path):
            return CollectionResult(
                artifacts=(),
                language="signed",
                file_path=str(file_path),
            )

    registry = ValidatorRegistry()
    registry.register(_SignatureValidator)
    return registry


def test_apply_preserves_ordered_target_specs_and_private_only_paths(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge_apply import (
        ChainMergeApplyResult,
        apply_chain_merge,
    )
    from maid_runner.core.manifest import load_manifest
    from maid_runner.core.snapshot import generate_snapshot

    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "target.py").write_text(TARGET_SOURCE)
    (source_dir / "private_helpers.py").write_text("def _hidden():\n    return 'x'\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "operations.md").write_text("operations\n")
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    (manifest_dir / "older.manifest.yaml").write_text(OLDER_OWNER)
    (manifest_dir / "latest.manifest.yaml").write_text(LATEST_OWNER)

    before_chain = ManifestChain(manifest_dir)
    assert before_chain.load_errors == []
    before_target = tuple(before_chain.merged_artifacts_for("src/target.py"))
    before_keys = [artifact.contract_key() for artifact in before_target]
    assert before_keys == sorted(before_keys)
    before_paths = before_chain.all_tracked_paths()
    inferred = (
        generate_snapshot(source_dir / "target.py", project_root=str(tmp_path))
        .files_snapshot[0]
        .artifacts
    )
    inferred_new = tuple(
        artifact for artifact in inferred if artifact.name in {"zulu_new", "gamma_new"}
    )
    assert [artifact.name for artifact in inferred_new] == ["zulu_new", "gamma_new"]

    result = apply_chain_merge(
        "src/target.py",
        before_chain,
        project_root=str(tmp_path),
        output_dir=str(manifest_dir),
    )

    assert isinstance(result, ChainMergeApplyResult)
    assert result.applied is True
    assert result.snapshot_path is not None
    replacement = load_manifest(result.snapshot_path)
    target_spec = replacement.file_spec_for("src/target.py")
    assert target_spec is not None
    assert target_spec.artifacts[: len(before_target)] == before_target
    assert target_spec.artifacts[len(before_target) :] == inferred_new
    assert target_spec.imports == ("legacy.target", "latest.target")
    private_spec = replacement.file_spec_for("src/private_helpers.py")
    assert private_spec is None
    private_scope = next(
        spec
        for spec in replacement.files_scope
        if spec.path == "src/private_helpers.py"
    )
    assert private_scope.reason == (
        "Preserve ownership of a private-only writable path during chain merge."
    )
    assert replacement.files_scope[0].path == "docs/operations.md"
    assert replacement.files_scope[0].reason == (
        "operational behavior remains in the replacement scope"
    )

    after_chain = ManifestChain(manifest_dir)
    after_target = tuple(after_chain.merged_artifacts_for("src/target.py"))
    after_keys = [artifact.contract_key() for artifact in after_target]
    assert after_keys == sorted(after_keys)
    assert {artifact.contract_key(): artifact for artifact in after_target} == {
        artifact.contract_key(): artifact for artifact in target_spec.artifacts
    }
    assert before_paths <= after_chain.all_tracked_paths()

    (manifest_dir / "followup.manifest.yaml").write_text(FOLLOWUP_OWNER)
    second_before_chain = ManifestChain(manifest_dir)
    second_before = tuple(second_before_chain.merged_artifacts_for("src/target.py"))
    second_result = apply_chain_merge(
        "src/target.py",
        second_before_chain,
        project_root=str(tmp_path),
        output_dir=str(manifest_dir),
    )
    assert second_result.applied is True
    assert second_result.snapshot_path is not None
    second_replacement = load_manifest(second_result.snapshot_path)
    second_target = second_replacement.file_spec_for("src/target.py")
    assert second_target is not None
    assert second_target.artifacts == second_before
    final_chain = ManifestChain(manifest_dir)
    assert tuple(final_chain.merged_artifacts_for("src/target.py")) == second_before


def test_apply_preserves_complete_target_test_details(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge_apply import apply_chain_merge
    from maid_runner.core.manifest import load_manifest

    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_observable.py").write_text(TEST_SOURCE)
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    (manifest_dir / "older-test.manifest.yaml").write_text(OLDER_TEST_OWNER)
    (manifest_dir / "latest-test.manifest.yaml").write_text(LATEST_TEST_OWNER)

    before_chain = ManifestChain(manifest_dir)
    before = tuple(before_chain.merged_artifacts_for("tests/test_observable.py"))
    assert len(before) == 1
    assert before[0].test_details is not None

    result = apply_chain_merge(
        "tests/test_observable.py",
        before_chain,
        project_root=str(tmp_path),
        output_dir=str(manifest_dir),
    )

    assert result.applied is True
    assert result.snapshot_path is not None
    replacement = load_manifest(result.snapshot_path)
    replacement_spec = replacement.file_spec_for("tests/test_observable.py")
    assert replacement_spec is not None
    assert replacement_spec.artifacts == before
    after_chain = ManifestChain(manifest_dir)
    assert tuple(after_chain.merged_artifacts_for("tests/test_observable.py")) == before


def test_apply_refuses_unmatched_exact_target_signature_atomically(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge_apply import apply_chain_merge

    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "target.py").write_text(TARGET_SOURCE)
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    (manifest_dir / "older.manifest.yaml").write_text(OLDER_OWNER)
    (manifest_dir / "exact.manifest.yaml").write_text(EXACT_SIGNATURE_OWNER)
    before_files = sorted(path.name for path in manifest_dir.iterdir())

    result = apply_chain_merge(
        "src/target.py",
        ManifestChain(manifest_dir),
        project_root=str(tmp_path),
        output_dir=str(manifest_dir),
    )

    assert result.applied is False
    assert result.snapshot_path is None
    assert result.missing_artifacts == (
        "exact:14:function:alpha20:alpha(System.String)",
    )
    assert sorted(path.name for path in manifest_dir.iterdir()) == before_files


def test_apply_appends_distinct_inferred_overloads_once(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge_apply import apply_chain_merge
    from maid_runner.core.manifest import load_manifest
    from maid_runner.core.snapshot import generate_snapshot

    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "parser.signed").write_text("signature-backed implementation\n")
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    (manifest_dir / "older.manifest.yaml").write_text(OLDER_OVERLOAD_OWNER)
    (manifest_dir / "latest.manifest.yaml").write_text(LATEST_OVERLOAD_OWNER)
    before_chain = ManifestChain(manifest_dir)
    before = tuple(before_chain.merged_artifacts_for("src/parser.signed"))
    registry = _signature_registry()
    inferred = (
        generate_snapshot(
            source_dir / "parser.signed",
            project_root=str(tmp_path),
            registry=registry,
        )
        .files_snapshot[0]
        .artifacts
    )
    inferred_string = next(
        artifact
        for artifact in inferred
        if artifact.signature == "parse(System.String)"
    )

    result = apply_chain_merge(
        "src/parser.signed",
        before_chain,
        project_root=str(tmp_path),
        output_dir=str(manifest_dir),
        registry=registry,
    )

    assert result.applied is True
    assert result.snapshot_path is not None
    replacement = load_manifest(result.snapshot_path)
    target_spec = replacement.file_spec_for("src/parser.signed")
    assert target_spec is not None
    assert target_spec.artifacts[: len(before)] == before
    assert [artifact.contract_key() for artifact in target_spec.artifacts] == [
        "class:Parser",
        "exact:19:method:Parser.parse19:parse(System.Int32)",
        "exact:19:method:Parser.parse20:parse(System.String)",
    ]
    assert target_spec.artifacts[len(before) :] == (inferred_string,)
