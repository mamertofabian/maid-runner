"""Behavioral contract for chain-merge child 3b coverage evidence wiring."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_manifest(root: Path, *, covered: bool = True) -> None:
    (root / "manifests").mkdir()
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "target.py").write_text(
        "def target() -> bool:\n    values = [True]\n    return all(values)\n",
        encoding="utf-8",
    )
    assertion = "assert target() is True" if covered else "assert callable(target)"
    (root / "tests" / "test_target.py").write_text(
        f"from src.target import target\n\ndef test_target():\n    {assertion}\n",
        encoding="utf-8",
    )
    (root / "manifests" / "target.manifest.yaml").write_text(
        'schema: "2"\n'
        'goal: "target"\n'
        "type: feature\n"
        'created: "2026-08-16T00:00:00Z"\n'
        "files:\n"
        "  edit:\n"
        "    - path: src/target.py\n"
        "      artifacts:\n"
        "        - kind: function\n"
        "          name: target\n"
        "          args: []\n"
        "          returns: bool\n"
        "  read:\n"
        "    - tests/test_target.py\n"
        "validate:\n"
        "  - python -m pytest -q tests/test_target.py\n",
        encoding="utf-8",
    )


def _chain(root: Path):
    from maid_runner.core.chain import ManifestChain

    return ManifestChain(root / "manifests")


def _add_duplicate_uncovered_manifest(root: Path) -> None:
    (root / "tests" / "test_weak.py").write_text(
        "from src.target import target\n\n"
        "def test_weak():\n"
        "    assert callable(target)\n",
        encoding="utf-8",
    )
    (root / "manifests" / "weak.manifest.yaml").write_text(
        'schema: "2"\n'
        'goal: "duplicate weak target declaration"\n'
        "type: feature\n"
        'created: "2026-08-16T00:00:01Z"\n'
        "files:\n"
        "  edit:\n"
        "    - path: src/target.py\n"
        "      artifacts:\n"
        "        - kind: function\n"
        "          name: target\n"
        "          args: []\n"
        "          returns: bool\n"
        "  read:\n"
        "    - tests/test_weak.py\n"
        "validate:\n"
        "  - python -m pytest -q tests/test_weak.py\n",
        encoding="utf-8",
    )


def _warm_coverage_cache(root: Path) -> int:
    from maid_runner.cli.commands._main import main

    return main(
        [
            "verify",
            "--artifact-coverage",
            "--no-changed-scope",
            "--manifest-dir",
            "manifests",
        ]
    )


def test_recorded_coverage_source_distinguishes_covered_uncovered_and_unknown():
    from maid_runner.core.chain_merge_evidence import RecordedCoverageEvidenceSource

    source = RecordedCoverageEvidenceSource(
        {
            ("src/target.py", "function:covered"): True,
            ("src/target.py", "function:uncovered"): False,
        }
    )

    assert source.coverage_for("src/target.py", "function:covered") is True
    assert source.coverage_for("src/target.py", "function:uncovered") is False
    assert source.coverage_for("src/target.py", "function:missing") is None
    assert source.coverage_for("src/other.py", "function:covered") is None


def test_recorded_coverage_source_satisfies_protocol():
    from maid_runner.core.chain_merge import CoverageEvidenceSource
    from maid_runner.core.chain_merge_evidence import RecordedCoverageEvidenceSource

    source: CoverageEvidenceSource = RecordedCoverageEvidenceSource({})

    assert isinstance(source, CoverageEvidenceSource)


def test_coverage_protocol_owner_command_rejects_knockout_sentinel():
    from maid_runner.core.chain_merge import CoverageEvidenceSource

    class RecordedSource:
        def coverage_for(self, file_path: str, artifact_key: str):
            return bool(file_path and artifact_key)

    source: CoverageEvidenceSource = RecordedSource()
    with pytest.raises(NotImplementedError) as exc_info:
        CoverageEvidenceSource.coverage_for(source, "src/target.py", "function:target")

    assert exc_info.value.args == ()


def test_recorded_coverage_cache_reader_rejects_stale_evidence(
    tmp_path, monkeypatch, capsys
):
    from maid_runner.core.chain_merge_evidence import (
        RecordedCoverageEvidenceSource,
        coverage_source_for_file,
    )

    _write_manifest(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert _warm_coverage_cache(tmp_path) == 0
    capsys.readouterr()

    source = RecordedCoverageEvidenceSource.from_cache(
        _chain(tmp_path).active_manifests(), str(tmp_path), "manifests"
    )
    assert source.coverage_for("src/target.py", "function:target") is True
    per_file = coverage_source_for_file(
        _chain(tmp_path), "src/target.py", str(tmp_path), "manifests"
    )
    assert per_file.coverage_for("src/target.py", "function:target") is True

    (tmp_path / "src" / "target.py").write_text(
        "def target() -> bool:\n    return False\n", encoding="utf-8"
    )
    stale = RecordedCoverageEvidenceSource.from_cache(
        _chain(tmp_path).active_manifests(), str(tmp_path), "manifests"
    )
    assert stale.coverage_for("src/target.py", "function:target") is None


def test_recorded_coverage_source_keeps_e710_when_duplicate_evidence_conflicts(
    tmp_path, monkeypatch, capsys
):
    from maid_runner.core.chain_merge_evidence import coverage_source_for_file

    _write_manifest(tmp_path)
    _add_duplicate_uncovered_manifest(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert _warm_coverage_cache(tmp_path) == 0
    capsys.readouterr()

    source = coverage_source_for_file(
        _chain(tmp_path), "src/target.py", str(tmp_path), "manifests"
    )
    assert source.coverage_for("src/target.py", "function:target") is None


def test_report_records_covered_and_unknown_coverage(tmp_path):
    from maid_runner.core.chain_merge import build_chain_merge_report
    from maid_runner.core.chain_merge_evidence import RecordedCoverageEvidenceSource

    _write_manifest(tmp_path)
    source = RecordedCoverageEvidenceSource(
        {("src/target.py", "function:target"): True}
    )

    report = build_chain_merge_report("src/target.py", _chain(tmp_path), None, source)

    assert report.acceptance.coverage_available is True
    assert report.acceptance.required_covered_artifacts == ("function:target",)
    assert report.acceptance.uncovered_coverage_artifacts == ()
    assert report.acceptance.unknown_coverage_artifacts == ()

    unknown_report = build_chain_merge_report(
        "src/target.py",
        _chain(tmp_path),
        None,
        RecordedCoverageEvidenceSource({}),
    )
    assert unknown_report.acceptance.coverage_available is True
    assert unknown_report.acceptance.required_covered_artifacts == ()
    assert unknown_report.acceptance.uncovered_coverage_artifacts == ()
    assert unknown_report.acceptance.unknown_coverage_artifacts == ("function:target",)


def test_report_blocks_recorded_e710_gap(tmp_path):
    from maid_runner.core.chain_merge import ChainMergeVerdict, build_chain_merge_report
    from maid_runner.core.chain_merge_evidence import RecordedCoverageEvidenceSource

    _write_manifest(tmp_path)
    source = RecordedCoverageEvidenceSource(
        {("src/target.py", "function:target"): False}
    )

    report = build_chain_merge_report("src/target.py", _chain(tmp_path), None, source)

    assert report.verdict is ChainMergeVerdict.BLOCKED
    assert report.acceptance.uncovered_coverage_artifacts == ("function:target",)
    assert any("E710" in reason for reason in report.blocking_reasons)


def test_absent_coverage_source_preserves_unknown_fallback(tmp_path):
    from maid_runner.core.chain_merge import build_chain_merge_report

    _write_manifest(tmp_path)

    report = build_chain_merge_report("src/target.py", _chain(tmp_path), None)

    assert report.acceptance.coverage_available is False
    assert report.acceptance.required_covered_artifacts == ()
    assert report.acceptance.uncovered_coverage_artifacts == ()
    assert (
        report.acceptance.unknown_coverage_artifacts
        == report.acceptance.required_artifacts
    )


def test_chain_merge_cli_emits_recorded_coverage_acceptance(
    tmp_path, monkeypatch, capsys
):
    from maid_runner.cli.commands._main import main

    _write_manifest(tmp_path, covered=False)
    monkeypatch.chdir(tmp_path)
    assert _warm_coverage_cache(tmp_path) == 1
    capsys.readouterr()

    assert (
        main(
            [
                "chain",
                "merge",
                "src/target.py",
                "--json",
                "--manifest-dir",
                "manifests",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["verdict"] == "blocked"
    assert payload["acceptance"]["coverage_available"] is True
    assert payload["acceptance"]["uncovered_coverage_artifacts"] == ["function:target"]
    assert any("E710" in reason for reason in payload["blocking_reasons"])

    assert (
        main(
            [
                "chain",
                "merge",
                "src/target.py",
                "--manifest-dir",
                "manifests",
            ]
        )
        == 0
    )
    text = capsys.readouterr().out
    assert "coverage: recorded for 0/1 artifacts" in text
    assert "E710" in text
