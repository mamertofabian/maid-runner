"""Behavioral contract for artifact coverage evaluated from runtime evidence."""

from __future__ import annotations

from dataclasses import replace
from functools import partial
from pathlib import Path
from types import SimpleNamespace

from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode


def _write_project(root: Path):
    for directory in ("src", "tests", "manifests"):
        (root / directory).mkdir()
    (root / "src" / "__init__.py").write_text("")
    manifests = []
    for name in ("alpha", "beta"):
        (root / "src" / f"{name}.py").write_text(
            f"def {name}() -> str:\n    return '{name}'\n"
        )
        (root / "tests" / f"test_{name}.py").write_text(
            f"from src.{name} import {name}\n\n"
            f"def test_{name}():\n    assert {name}() == '{name}'\n"
        )
        manifest_path = root / "manifests" / f"{name}.manifest.yaml"
        manifest_path.write_text(
            f"""schema: "2"
goal: "Cover {name}"
type: feature
created: "2026-08-11T00:00:00Z"
files:
  edit:
    - path: src/{name}.py
      artifacts:
        - kind: function
          name: {name}
          args: []
          returns: str
  read:
    - tests/test_{name}.py
validate:
  - python -m pytest -q tests/test_{name}.py
"""
        )
        manifests.append(load_manifest(manifest_path))
    return manifests


def _record(root: Path, command, executed=(), *, returncode=0, output=""):
    from maid_runner.core._runtime_command_executor import (
        RuntimeCommandRecord,
        RuntimeFileExecution,
    )

    execution = {
        str((root / "src" / f"{name}.py").resolve()): RuntimeFileExecution(
            executed_lines=frozenset({2}),
            called_qualnames=frozenset({name}),
        )
        for name in executed
    }
    return RuntimeCommandRecord(
        command=tuple(command),
        returncode=returncode,
        stdout=output,
        stderr="",
        execution_data=execution,
        report_errors=(),
    )


class _GroupExecutor:
    def __init__(self, root: Path, executed=("alpha", "beta")):
        self.root = root
        self.executed = set(executed)
        self.calls = []

    def execute_with_contexts(
        self,
        command,
        target_files,
        project_root,
        timeout_seconds,
        pytest_workers=None,
    ):
        from maid_runner.core.runtime_evidence import (
            RuntimeContextEvidence,
            RuntimeEvidenceCompleteness,
            RuntimeGroupEvidence,
        )

        self.calls.append(tuple(command))
        selectors = {
            f"tests/test_{name}.py": (f"tests/test_{name}.py::test_{name}",)
            for name in ("alpha", "beta")
        }
        contexts = []
        for name in self.executed:
            nodeid = selectors[f"tests/test_{name}.py"]
            contexts.append(
                RuntimeContextEvidence(
                    context_id=f"node:{nodeid[0]}",
                    kind="node",
                    consuming_nodeids=nodeid,
                    execution_data=_record(self.root, (), (name,)).execution_data,
                    lifecycle_equivalent=True,
                )
            )
        return RuntimeGroupEvidence(
            command=tuple(command),
            selected_nodeids=tuple(
                node for values in selectors.values() for node in values
            ),
            selector_nodeids=selectors,
            contexts=tuple(contexts),
            result=_record(self.root, command, self.executed),
            worker_ids=("main",),
            completeness=RuntimeEvidenceCompleteness(complete=True),
        )


class _ExactExecutor:
    def __init__(self, root: Path, *, failures=(), missing=()):
        self.root = root
        self.failures = set(failures)
        self.missing = set(missing)
        self.calls = []

    def execute(self, command, target_files, project_root, timeout_seconds):
        self.calls.append(tuple(command))
        name = "alpha" if "tests/test_alpha.py" in command else "beta"
        failed = name in self.failures
        output = (
            f"tests/test_{name}.py::test_{name} FAILED\n"
            f"1 failed in {0.01 + len(self.calls) / 100:.2f}s\n"
            if failed
            else ""
        )
        return _record(
            self.root,
            command,
            () if name in self.missing else (name,),
            returncode=1 if failed else 0,
            output=output,
        )


def _bundle(root: Path, manifests, *, executed=("alpha", "beta")):
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    executor = _GroupExecutor(root, executed)
    bundle = collect_runtime_evidence(manifests, root, executor=executor).evidence
    return bundle, executor


def _legacy(root: Path, manifests, executor=None):
    from maid_runner.core.artifact_coverage import run_artifact_coverage_batch

    return run_artifact_coverage_batch(manifests, root, executor=executor)


def _incomplete(command, **fields):
    from maid_runner.core.runtime_evidence import RuntimeEvidenceCompleteness

    values = {
        "complete": False,
        "missing_worker_ids": (),
        "unsupported_selectors": (),
        "unresolved_context_ids": (),
        "unproven_fixture_lifecycles": (),
        "diagnostics": (),
    }
    values.update(fields)
    return replace(command, completeness=RuntimeEvidenceCompleteness(**values))


def test_evidence_report_matches_legacy_honest_and_missing_artifacts(tmp_path):
    from maid_runner.core.artifact_coverage import (
        EvidenceArtifactCoverageResult,
        evaluate_artifact_coverage_from_evidence,
    )

    manifests = _write_project(tmp_path)
    evidence, _ = _bundle(tmp_path, manifests, executed=("alpha",))
    fallback = _ExactExecutor(tmp_path)

    result = evaluate_artifact_coverage_from_evidence(
        manifests, tmp_path, evidence, fallback_executor=fallback
    )
    legacy = _legacy(tmp_path, manifests, _ExactExecutor(tmp_path, missing=("beta",)))

    assert isinstance(result, EvidenceArtifactCoverageResult)
    assert {path: report.to_dict() for path, report in result.reports.items()} == {
        path: report.to_dict() for path, report in legacy.items()
    }
    assert result.fallback_identities == ()
    assert result.complete is True
    assert fallback.calls == []


def test_unrelated_ambient_context_cannot_satisfy_e710(tmp_path):
    from maid_runner.core._runtime_command_executor import RuntimeFileExecution
    from maid_runner.core.artifact_coverage import (
        evaluate_artifact_coverage_from_evidence,
    )
    from maid_runner.core.runtime_evidence import RuntimeContextEvidence

    manifests = _write_project(tmp_path)
    evidence, _ = _bundle(tmp_path, manifests)
    alpha, beta = evidence.commands
    ambient = RuntimeContextEvidence(
        context_id="node:tests/test_beta.py::test_beta",
        kind="node",
        consuming_nodeids=beta.selected_nodeids,
        execution_data={
            str((tmp_path / "src/alpha.py").resolve()): RuntimeFileExecution(
                executed_lines=frozenset({2}), called_qualnames=frozenset({"alpha"})
            )
        },
        lifecycle_equivalent=True,
    )
    evidence = replace(evidence, commands=(replace(alpha, contexts=(ambient,)), beta))

    result = evaluate_artifact_coverage_from_evidence(manifests, tmp_path, evidence)

    assert [
        error.code for error in result.reports[manifests[0].source_path].errors
    ] == [ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS]


def test_command_failure_attribution_and_e900_match_legacy(tmp_path):
    from maid_runner.core.artifact_coverage import (
        evaluate_artifact_coverage_from_evidence,
    )

    manifests = _write_project(tmp_path)
    evidence, _ = _bundle(tmp_path, manifests)
    evidence = replace(
        evidence,
        commands=(_incomplete(evidence.commands[0]), evidence.commands[1]),
    )
    fallback = _ExactExecutor(tmp_path, failures=("alpha",))

    result = evaluate_artifact_coverage_from_evidence(
        manifests, tmp_path, evidence, fallback_executor=fallback
    )
    legacy = _legacy(tmp_path, manifests, _ExactExecutor(tmp_path, failures=("alpha",)))

    assert (
        result.reports[manifests[0].source_path].to_dict()
        == legacy[manifests[0].source_path].to_dict()
    )
    assert result.fallback_identities == (evidence.commands[0].identity,)


def test_stateful_wide_scope_yield_fixture_uses_exact_command_fallback(tmp_path):
    from maid_runner.core.artifact_coverage import (
        evaluate_artifact_coverage_from_evidence,
    )
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    manifests = _write_project(tmp_path)
    (tmp_path / "tests" / "test_alpha.py").write_text(
        "def test_alpha():\n    assert True\n"
    )
    (tmp_path / "conftest.py").write_text(
        "import pytest\n"
        "from src.alpha import alpha\n\n"
        "@pytest.fixture(scope='session', autouse=True)\n"
        "def stateful_session():\n"
        "    yield\n"
        "    alpha()\n"
    )
    evidence = collect_runtime_evidence(manifests, tmp_path).evidence

    result = evaluate_artifact_coverage_from_evidence(manifests, tmp_path, evidence)
    legacy = _legacy(tmp_path, manifests)

    assert {path: report.to_dict() for path, report in result.reports.items()} == {
        path: report.to_dict() for path, report in legacy.items()
    }
    assert result.fallback_identities == tuple(
        command.identity for command in evidence.commands
    )
    assert all(
        command.completeness.unproven_fixture_lifecycles
        for command in evidence.commands
    )
    assert result.complete is False


def test_ambiguous_dynamic_fixture_or_collection_context_runs_exact_fallback(tmp_path):
    from maid_runner.core.artifact_coverage import (
        evaluate_artifact_coverage_from_evidence,
    )
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    session_root = tmp_path / "session-hook"
    session_root.mkdir()
    manifests = _write_project(session_root)
    (session_root / "tests" / "test_alpha.py").write_text(
        "def test_alpha():\n    assert True\n"
    )
    (session_root / "conftest.py").write_text(
        "import pytest\n"
        "from src.alpha import alpha\n\n"
        "@pytest.hookimpl(trylast=True)\n"
        "def pytest_sessionfinish(session, exitstatus):\n"
        "    alpha()\n"
    )
    evidence = collect_runtime_evidence(manifests, session_root).evidence
    assert evidence.commands[0].result.returncode == 0, (
        evidence.commands[0].result.stdout + evidence.commands[0].result.stderr
    )

    result = evaluate_artifact_coverage_from_evidence(manifests, session_root, evidence)
    legacy = _legacy(session_root, manifests)

    assert {path: report.to_dict() for path, report in result.reports.items()} == {
        path: report.to_dict() for path, report in legacy.items()
    }
    assert result.reports[manifests[0].source_path].success is True
    assert result.fallback_identities == tuple(
        command.identity for command in evidence.commands
    )
    assert all(
        "session:teardown" in command.completeness.unresolved_context_ids
        for command in evidence.commands
    ), tuple(command.completeness for command in evidence.commands)

    from maid_runner.core._runtime_evidence_pytest_plugin import RuntimeEvidencePlugin

    def project_partial_hook(session, exitstatus):
        return None

    hook = SimpleNamespace(
        get_hookimpls=lambda: [
            SimpleNamespace(function=partial(project_partial_hook), plugin=None)
        ]
    )
    partial_plugin = RuntimeEvidencePlugin(
        tmp_path / "partial-hook-evidence",
        frozenset({str(Path(__file__).resolve())}),
    )
    partial_plugin.pytest_sessionfinish(
        SimpleNamespace(
            config=SimpleNamespace(hook=SimpleNamespace(pytest_sessionfinish=hook))
        ),
        0,
    )
    assert "session:teardown" in partial_plugin.completeness.unresolved_context_ids

    collection_root = tmp_path / "collection-import"
    collection_root.mkdir()
    collection_manifests = _write_project(collection_root)
    (collection_root / "tests" / "test_alpha.py").write_text(
        "from src.alpha import alpha\n\n"
        "IMPORTED = alpha()\n\n"
        "def test_alpha():\n"
        "    assert IMPORTED == 'alpha'\n"
    )
    collection_evidence = collect_runtime_evidence(
        collection_manifests, collection_root
    ).evidence

    collection_result = evaluate_artifact_coverage_from_evidence(
        collection_manifests, collection_root, collection_evidence
    )
    collection_legacy = _legacy(collection_root, collection_manifests)

    assert {
        path: report.to_dict() for path, report in collection_result.reports.items()
    } == {path: report.to_dict() for path, report in collection_legacy.items()}
    assert collection_result.reports[collection_manifests[0].source_path].success
    assert collection_result.fallback_identities == tuple(
        command.identity for command in collection_evidence.commands
    )
    assert all(
        "collection:global" in command.completeness.unresolved_context_ids
        for command in collection_evidence.commands
    )


def test_worker_loss_or_selector_gap_runs_exact_fallback(tmp_path):
    from maid_runner.core.artifact_coverage import (
        evaluate_artifact_coverage_from_evidence,
    )

    manifests = _write_project(tmp_path)
    evidence, _ = _bundle(tmp_path, manifests)
    alpha = _incomplete(evidence.commands[0], missing_worker_ids=("gw1",))
    beta = _incomplete(
        evidence.commands[1], unsupported_selectors=("tests/test_beta.py",)
    )
    evidence = replace(evidence, commands=(alpha, beta))
    fallback = _ExactExecutor(tmp_path)

    result = evaluate_artifact_coverage_from_evidence(
        manifests, tmp_path, evidence, fallback_executor=fallback
    )

    assert result.fallback_identities == (alpha.identity, beta.identity)
    assert fallback.calls == [
        ("-q", "tests/test_alpha.py"),
        ("-q", "tests/test_beta.py"),
    ]


def test_content_digest_change_rejects_buffered_evidence(tmp_path):
    from maid_runner.core.artifact_coverage import (
        evaluate_artifact_coverage_from_evidence,
    )

    manifests = _write_project(tmp_path)
    evidence, _ = _bundle(tmp_path, manifests)
    (tmp_path / "tests" / "input.json").write_text('{"changed": true}\n')
    fallback = _ExactExecutor(tmp_path)

    result = evaluate_artifact_coverage_from_evidence(
        manifests, tmp_path, evidence, fallback_executor=fallback
    )

    assert result.fallback_identities == tuple(
        command.identity for command in evidence.commands
    )
    assert len(fallback.calls) == 2


def test_resolved_environment_identity_change_runs_exact_fallback(
    monkeypatch, tmp_path
):
    from maid_runner.core.artifact_coverage import (
        evaluate_artifact_coverage_from_evidence,
    )

    manifests = _write_project(tmp_path)
    monkeypatch.setenv("EVIDENCE_ENVIRONMENT", "before")
    evidence, _ = _bundle(tmp_path, manifests)
    monkeypatch.setenv("EVIDENCE_ENVIRONMENT", "after")
    fallback = _ExactExecutor(tmp_path)

    result = evaluate_artifact_coverage_from_evidence(
        manifests, tmp_path, evidence, fallback_executor=fallback
    )

    assert result.fallback_identities == tuple(
        command.identity for command in evidence.commands
    )


def test_compatible_group_executes_once_and_reports_each_manifest(tmp_path):
    from maid_runner.core.artifact_coverage import (
        evaluate_artifact_coverage_from_evidence,
    )

    manifests = _write_project(tmp_path)
    evidence, group_executor = _bundle(tmp_path, manifests)
    fallback = _ExactExecutor(tmp_path)

    result = evaluate_artifact_coverage_from_evidence(
        manifests, tmp_path, evidence, fallback_executor=fallback
    )

    assert len(group_executor.calls) == 1
    assert fallback.calls == []
    assert list(result.reports) == [manifest.source_path for manifest in manifests]
    assert all(report.success for report in result.reports.values())


def test_evidence_and_legacy_json_match_except_duration_fields(tmp_path):
    from maid_runner.core.artifact_coverage import (
        evaluate_artifact_coverage_from_evidence,
    )

    manifests = _write_project(tmp_path)
    evidence, _ = _bundle(tmp_path, manifests)
    evidence = replace(
        evidence,
        commands=(_incomplete(evidence.commands[0]), evidence.commands[1]),
    )

    result = evaluate_artifact_coverage_from_evidence(
        manifests,
        tmp_path,
        evidence,
        fallback_executor=_ExactExecutor(tmp_path, failures=("alpha",)),
    )
    legacy = _legacy(tmp_path, manifests, _ExactExecutor(tmp_path, failures=("alpha",)))

    assert {path: report.to_dict() for path, report in result.reports.items()} == {
        path: report.to_dict() for path, report in legacy.items()
    }
