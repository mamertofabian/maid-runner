"""Behavioral contract for `maid chain merge --verify-equivalence` (child 5)."""

from __future__ import annotations

import json


_MANIFEST = """schema: "2"
goal: "Track alpha"
type: feature
files:
  create:
    - path: src/foo.py
      artifacts:
        - kind: function
          name: alpha
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
"""


def _project(tmp_path):
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    (manifests / "a.manifest.yaml").write_text(_MANIFEST)
    return manifests


def _baseline_payload():
    return {
        "file_path": "src/foo.py",
        "verdict": "lean",
        "active_manifest_count": 1,
        "superseded_manifest_count": 0,
        "distinct_artifact_count": 1,
        "total_declaration_count": 1,
        "redundant_declaration_count": 0,
        "blocking_reasons": [],
        "acceptance": {
            "required_artifacts": ["function:alpha"],
            "detection_available": True,
            "required_detecting_nodeids": {
                "function:alpha": ["tests/old_test.py::test_alpha"]
            },
            "unknown_detection_artifacts": [],
            "coverage_available": True,
            "required_covered_artifacts": ["function:alpha"],
            "uncovered_coverage_artifacts": [],
            "unknown_coverage_artifacts": [],
        },
    }


def _write_baseline(tmp_path):
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(_baseline_payload()))
    return path


def _recorded_sources(monkeypatch, *, detecting=True, covered=True):
    from maid_runner.core import chain_merge_evidence

    class Detection:
        def detecting_nodeids_for(self, artifact_key):
            if detecting:
                return ("tests/new_test.py::test_consolidated",)
            return ()

    class Coverage:
        def coverage_for(self, file_path, artifact_key):
            return covered

    monkeypatch.setattr(
        chain_merge_evidence,
        "detection_source_for_file",
        lambda chain, file_path: Detection(),
    )
    monkeypatch.setattr(
        chain_merge_evidence,
        "coverage_source_for_file",
        lambda chain, file_path, manifest_dir: Coverage(),
    )


def test_chain_merge_verify_equivalence_json_passes_for_current_superset(
    tmp_path, capsys, monkeypatch
):
    from maid_runner.cli.commands._format import (
        format_chain_merge_equivalence_result,
    )
    from maid_runner.cli.commands._main import main
    from maid_runner.core.chain_merge_equivalence import MergeEquivalenceResult

    manifests = _project(tmp_path)
    baseline = _write_baseline(tmp_path)
    _recorded_sources(monkeypatch)

    rc = main(
        [
            "chain",
            "merge",
            "src/foo.py",
            "--verify-equivalence",
            str(baseline),
            "--dry-run",
            "--json",
            "--manifest-dir",
            str(manifests),
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "file_path": "src/foo.py",
        "success": True,
        "detection_regressions": [],
        "coverage_regressions": [],
        "evidence_regressions": [],
        "errors": [],
    }
    direct = format_chain_merge_equivalence_result(
        MergeEquivalenceResult(
            file_path="src/foo.py",
            success=True,
            detection_regressions=(),
            coverage_regressions=(),
            evidence_regressions=(),
            errors=(),
        ),
        json_mode=True,
    )
    assert json.loads(direct) == payload
    text = format_chain_merge_equivalence_result(
        MergeEquivalenceResult(
            file_path="src/foo.py",
            success=True,
            detection_regressions=(),
            coverage_regressions=(),
            evidence_regressions=(),
            errors=(),
        )
    )
    assert "src/foo.py" in text
    assert "equivalent" in text.lower()


def test_chain_merge_verify_equivalence_returns_one_for_regression(
    tmp_path, capsys, monkeypatch
):
    from maid_runner.cli.commands._main import main

    manifests = _project(tmp_path)
    baseline = _write_baseline(tmp_path)
    _recorded_sources(monkeypatch, detecting=False)

    rc = main(
        [
            "chain",
            "merge",
            "src/foo.py",
            "--verify-equivalence",
            str(baseline),
            "--json",
            "--manifest-dir",
            str(manifests),
        ]
    )

    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert payload["detection_regressions"] == ["function:alpha"]
    assert payload["errors"][0]["code"] == "E715"
    assert payload["errors"][0]["severity"] == "error"

    text_rc = main(
        [
            "chain",
            "merge",
            "src/foo.py",
            "--verify-equivalence",
            str(baseline),
            "--manifest-dir",
            str(manifests),
        ]
    )
    assert text_rc == 1
    text_output = capsys.readouterr().out
    assert "E715" in text_output
    assert "function:alpha" in text_output


def test_chain_merge_verify_equivalence_rejects_invalid_baseline_or_conflicting_mode(
    tmp_path, capsys
):
    from maid_runner.cli.commands._main import main

    manifests = _project(tmp_path)
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json")

    invalid_rc = main(
        [
            "chain",
            "merge",
            "src/foo.py",
            "--verify-equivalence",
            str(invalid),
            "--manifest-dir",
            str(manifests),
        ]
    )
    assert invalid_rc == 2
    invalid_capture = capsys.readouterr()
    assert "baseline" in invalid_capture.err.lower()
    assert invalid_capture.out == ""

    missing_rc = main(
        [
            "chain",
            "merge",
            "src/foo.py",
            "--verify-equivalence",
            str(tmp_path / "missing.json"),
            "--manifest-dir",
            str(manifests),
        ]
    )
    assert missing_rc == 2
    missing_capture = capsys.readouterr()
    assert "baseline" in missing_capture.err.lower()
    assert missing_capture.out == ""

    malformed = tmp_path / "malformed.json"
    malformed.write_text(json.dumps({"file_path": "src/foo.py", "acceptance": []}))
    malformed_rc = main(
        [
            "chain",
            "merge",
            "src/foo.py",
            "--verify-equivalence",
            str(malformed),
            "--manifest-dir",
            str(manifests),
        ]
    )
    assert malformed_rc == 2
    malformed_capture = capsys.readouterr()
    assert "baseline" in malformed_capture.err.lower()
    assert malformed_capture.out == ""

    mismatch = _write_baseline(tmp_path)
    mismatch_payload = json.loads(mismatch.read_text())
    mismatch_payload["file_path"] = "src/different.py"
    mismatch.write_text(json.dumps(mismatch_payload))
    mismatch_rc = main(
        [
            "chain",
            "merge",
            "src/foo.py",
            "--verify-equivalence",
            str(mismatch),
            "--manifest-dir",
            str(manifests),
        ]
    )
    assert mismatch_rc == 2
    mismatch_capture = capsys.readouterr()
    assert "src/different.py" in mismatch_capture.err
    assert mismatch_capture.out == ""

    baseline = _write_baseline(tmp_path)
    conflict_rc = main(
        [
            "chain",
            "merge",
            "src/foo.py",
            "--verify-equivalence",
            str(baseline),
            "--apply",
            "--manifest-dir",
            str(manifests),
        ]
    )
    assert conflict_rc == 2
    conflict_capture = capsys.readouterr()
    assert "cannot be combined" in conflict_capture.err.lower()
    assert conflict_capture.out == ""

    all_conflict_rc = main(
        [
            "chain",
            "merge",
            "src/foo.py",
            "--verify-equivalence",
            str(baseline),
            "--all",
            "--manifest-dir",
            str(manifests),
        ]
    )
    assert all_conflict_rc == 2
    all_capture = capsys.readouterr()
    assert "cannot be combined" in all_capture.err.lower()
    assert all_capture.out == ""


def test_chain_merge_verify_equivalence_rejects_non_report_and_inconsistent_evidence(
    tmp_path, capsys
):
    from maid_runner.cli.commands._main import main

    manifests = _project(tmp_path)
    baseline = tmp_path / "baseline.json"

    invalid_payloads = []
    minimal = {
        "file_path": "src/foo.py",
        "acceptance": _baseline_payload()["acceptance"],
    }
    invalid_payloads.append(minimal)

    duplicate_artifact = _baseline_payload()
    duplicate_artifact["acceptance"]["required_artifacts"] = [
        "function:alpha",
        "function:alpha",
    ]
    invalid_payloads.append(duplicate_artifact)

    extra_evidence = _baseline_payload()
    extra_evidence["acceptance"]["required_detecting_nodeids"]["function:ghost"] = [
        "tests/old_test.py::test_ghost"
    ]
    invalid_payloads.append(extra_evidence)

    overlapping_coverage = _baseline_payload()
    overlapping_coverage["acceptance"]["uncovered_coverage_artifacts"] = [
        "function:alpha"
    ]
    invalid_payloads.append(overlapping_coverage)

    blank_nodeid = _baseline_payload()
    blank_nodeid["acceptance"]["required_detecting_nodeids"]["function:alpha"] = [""]
    invalid_payloads.append(blank_nodeid)

    unavailable_with_recorded_detection = _baseline_payload()
    unavailable_with_recorded_detection["acceptance"]["detection_available"] = False
    invalid_payloads.append(unavailable_with_recorded_detection)

    for payload in invalid_payloads:
        baseline.write_text(json.dumps(payload))
        rc = main(
            [
                "chain",
                "merge",
                "src/foo.py",
                "--verify-equivalence",
                str(baseline),
                "--json",
                "--manifest-dir",
                str(manifests),
            ]
        )
        assert rc == 2
        output = json.loads(capsys.readouterr().out)
        assert "baseline" in output["error"].lower()

    valid_text = json.dumps(_baseline_payload())
    duplicate_key_text = valid_text.replace(
        '"required_artifacts": ["function:alpha"]',
        '"required_artifacts": ["function:alpha"], '
        '"required_artifacts": ["function:alpha"]',
    )
    baseline.write_text(duplicate_key_text)
    duplicate_key_rc = main(
        [
            "chain",
            "merge",
            "src/foo.py",
            "--verify-equivalence",
            str(baseline),
            "--json",
            "--manifest-dir",
            str(manifests),
        ]
    )
    assert duplicate_key_rc == 2
    assert "baseline" in json.loads(capsys.readouterr().out)["error"].lower()


def test_chain_merge_verify_equivalence_blocks_structurally_blocked_baseline(
    tmp_path, capsys, monkeypatch
):
    from maid_runner.cli.commands._main import main

    manifests = _project(tmp_path)
    _recorded_sources(monkeypatch)
    payload = _baseline_payload()
    payload.update(
        {
            "verdict": "blocked",
            "active_manifest_count": 0,
            "distinct_artifact_count": 0,
            "total_declaration_count": 0,
            "blocking_reasons": ["Nothing to merge."],
        }
    )
    payload["acceptance"] = {
        "required_artifacts": [],
        "detection_available": True,
        "required_detecting_nodeids": {},
        "unknown_detection_artifacts": [],
        "coverage_available": True,
        "required_covered_artifacts": [],
        "uncovered_coverage_artifacts": [],
        "unknown_coverage_artifacts": [],
    }
    baseline = tmp_path / "blocked.json"
    baseline.write_text(json.dumps(payload))

    rc = main(
        [
            "chain",
            "merge",
            "src/foo.py",
            "--verify-equivalence",
            str(baseline),
            "--json",
            "--manifest-dir",
            str(manifests),
        ]
    )

    assert rc == 1
    output = json.loads(capsys.readouterr().out)
    assert output["success"] is False
    assert output["evidence_regressions"] == ["baseline:contract"]
    assert output["errors"][0]["code"] == "E715"

    complete_blocked = _baseline_payload()
    complete_blocked["verdict"] = "blocked"
    complete_blocked["blocking_reasons"] = ["Baseline is not eligible."]
    baseline.write_text(json.dumps(complete_blocked))
    complete_rc = main(
        [
            "chain",
            "merge",
            "src/foo.py",
            "--verify-equivalence",
            str(baseline),
            "--json",
            "--manifest-dir",
            str(manifests),
        ]
    )
    assert complete_rc == 1
    complete_output = json.loads(capsys.readouterr().out)
    assert complete_output["success"] is False
    assert "baseline:verdict" in complete_output["evidence_regressions"]
    assert {error["code"] for error in complete_output["errors"]} == {"E715"}
