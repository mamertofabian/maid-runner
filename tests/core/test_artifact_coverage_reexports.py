"""Behavioral contract for executable Python package re-export coverage."""

from __future__ import annotations

from pathlib import Path

from maid_runner.core.artifact_coverage import (
    evaluate_artifact_coverage_from_evidence,
    run_artifact_coverage,
    run_artifact_coverage_batch,
)
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode
from maid_runner.core.runtime_evidence import collect_runtime_evidence


def test_exact_and_derived_coverage_credit_called_package_reexport(
    tmp_path: Path,
) -> None:
    manifest = _write_reexport_project(tmp_path, call_export=True)

    reports = _coverage_reports(manifest, tmp_path)

    for report in reports:
        assert report.success is True
        assert [finding.to_dict() for finding in report.findings] == [
            {
                "artifact_name": "exported",
                "artifact_kind": "function",
                "parent_class": None,
                "file_path": "pkg/__init__.py",
                "executed": True,
            }
        ]


def test_aliased_reexport_uses_source_symbol_but_reports_public_identity(
    tmp_path: Path,
) -> None:
    manifest = _write_reexport_project(
        tmp_path,
        public_name="public_api",
        source_name="implementation_name",
        call_export=True,
    )

    reports = _coverage_reports(manifest, tmp_path)

    for report in reports:
        assert report.success is True
        assert len(report.findings) == 1
        finding = report.findings[0]
        assert finding.artifact_name == "public_api"
        assert finding.file_path == "pkg/__init__.py"
        assert finding.executed is True


def test_imported_but_uncalled_reexport_remains_e710(tmp_path: Path) -> None:
    manifest = _write_reexport_project(tmp_path, call_export=False)

    reports = _coverage_reports(manifest, tmp_path)

    assert all(report.success is False for report in reports)
    for report in reports:
        _assert_public_e710(report, "exported")


def test_star_reexport_remains_e710(tmp_path: Path) -> None:
    manifest = _write_reexport_project(
        tmp_path, call_export=True, reexport_style="star"
    )

    reports = _coverage_reports(manifest, tmp_path)

    assert all(report.success is False for report in reports)
    for report in reports:
        _assert_public_e710(report, "exported")


def test_multihop_reexport_remains_e710(tmp_path: Path) -> None:
    manifest = _write_reexport_project(
        tmp_path, call_export=True, reexport_style="multihop"
    )

    reports = _coverage_reports(manifest, tmp_path)

    assert all(report.success is False for report in reports)
    for report in reports:
        _assert_public_e710(report, "exported")


def _coverage_reports(manifest, root: Path):
    exact = run_artifact_coverage(manifest, root)
    batch = run_artifact_coverage_batch((manifest,), root, jobs=1)[manifest.source_path]
    evidence = collect_runtime_evidence((manifest,), root, pytest_workers=1).evidence
    derived = evaluate_artifact_coverage_from_evidence(
        (manifest,), root, evidence, evidence_mode="derived"
    ).reports[manifest.source_path]
    return exact, batch, derived


def _assert_public_e710(report, public_name: str) -> None:
    assert report.success is False
    assert report.findings[0].executed is False
    assert [error.code for error in report.errors] == [
        ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS
    ]
    assert report.errors[0].location.file == "pkg/__init__.py"
    assert f"'{public_name}'" in report.errors[0].message


def _write_reexport_project(
    root: Path,
    *,
    public_name: str = "exported",
    source_name: str = "exported",
    call_export: bool,
    reexport_style: str = "direct",
):
    package = root / "pkg"
    package.mkdir()
    alias = f" as {public_name}" if public_name != source_name else ""
    if reexport_style == "star":
        init_source = "from .implementation import *\n"
    elif reexport_style == "multihop":
        middle = package / "middle"
        middle.mkdir()
        (middle / "__init__.py").write_text(
            f"from ..implementation import {source_name}{alias}\n",
            encoding="utf-8",
        )
        init_source = f"from .middle import {public_name}\n"
    else:
        init_source = f"from .implementation import {source_name}{alias}\n"
    (package / "__init__.py").write_text(init_source, encoding="utf-8")
    (package / "implementation.py").write_text(
        f"def {source_name}() -> str:\n    return 'covered'\n",
        encoding="utf-8",
    )
    tests = root / "tests"
    tests.mkdir()
    assertion = (
        f"    assert {public_name}() == 'covered'\n"
        if call_export
        else f"    assert callable({public_name})\n"
    )
    (tests / "test_public_api.py").write_text(
        f"from pkg import {public_name}\n\n\n"
        "def test_public_api():\n"
        f"{assertion}",
        encoding="utf-8",
    )
    manifests = root / "manifests"
    manifests.mkdir()
    manifest_path = manifests / "reexport.manifest.yaml"
    manifest_path.write_text(
        "schema: '2'\n"
        "goal: 'Exercise a public package re-export'\n"
        "type: fix\n"
        "created: '2026-08-16T00:00:00Z'\n"
        "files:\n"
        "  edit:\n"
        "    - path: pkg/__init__.py\n"
        "      artifacts:\n"
        "        - kind: function\n"
        f"          name: {public_name}\n"
        "          args: []\n"
        "          returns: str\n"
        "validate:\n"
        "  - python -m pytest -q tests/test_public_api.py\n",
        encoding="utf-8",
    )
    return load_manifest(manifest_path)
