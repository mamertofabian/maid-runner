"""Behavioral contract for abstract Python artifact coverage applicability."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent, indent

from maid_runner.core._runtime_command_executor import (
    RuntimeCommandRecord,
    RuntimeFileExecution,
)
from maid_runner.core.artifact_coverage import (
    evaluate_artifact_coverage_from_evidence,
    run_artifact_coverage,
    run_artifact_coverage_batch,
)
from maid_runner.core.manifest import load_manifest
from maid_runner.core.runtime_evidence import (
    collect_runtime_evidence,
    RuntimeContextEvidence,
    RuntimeEvidenceCompleteness,
    RuntimeGroupEvidence,
)


def test_abstract_protocol_contracts_are_not_runtime_coverage_targets(
    tmp_path: Path,
) -> None:
    manifest = _write_project(
        tmp_path,
        source="""
            from abc import abstractmethod
            from typing import Protocol

            class Reader(Protocol):
                @abstractmethod
                def read(self, value: str) -> str:
                    raise NotImplementedError

            class ConcreteReader:
                def read(self, value: str) -> str:
                    return value.upper()
        """,
        test_body="""
            from contracts import ConcreteReader

            def test_reader():
                assert ConcreteReader().read("covered") == "COVERED"
        """,
        artifacts="""
                - kind: class
                  name: Reader
                - kind: method
                  name: read
                  of: Reader
                  args:
                    - {name: self, type: Reader}
                    - {name: value, type: str}
                  returns: str
                - kind: class
                  name: ConcreteReader
                - kind: method
                  name: read
                  of: ConcreteReader
                  args:
                    - {name: self, type: ConcreteReader}
                    - {name: value, type: str}
                  returns: str
        """,
    )

    reports = _coverage_reports(
        manifest,
        tmp_path,
        executed_qualnames=("ConcreteReader", "ConcreteReader.read"),
    )

    assert all(report.success for report in reports)
    for report in reports:
        assert [
            (finding.artifact_name, finding.parent_class, finding.executed)
            for finding in report.findings
        ] == [
            ("ConcreteReader", None, True),
            ("read", "ConcreteReader", True),
        ]


def test_qualified_abc_abstractmethod_contract_is_not_a_runtime_target(
    tmp_path: Path,
) -> None:
    manifest = _write_project(
        tmp_path,
        source="""
            import abc

            class Reader(abc.ABC):
                @abc.abstractmethod
                def read(self, value: str) -> str: ...
        """,
        test_body="""
            import inspect
            from contracts import Reader

            def test_reader_contract():
                assert inspect.isabstract(Reader)
        """,
        artifacts="""
                - kind: class
                  name: Reader
                - kind: method
                  name: read
                  of: Reader
                  args:
                    - {name: self, type: Reader}
                    - {name: value, type: str}
                  returns: str
        """,
    )

    reports = _coverage_reports(manifest, tmp_path)

    assert all(report.success for report in reports)
    for report in reports:
        assert report.findings == ()
        assert report.errors == ()


def test_mixed_abstract_class_keeps_concrete_method_coverage_obligation(
    tmp_path: Path,
) -> None:
    manifest = _write_project(
        tmp_path,
        source="""
            from abc import ABC, abstractmethod

            class Template(ABC):
                @abstractmethod
                def render(self, value: str) -> str:
                    raise NotImplementedError

                def normalize(self, value: str) -> str:
                    return value.strip()
        """,
        test_body="""
            import inspect
            from contracts import Template

            def test_template_contract():
                assert inspect.isabstract(Template)
        """,
        artifacts="""
                - kind: class
                  name: Template
                - kind: method
                  name: render
                  of: Template
                  args:
                    - {name: self, type: Template}
                    - {name: value, type: str}
                  returns: str
                - kind: method
                  name: normalize
                  of: Template
                  args:
                    - {name: self, type: Template}
                    - {name: value, type: str}
                  returns: str
        """,
    )

    reports = _coverage_reports(manifest, tmp_path)

    assert all(report.success is False for report in reports)
    for report in reports:
        assert [error.message.split("'")[1] for error in report.errors] == [
            "Template",
            "Template.normalize",
        ]
        assert [
            (finding.artifact_name, finding.parent_class) for finding in report.findings
        ] == [("Template", None), ("normalize", "Template")]


def test_fake_abstractmethod_attribute_does_not_bypass_runtime_coverage(
    tmp_path: Path,
) -> None:
    manifest = _write_project(
        tmp_path,
        source="""
            class fake:
                @staticmethod
                def abstractmethod(function):
                    return function

            class Service:
                @fake.abstractmethod
                def run(self) -> str:
                    return "not called"
        """,
        test_body="""
            from contracts import Service

            def test_service_contract():
                assert callable(Service)
        """,
        artifacts="""
                - kind: class
                  name: Service
                - kind: method
                  name: run
                  of: Service
                  args:
                    - {name: self, type: Service}
                  returns: str
        """,
    )

    reports = _coverage_reports(manifest, tmp_path)

    assert all(report.success is False for report in reports)
    for report in reports:
        assert [error.message.split("'")[1] for error in report.errors] == [
            "Service",
            "Service.run",
        ]


def test_undecorated_stub_body_remains_a_runtime_coverage_obligation(
    tmp_path: Path,
) -> None:
    manifest = _write_project(
        tmp_path,
        source="""
            class Service:
                def run(self) -> str:
                    raise NotImplementedError
        """,
        test_body="""
            from contracts import Service

            def test_service_contract():
                assert callable(Service)
        """,
        artifacts="""
                - kind: class
                  name: Service
                - kind: method
                  name: run
                  of: Service
                  args:
                    - {name: self, type: Service}
                  returns: str
        """,
    )

    reports = _coverage_reports(manifest, tmp_path)

    assert all(report.success is False for report in reports)
    for report in reports:
        assert [error.message.split("'")[1] for error in report.errors] == [
            "Service",
            "Service.run",
        ]


def test_locally_bound_abstractmethod_name_does_not_bypass_runtime_coverage(
    tmp_path: Path,
) -> None:
    manifest = _write_project(
        tmp_path,
        source="""
            from abc import abstractmethod

            def abstractmethod(function):
                return function

            class Service:
                @abstractmethod
                def run(self) -> str:
                    return "not called"
        """,
        test_body="""
            from contracts import Service

            def test_service_contract():
                assert callable(Service)
        """,
        artifacts="""
                - kind: class
                  name: Service
                - kind: method
                  name: run
                  of: Service
                  args:
                    - {name: self, type: Service}
                  returns: str
        """,
    )

    reports = _coverage_reports(manifest, tmp_path)

    assert all(report.success is False for report in reports)
    for report in reports:
        assert [error.message.split("'")[1] for error in report.errors] == [
            "Service",
            "Service.run",
        ]


def test_locally_bound_abc_name_does_not_bypass_runtime_coverage(
    tmp_path: Path,
) -> None:
    manifest = _write_project(
        tmp_path,
        source="""
            class abc:
                @staticmethod
                def abstractmethod(function):
                    return function

            class Service:
                @abc.abstractmethod
                def run(self) -> str:
                    return "not called"
        """,
        test_body="""
            from contracts import Service

            def test_service_contract():
                assert callable(Service)
        """,
        artifacts="""
                - kind: class
                  name: Service
                - kind: method
                  name: run
                  of: Service
                  args:
                    - {name: self, type: Service}
                  returns: str
        """,
    )

    reports = _coverage_reports(manifest, tmp_path)

    assert all(report.success is False for report in reports)
    for report in reports:
        assert [error.message.split("'")[1] for error in report.errors] == [
            "Service",
            "Service.run",
        ]


def test_definition_decorator_rebinding_does_not_bypass_runtime_coverage(
    tmp_path: Path,
) -> None:
    manifest = _write_project(
        tmp_path,
        source="""
            from abc import abstractmethod

            def fake(function):
                return function

            def preserve_class(cls):
                return cls

            @((abstractmethod := fake) and preserve_class)
            class RebindingMarker:
                pass

            class Service:
                @abstractmethod
                def run(self) -> str:
                    return "not called"
        """,
        test_body="""
            from contracts import Service

            def test_service_contract():
                assert callable(Service)
        """,
        artifacts="""
                - kind: class
                  name: Service
                - kind: method
                  name: run
                  of: Service
                  args:
                    - {name: self, type: Service}
                  returns: str
        """,
    )

    reports = _coverage_reports(manifest, tmp_path)

    assert all(report.success is False for report in reports)
    for report in reports:
        assert [error.message.split("'")[1] for error in report.errors] == [
            "Service",
            "Service.run",
        ]


def test_comprehension_walrus_rebinding_does_not_bypass_runtime_coverage(
    tmp_path: Path,
) -> None:
    manifest = _write_project(
        tmp_path,
        source="""
            import abc

            class fake_abc:
                @staticmethod
                def abstractmethod(function):
                    return function

            rebound = [(abc := fake_abc) for _ in range(1)]

            class Service:
                @abc.abstractmethod
                def run(self) -> str:
                    return "not called"
        """,
        test_body="""
            from contracts import Service

            def test_service_contract():
                assert callable(Service)
        """,
        artifacts="""
                - kind: class
                  name: Service
                - kind: method
                  name: run
                  of: Service
                  args:
                    - {name: self, type: Service}
                  returns: str
        """,
    )

    reports = _coverage_reports(manifest, tmp_path)

    assert all(report.success is False for report in reports)
    for report in reports:
        assert [error.message.split("'")[1] for error in report.errors] == [
            "Service",
            "Service.run",
        ]


def test_direct_abc_attribute_mutation_does_not_bypass_runtime_coverage(
    tmp_path: Path,
) -> None:
    manifest = _write_project(
        tmp_path,
        source="""
            import abc

            def fake(function):
                return function

            abc.abstractmethod = fake

            class Service:
                @abc.abstractmethod
                def run(self) -> str:
                    return "not called"
        """,
        test_body="""
            from contracts import Service

            def test_service_contract():
                assert callable(Service)
        """,
        artifacts="""
                - kind: class
                  name: Service
                - kind: method
                  name: run
                  of: Service
                  args:
                    - {name: self, type: Service}
                  returns: str
        """,
    )

    reports = _coverage_reports(manifest, tmp_path)

    assert all(report.success is False for report in reports)
    for report in reports:
        assert [error.message.split("'")[1] for error in report.errors] == [
            "Service",
            "Service.run",
        ]


def _coverage_reports(
    manifest,
    root: Path,
    *,
    executed_qualnames: tuple[str, ...] = (),
):
    executor = _FakeRuntimeCommandExecutor(
        root,
        executed_qualnames=executed_qualnames,
    )
    exact = run_artifact_coverage(manifest, root, executor=executor)
    batch = run_artifact_coverage_batch((manifest,), root, executor=executor, jobs=1)[
        manifest.source_path
    ]
    evidence = collect_runtime_evidence(
        (manifest,),
        root,
        executor=executor,
        pytest_workers=1,
    ).evidence
    derived = evaluate_artifact_coverage_from_evidence(
        (manifest,), root, evidence, evidence_mode="derived"
    ).reports[manifest.source_path]
    return exact, batch, derived


class _FakeRuntimeCommandExecutor:
    def __init__(
        self,
        root: Path,
        *,
        executed_qualnames: tuple[str, ...],
    ) -> None:
        self._root = root
        self._executed_qualnames = frozenset(executed_qualnames)

    def execute(
        self,
        command: tuple[str, ...],
        target_files: set[str],
        project_root: Path,
        timeout_seconds: float,
        **_kwargs,
    ) -> RuntimeCommandRecord:
        return self._record(command, target_files)

    def execute_with_contexts(
        self,
        command: tuple[str, ...],
        target_files: set[str],
        project_root: Path,
        timeout_seconds: float,
        pytest_workers=None,
        logical_selectors: tuple[str, ...] | None = None,
    ) -> RuntimeGroupEvidence:
        nodeid = "tests/test_contracts.py::test_contract"
        context = RuntimeContextEvidence(
            context_id=nodeid,
            kind="node",
            consuming_nodeids=(nodeid,),
            execution_data=self._execution_data(target_files),
        )
        selectors = tuple(logical_selectors or ("tests/test_contracts.py",))
        return RuntimeGroupEvidence(
            command=command,
            selected_nodeids=(nodeid,),
            selector_nodeids={selector: (nodeid,) for selector in selectors},
            contexts=(context,),
            result=self._record(command, target_files),
            worker_ids=(),
            completeness=RuntimeEvidenceCompleteness(complete=True),
        )

    def _record(
        self,
        command: tuple[str, ...],
        target_files: set[str],
    ) -> RuntimeCommandRecord:
        return RuntimeCommandRecord(
            command=command,
            returncode=0,
            stdout="",
            stderr="",
            execution_data=self._execution_data(target_files),
            report_errors=(),
        )

    def _execution_data(
        self,
        target_files: set[str],
    ) -> dict[str, RuntimeFileExecution]:
        contract_path = str((self._root / "contracts.py").resolve())
        selected_files = target_files or {contract_path}
        return {
            path: RuntimeFileExecution(
                executed_lines=frozenset(),
                called_qualnames=(
                    self._executed_qualnames
                    if Path(path) == Path(contract_path)
                    else frozenset()
                ),
            )
            for path in selected_files
        }


def _write_project(
    root: Path,
    *,
    source: str,
    test_body: str,
    artifacts: str,
):
    (root / "contracts.py").write_text(dedent(source).lstrip(), encoding="utf-8")
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_contracts.py").write_text(
        dedent(test_body).lstrip(),
        encoding="utf-8",
    )
    manifests = root / "manifests"
    manifests.mkdir()
    manifest_path = manifests / "abstract-contract.manifest.yaml"
    manifest_path.write_text(
        "schema: '2'\n"
        "goal: 'Exercise concrete behavior behind abstract contracts'\n"
        "type: fix\n"
        "created: '2026-08-16T00:00:00Z'\n"
        "files:\n"
        "  edit:\n"
        "    - path: contracts.py\n"
        "      artifacts:\n"
        f"{indent(dedent(artifacts).strip(), '        ')}\n"
        "validate:\n"
        "  - python -m pytest -q tests/test_contracts.py\n",
        encoding="utf-8",
    )
    return load_manifest(manifest_path)
