"""Behavioral contract for knockout applicability in chain equivalence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


REQUIRED_ARTIFACTS = (
    "attribute:Service.enabled",
    "class:Service",
    "function:alpha",
    "method:Service.run",
)
DETECTION_ARTIFACTS = (
    "function:alpha",
    "method:Service.run",
)


def test_chain_report_limits_detection_to_knockout_capable_artifacts(
    tmp_path: Path,
) -> None:
    from maid_runner.cli.commands._format import format_chain_merge_report
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge import (
        artifact_requires_knockout_detection,
        build_chain_merge_report,
    )

    class RecordedSource:
        def __init__(self) -> None:
            self.requested: list[str] = []

        def detecting_nodeids_for(self, artifact_key: str) -> tuple[str, ...]:
            self.requested.append(artifact_key)
            return (f"tests/test_mixed.py::test_{len(self.requested)}",)

    _write_mixed_project(tmp_path)
    source = RecordedSource()
    report = build_chain_merge_report(
        "src/mixed.py",
        ManifestChain(tmp_path / "manifests"),
        source,
    )

    assert report.acceptance.required_artifacts == REQUIRED_ARTIFACTS
    assert tuple(source.requested) == DETECTION_ARTIFACTS
    assert tuple(report.acceptance.required_detecting_nodeids) == DETECTION_ARTIFACTS
    assert report.acceptance.unknown_detection_artifacts == ()
    assert report.acceptance.unknown_coverage_artifacts == REQUIRED_ARTIFACTS
    assert artifact_requires_knockout_detection("function:alpha") is True
    assert artifact_requires_knockout_detection("exact:14:function:alpha3:str") is True
    assert artifact_requires_knockout_detection("method:Service.run") is True
    assert (
        artifact_requires_knockout_detection(
            "exact:19:method:Parser.parse19:parse(System.Int32)"
        )
        is True
    )
    assert artifact_requires_knockout_detection("class:Service") is False
    assert artifact_requires_knockout_detection("attribute:Service.enabled") is False
    assert artifact_requires_knockout_detection("enum:Mode") is False
    assert artifact_requires_knockout_detection("interface:Runnable") is False
    assert artifact_requires_knockout_detection("type:Identifier") is False
    assert artifact_requires_knockout_detection("namespace:example.core") is False
    assert artifact_requires_knockout_detection("test_function:test_alpha") is False
    assert "detection: recorded for 2/2 artifacts" in format_chain_merge_report(report)


def test_chain_report_keeps_only_supported_artifacts_unknown_when_cold(
    tmp_path: Path,
) -> None:
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge import build_chain_merge_report

    _write_mixed_project(tmp_path)
    report = build_chain_merge_report(
        "src/mixed.py",
        ManifestChain(tmp_path / "manifests"),
        None,
    )

    assert report.acceptance.detection_available is False
    assert report.acceptance.required_detecting_nodeids == {}
    assert report.acceptance.unknown_detection_artifacts == DETECTION_ARTIFACTS
    assert report.acceptance.unknown_coverage_artifacts == REQUIRED_ARTIFACTS


def test_equivalence_accepts_complete_mixed_artifact_evidence() -> None:
    from maid_runner.core.chain_merge_equivalence import check_merge_equivalence

    baseline = _acceptance(
        detecting={
            "function:alpha": ("tests/old.py::test_alpha",),
            "method:Service.run": ("tests/old.py::test_run",),
        }
    )
    candidate = _acceptance(
        detecting={
            "function:alpha": ("tests/new.py::test_combined",),
            "method:Service.run": ("tests/new.py::test_combined",),
        }
    )

    result = check_merge_equivalence("src/mixed.py", baseline, candidate)

    assert result.success is True
    assert result.evidence_regressions == ()
    assert result.detection_regressions == ()
    assert result.coverage_regressions == ()


def test_equivalence_rejects_detection_claims_for_unsupported_artifacts() -> None:
    from maid_runner.core.chain_merge_equivalence import check_merge_equivalence

    claimed_for_every_kind = _acceptance(
        detecting={
            artifact: (f"tests/test_mixed.py::test_{index}",)
            for index, artifact in enumerate(REQUIRED_ARTIFACTS)
        }
    )

    result = check_merge_equivalence(
        "src/mixed.py",
        claimed_for_every_kind,
        claimed_for_every_kind,
    )

    assert result.success is False
    assert "baseline:contract" in result.evidence_regressions
    assert "candidate:contract" in result.evidence_regressions
    assert {error.code.value for error in result.errors} == {"E715"}


def test_equivalence_does_not_require_detection_source_without_eligible_artifacts() -> (
    None
):
    from maid_runner.core.chain_merge import ChainMergeAcceptanceSpec
    from maid_runner.core.chain_merge_equivalence import check_merge_equivalence

    required = ("attribute:Service.enabled", "class:Service")
    acceptance = ChainMergeAcceptanceSpec(
        required_artifacts=required,
        detection_available=False,
        required_detecting_nodeids={},
        unknown_detection_artifacts=(),
        coverage_available=True,
        required_covered_artifacts=required,
        uncovered_coverage_artifacts=(),
        unknown_coverage_artifacts=(),
    )

    result = check_merge_equivalence("src/mixed.py", acceptance, acceptance)

    assert result.success is True
    assert result.evidence_regressions == ()
    assert result.errors == ()


def test_cli_accepts_mixed_baseline_and_reports_only_candidate_debt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands._main import main

    _write_mixed_project(tmp_path)
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(_baseline_report(), indent=2) + "\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "chain",
            "merge",
            "src/mixed.py",
            "--verify-equivalence",
            str(baseline),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["success"] is False
    assert payload["evidence_regressions"]
    assert all(
        marker.startswith("candidate:") for marker in payload["evidence_regressions"]
    )


def test_cli_rejects_detection_claimed_for_unsupported_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands._main import main

    _write_mixed_project(tmp_path)
    payload = _baseline_report()
    payload["acceptance"]["required_detecting_nodeids"]["class:Service"] = [
        "tests/old.py::test_service"
    ]
    baseline = _write_baseline(tmp_path, payload)
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "chain",
            "merge",
            "src/mixed.py",
            "--verify-equivalence",
            str(baseline),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "baseline" in captured.err.lower()


def test_cli_rejects_supported_artifact_missing_from_detection_partition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands._main import main

    _write_mixed_project(tmp_path)
    payload = _baseline_report()
    del payload["acceptance"]["required_detecting_nodeids"]["method:Service.run"]
    baseline = _write_baseline(tmp_path, payload)
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "chain",
            "merge",
            "src/mixed.py",
            "--verify-equivalence",
            str(baseline),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "baseline" in captured.err.lower()


def _acceptance(*, detecting):
    from maid_runner.core.chain_merge import ChainMergeAcceptanceSpec

    return ChainMergeAcceptanceSpec(
        required_artifacts=REQUIRED_ARTIFACTS,
        detection_available=True,
        required_detecting_nodeids=dict(detecting),
        unknown_detection_artifacts=(),
        coverage_available=True,
        required_covered_artifacts=REQUIRED_ARTIFACTS,
        uncovered_coverage_artifacts=(),
        unknown_coverage_artifacts=(),
    )


def _baseline_report() -> dict:
    return {
        "file_path": "src/mixed.py",
        "verdict": "lean",
        "active_manifest_count": 1,
        "superseded_manifest_count": 0,
        "distinct_artifact_count": len(REQUIRED_ARTIFACTS),
        "total_declaration_count": len(REQUIRED_ARTIFACTS),
        "redundant_declaration_count": 0,
        "blocking_reasons": [],
        "acceptance": {
            "required_artifacts": list(REQUIRED_ARTIFACTS),
            "detection_available": True,
            "required_detecting_nodeids": {
                "function:alpha": ["tests/old.py::test_alpha"],
                "method:Service.run": ["tests/old.py::test_run"],
            },
            "unknown_detection_artifacts": [],
            "coverage_available": True,
            "required_covered_artifacts": list(REQUIRED_ARTIFACTS),
            "uncovered_coverage_artifacts": [],
            "unknown_coverage_artifacts": [],
        },
    }


def _write_baseline(root: Path, payload: dict) -> Path:
    baseline = root / "baseline.json"
    baseline.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return baseline


def _write_mixed_project(root: Path) -> None:
    (root / "src").mkdir()
    (root / "manifests").mkdir()
    (root / "src" / "mixed.py").write_text(
        "class Service:\n"
        "    enabled: bool = True\n\n"
        "    def run(self) -> str:\n"
        "        return 'ok'\n\n"
        "def alpha() -> str:\n"
        "    return 'alpha'\n",
        encoding="utf-8",
    )
    (root / "manifests" / "mixed.manifest.yaml").write_text(
        'schema: "2"\n'
        'goal: "Protect mixed artifacts"\n'
        "type: fix\n"
        'created: "2026-08-19T00:00:00Z"\n'
        "files:\n"
        "  edit:\n"
        "    - path: src/mixed.py\n"
        "      artifacts:\n"
        "        - {kind: class, name: Service}\n"
        "        - {kind: attribute, name: enabled, of: Service, type: bool}\n"
        "        - {kind: method, name: run, of: Service, args: [], returns: str}\n"
        "        - {kind: function, name: alpha, args: [], returns: str}\n"
        "validate:\n"
        "  - python -m pytest -q\n",
        encoding="utf-8",
    )
