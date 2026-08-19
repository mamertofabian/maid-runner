"""Behavioral contract for abstract declaration knockout applicability."""

from __future__ import annotations

from pathlib import Path


def _manifest(project: Path, artifacts: str):
    from maid_runner.core.manifest import load_manifest

    manifest_path = project / "manifests" / "contract.manifest.yaml"
    manifest_path.parent.mkdir()
    manifest_path.write_text(
        'schema: "2"\n'
        'goal: "Protect abstract contract applicability"\n'
        "type: fix\n"
        'created: "2026-08-20T00:00:00Z"\n'
        "files:\n"
        "  edit:\n"
        "    - path: src/contracts.py\n"
        "      artifacts:\n"
        f"{artifacts}"
        "validate:\n"
        "  - python -m pytest -q tests/test_contracts.py\n",
        encoding="utf-8",
    )
    return load_manifest(manifest_path)


def test_knockout_plan_omits_exact_stdlib_abstract_contract_only(
    tmp_path: Path,
) -> None:
    from maid_runner.core.knockout import build_knockout_mutation_specs

    project = tmp_path / "project"
    source = project / "src"
    source.mkdir(parents=True)
    (source / "contracts.py").write_text(
        "import abc\n"
        "from abc import ABC, abstractmethod\n\n"
        "class Base(ABC):\n"
        "    @abstractmethod\n"
        "    def run(self) -> str:\n"
        '        """Declare the required operation."""\n\n'
        "    @abc.abstractmethod\n"
        "    def qualified(self) -> str:\n"
        '        """Declare a qualified operation."""\n\n'
        "    def concrete(self) -> str:\n"
        "        return 'ok'\n",
        encoding="utf-8",
    )
    manifest = _manifest(
        project,
        "        - {kind: method, name: run, of: Base, returns: str}\n"
        "        - {kind: method, name: qualified, of: Base, returns: str}\n"
        "        - {kind: method, name: concrete, of: Base, returns: str}\n",
    )

    specs = build_knockout_mutation_specs((manifest,), project, limit=1)

    assert [spec.identity.artifact_name for spec in specs] == ["concrete"]


def test_knockout_plan_keeps_fake_and_rebound_abstractmethod_decorators(
    tmp_path: Path,
) -> None:
    from maid_runner.core.knockout import build_knockout_mutation_specs

    project = tmp_path / "project"
    source = project / "src"
    source.mkdir(parents=True)
    (source / "contracts.py").write_text(
        "def abstractmethod(function):\n"
        "    return function\n\n"
        "class Fake:\n"
        "    @abstractmethod\n"
        "    def fake(self) -> str:\n"
        "        return 'fake'\n\n"
        "from abc import abstractmethod as rebound\n"
        "rebound = abstractmethod\n\n"
        "class Rebound:\n"
        "    @rebound\n"
        "    def rebound_method(self) -> str:\n"
        "        return 'rebound'\n",
        encoding="utf-8",
    )
    manifest = _manifest(
        project,
        "        - {kind: method, name: fake, of: Fake, returns: str}\n"
        "        - {kind: method, name: rebound_method, of: Rebound, returns: str}\n",
    )

    specs = build_knockout_mutation_specs((manifest,), project)

    assert [spec.identity.artifact_name for spec in specs] == [
        "fake",
        "rebound_method",
    ]
