"""Runtime gates reuse exact producer proof for Protocol interface declarations."""

from pathlib import Path
import subprocess
import textwrap

import pytest
import yaml

from maid_runner.core.artifact_coverage import (
    evaluate_artifact_coverage_from_evidence,
    run_artifact_coverage,
    run_artifact_coverage_batch,
)
from maid_runner.core.knockout import (
    build_knockout_mutation_specs,
    rewrite_artifact_body,
    run_knockout,
)
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode
from maid_runner.core.runtime_evidence import collect_runtime_evidence
from maid_runner.validators.python import PythonValidator

_MODES = ["exact", "batch", "evidence-exact", "evidence-derived"]
_CASES = [
    ("from typing import Protocol", "Protocol", "...", False, False),
    ("from typing import Protocol", "Protocol", '"Read contract."', False, False),
    ("from typing import Protocol as P", "P", "pass", False, False),
    ("import typing as t", "t.Protocol", "...", True, False),
    ("from typing_extensions import Protocol as P", "P", "...", False, False),
    ("import typing_extensions as t", "t.Protocol", '"Read contract."', True, False),
    (
        "from typing import Protocol, TypeVar\n_T = TypeVar('_T')",
        "Protocol[_T]",
        "...",
        False,
        False,
    ),
    ("from typing import Protocol", "Protocol", "...", False, True),
    (
        "from typing import Protocol\nclass Reader:\n    def read(self) -> str: ...",
        "Protocol",
        "...",
        False,
        False,
    ),
]


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=maid-test",
            "-c",
            "user.email=maid-test@example.com",
            *arguments,
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _source(
    imports: str,
    base: str,
    body: str,
    *,
    async_method: bool = False,
    getter: bool = False,
) -> str:
    bases = f"({base})" if base else ""
    decorator = "    @property\n" if getter else ""
    declaration = "async def" if async_method else "def"
    return (
        f"{imports}\nclass Reader{bases}:\n{decorator}    {declaration} read(self) -> str:\n"
        + textwrap.indent(body, "        ")
        + "\n"
    )


def _project(
    root: Path,
    source: str,
    *,
    async_method: bool = False,
    getter: bool = False,
    test: str | None = None,
    artifacts=None,
    default_hook: bool = False,
):
    (root / "manifests").mkdir()
    (root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n.maid/\n")
    (root / "contracts.py").write_text(source)
    if test is None:
        declaration = "async def" if async_method else "def"
        decorator = "    @property\n" if getter else ""
        operation = (
            "asyncio.run(reader.read())"
            if async_method
            else ("reader.read" if getter else "reader.read()")
        )
        test = (
            "import asyncio\nfrom contracts import Reader\nclass Concrete:\n"
            + decorator
            + f"    {declaration} read(self):\n        value = 'ok'\n        return value\n"
            + f"def test_reader():\n    reader: Reader = Concrete()\n    assert {operation} == 'ok'\n"
        )
    (root / "test_contracts.py").write_text(test)
    if artifacts is None:
        # Getter body probes intentionally address the callable AST target as a
        # method. Ordinary ATTRIBUTE-artifact exclusion is unchanged.
        artifacts = [
            {"kind": "class", "name": "Reader"},
            {
                "kind": "method",
                "name": "read",
                "of": "Reader",
                "args": [],
                "returns": "str",
            },
        ]
    if default_hook:
        for artifact in artifacts:
            if artifact.get("kind") == "method":
                artifact["default_hook"] = True
    data = {
        "schema": "2",
        "goal": "Check runtime applicability",
        "type": "fix",
        "created": "2026-10-21T00:00:00Z",
        "files": {
            "edit": [{"path": "contracts.py", "artifacts": artifacts}],
            "read": ["test_contracts.py"],
        },
        "validate": [["python", "-m", "pytest", "test_contracts.py", "-q"]],
    }
    path = root / "manifests/contract.manifest.yaml"
    path.write_text(yaml.safe_dump(data))
    _git(root, "init", "-q")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "fixture baseline")
    return load_manifest(path)


def _report(manifest, root: Path, mode: str):
    if mode == "exact":
        return run_artifact_coverage(manifest, root)
    if mode == "batch":
        return run_artifact_coverage_batch([manifest], root, jobs=1)[
            manifest.source_path
        ]
    evidence = collect_runtime_evidence([manifest], root).evidence
    return evaluate_artifact_coverage_from_evidence(
        [manifest], root, evidence, evidence_mode=mode.removeprefix("evidence-")
    ).reports[manifest.source_path]


@pytest.mark.parametrize("imports,base,body,async_method,getter", _CASES)
@pytest.mark.parametrize("mode", _MODES)
def test_protocol_signatures_have_no_runtime_body_requirement(
    tmp_path: Path,
    mode: str,
    imports: str,
    base: str,
    body: str,
    async_method: bool,
    getter: bool,
) -> None:
    manifest = _project(
        tmp_path,
        _source(imports, base, body, async_method=async_method, getter=getter),
        async_method=async_method,
        getter=getter,
    )

    report = _report(manifest, tmp_path, mode)

    assert report.success, report.errors
    assert not report.findings
    assert build_knockout_mutation_specs([manifest], tmp_path) == ()


@pytest.mark.parametrize("mode", _MODES)
@pytest.mark.parametrize(
    "body",
    [
        "return 'ok'",
        "value = 'ok'\nreturn value",
        "raise NotImplementedError('unsupported')",
    ],
)
def test_concrete_protocol_defaults_still_require_execution(
    tmp_path: Path, mode: str, body: str
) -> None:
    manifest = _project(
        tmp_path,
        _source("from typing import Protocol", "Protocol", body),
        default_hook=True,
    )

    report = _report(manifest, tmp_path, mode)

    assert not report.success
    assert any(
        error.code == ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS
        for error in report.errors
    )
    assert len(build_knockout_mutation_specs([manifest], tmp_path)) == 1


@pytest.mark.parametrize(
    "source",
    [
        _source("class Protocol: pass", "Protocol", "..."),
        _source("from typing import Protocol\nProtocol = object", "Protocol", "..."),
        _source("from typing import Protocol as P\nP = object", "P", "..."),
        _source(
            "from typing import Protocol\nclass Base(Protocol):\n    def read(self) -> str: ...",
            "Base",
            "...",
        ),
        _source(
            "from typing import Protocol\nclass Reader(Protocol):\n    def read(self) -> str: ...",
            "",
            "...",
        ),
        _source(
            "from abc import abstractmethod\nabstractmethod = lambda function: function",
            "",
            "...",
        ).replace("    def read", "    @abstractmethod\n    def read"),
        "from typing import Protocol\nclass Reader(Protocol):\n"
        "    def read(self) -> str: ...\nclass Reader:\n    pass\n",
        "from typing import Protocol\nclass Reader(Protocol):\n"
        "    def read(self) -> str: ...\nclass Reader(Protocol):\n    pass\n",
    ],
)
def test_unknown_or_redefined_classes_do_not_inherit_interface_exemption(
    tmp_path: Path, source: str
) -> None:
    manifest = _project(tmp_path, source)

    report = run_artifact_coverage(manifest, tmp_path)

    assert not report.success
    assert any(
        error.code == ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS
        for error in report.errors
    )
    assert len(build_knockout_mutation_specs([manifest], tmp_path)) == 1


def test_ordinary_property_metadata_is_not_interface_proof(tmp_path: Path) -> None:
    source = _source("", "", "...", getter=True)
    collected = PythonValidator().collect_implementation_artifacts(
        source, "contracts.py"
    )
    prop = next(artifact for artifact in collected.artifacts if artifact.name == "read")
    assert prop.is_stub is False
    manifest = _project(tmp_path, source, getter=True)

    report = run_artifact_coverage(manifest, tmp_path)

    assert not report.success
    assert any(
        error.code == ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS
        for error in report.errors
    )
    assert len(build_knockout_mutation_specs([manifest], tmp_path)) == 1


@pytest.mark.parametrize(
    "source",
    [
        "from typing import Protocol\nclass Reader(Protocol):\n    pass\n",
        "from typing import Protocol\nclass Reader(Protocol):\n    value: str\n",
        "class Reader:\n    pass\n",
        "from dataclasses import dataclass\n@dataclass\nclass Reader:\n    value: str\n",
    ],
)
def test_attribute_only_and_empty_classes_preserve_existing_runtime_policy(
    tmp_path: Path, source: str
) -> None:
    artifacts = [{"kind": "class", "name": "Reader"}]
    if "value: str" in source:
        artifacts.append(
            {"kind": "attribute", "name": "value", "of": "Reader", "type": "str"}
        )
    manifest = _project(
        tmp_path,
        source,
        artifacts=artifacts,
        test="from contracts import Reader\ndef test_declaration():\n    assert Reader is not None\n",
    )

    report = run_artifact_coverage(manifest, tmp_path)

    assert report.success, report.errors
    assert not report.findings
    assert build_knockout_mutation_specs([manifest], tmp_path) == ()


def test_knockout_skips_protocol_signature_without_mutating_source(
    tmp_path: Path,
) -> None:
    manifest = _project(
        tmp_path, _source("from typing import Protocol", "Protocol", "...")
    )
    source = tmp_path / "contracts.py"
    before = source.read_bytes()

    report = run_knockout(manifest, tmp_path)

    assert report.success, report.errors
    assert not report.results
    assert source.read_bytes() == before


def test_executed_concrete_default_remains_covered_and_knockout_eligible(
    tmp_path: Path,
) -> None:
    test = "from contracts import Reader\nclass Concrete(Reader):\n    pass\ndef test_default():\n    assert Concrete().read() == 'ok'\n"
    manifest = _project(
        tmp_path,
        _source("from typing import Protocol", "Protocol", "return 'ok'"),
        test=test,
        default_hook=True,
    )

    coverage = run_artifact_coverage(manifest, tmp_path)
    knockout = run_knockout(manifest, tmp_path)

    assert coverage.success, coverage.errors
    assert all(finding.executed for finding in coverage.findings)
    assert knockout.success, knockout.errors
    assert len(knockout.results) == 1


@pytest.mark.parametrize("final_interface", [True, False])
def test_knockout_uses_effective_redefined_class_and_restores_source(
    tmp_path: Path, final_interface: bool
) -> None:
    first = _source("from typing import Protocol", "Protocol", "...")
    concrete = _source("", "Protocol", "return 'ok'")
    source = concrete + first if final_interface else first + concrete
    test = (
        None
        if final_interface
        else (
            "from contracts import Reader\nclass Concrete(Reader):\n    pass\n"
            "def test_default():\n    assert Concrete().read() == 'ok'\n"
        )
    )
    # The concrete-first fixture needs the import before both definitions.
    source = "from typing import Protocol\n" + source
    manifest = _project(tmp_path, source, test=test, default_hook=not final_interface)
    path = tmp_path / "contracts.py"
    before = path.read_bytes()

    coverage = run_artifact_coverage(manifest, tmp_path)
    knockout = run_knockout(manifest, tmp_path)

    assert coverage.success, coverage.errors
    assert knockout.success, knockout.errors
    assert len(knockout.results) == (0 if final_interface else 1)
    assert path.read_bytes() == before


@pytest.mark.parametrize("nested_member", [False, True])
def test_knockout_direct_method_is_not_displaced_by_nested_class_name(
    tmp_path: Path, nested_member: bool
) -> None:
    source = (
        "class Reader:\n    def read(self):\n        return 'direct'\n"
        "class Outer:\n    class Reader:\n"
        + (
            "        def read(self):\n            return 'nested'\n"
            if nested_member
            else "        pass\n"
        )
    )
    source += (
        "class Peer:\n    class Reader:\n        def read(self):\n"
        "            return 'peer'\n"
    )
    manifest = _project(
        tmp_path,
        source,
        default_hook=True,
        test="from contracts import Reader\ndef test_reader():\n    assert Reader().read() == 'direct'\n",
    )
    path = tmp_path / "contracts.py"
    before = path.read_bytes()

    coverage = run_artifact_coverage(manifest, tmp_path)
    knockout = run_knockout(manifest, tmp_path)

    mutated = rewrite_artifact_body(source, "read", "method", "Reader")
    namespace = {}
    exec(compile(mutated, "contracts.py", "exec"), namespace)

    with pytest.raises(NotImplementedError, match="maid-knockout"):
        namespace["Reader"]().read()
    assert coverage.success, coverage.errors
    assert knockout.success, knockout.errors
    assert len(knockout.results) == 1
    assert path.read_bytes() == before
    assert namespace["Peer"].Reader().read() == "peer"
    if nested_member:
        assert namespace["Outer"].Reader().read() == "nested"
    else:
        assert isinstance(namespace["Outer"].Reader(), namespace["Outer"].Reader)


@pytest.mark.parametrize("mode", _MODES)
def test_interface_only_unittest_needs_no_body_instrumentation(
    tmp_path: Path, mode: str
) -> None:
    manifest = _project(
        tmp_path, _source("from typing import Protocol", "Protocol", "...")
    )
    (tmp_path / "test_contracts.py").write_text(
        "import unittest\nfrom contracts import Reader\nclass Concrete:\n"
        "    def read(self):\n        value = 'ok'\n        return value\n"
        "class ReaderTests(unittest.TestCase):\n    def test_reader(self):\n"
        "        reader: Reader = Concrete()\n        self.assertEqual(reader.read(), 'ok')\n"
    )
    path = Path(manifest.source_path)
    data = yaml.safe_load(path.read_text())
    data["validate"] = [["python", "-m", "unittest", "test_contracts", "-q"]]
    path.write_text(yaml.safe_dump(data))
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "Use actual unittest contract")
    manifest = load_manifest(path)
    actual = subprocess.run(
        manifest.validate_commands[0], cwd=tmp_path, capture_output=True, text=True
    )
    assert actual.returncode == 0, actual.stdout + actual.stderr

    report = _report(manifest, tmp_path, mode)

    assert report.success, report.errors
    assert not report.findings
    assert build_knockout_mutation_specs([manifest], tmp_path) == ()


def test_mixed_interface_and_adapter_preserve_real_runtime_observations(
    tmp_path: Path,
) -> None:
    source = _source("from typing import Protocol", "Protocol", "...")
    source += "\nclass Adapter:\n    def read(self) -> str:\n        value = 'ok'\n        return value\n"
    artifacts = [{"kind": "class", "name": name} for name in ("Reader", "Adapter")] + [
        {"kind": "method", "name": "read", "of": name, "args": [], "returns": "str"}
        for name in ("Reader", "Adapter")
    ]
    test = "from contracts import Reader, Adapter\ndef test_adapter():\n    reader: Reader = Adapter()\n    assert reader.read() == 'ok'\n"
    manifest = _project(tmp_path, source, artifacts=artifacts, test=test)

    report = run_artifact_coverage(manifest, tmp_path)
    plan = build_knockout_mutation_specs([manifest], tmp_path)

    assert report.success, report.errors
    assert {
        (finding.artifact_name, finding.parent_class, finding.executed)
        for finding in report.findings
    } == {("Adapter", None, True), ("read", "Adapter", True)}
    assert [
        (spec.identity.artifact_name, spec.identity.parent_class) for spec in plan
    ] == [("read", "Adapter")]
