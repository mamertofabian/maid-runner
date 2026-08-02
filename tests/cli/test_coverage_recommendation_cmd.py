from __future__ import annotations

import json
from pathlib import Path

from maid_runner.cli.commands._main import build_parser, main


def test_bootstrap_model_parser_defaults_to_legacy_and_registers_risk_flags() -> None:
    parser = build_parser()

    legacy = parser.parse_args(["bootstrap", "--rank"])
    risk = parser.parse_args(
        [
            "bootstrap",
            "--rank",
            "--model",
            "risk-v1",
            "--explain",
            "src/app.py",
        ]
    )

    assert legacy.model == "legacy-v1"
    assert legacy.explain is None
    assert legacy.deep is False
    assert risk.model == "risk-v1"
    assert risk.explain == "src/app.py"


def test_risk_v1_json_dispatches_through_main(tmp_path: Path, capsys) -> None:
    source = tmp_path / "src" / "app.py"
    source.parent.mkdir()
    source.write_text("def app():\n    return 1\n")

    exit_code = main(
        [
            "bootstrap",
            str(tmp_path),
            "--rank",
            "--model",
            "risk-v1",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["model"] == "risk-v1"
    assert payload["total_candidates"] == 1
    candidate = payload["candidates"][0]
    assert candidate["rank"] == 1
    assert candidate["path"] == "src/app.py"
    assert candidate["coverage_status"] == "undeclared"
    assert isinstance(candidate["signals"], dict)
    assert candidate["score"] >= 0
    assert candidate["priority"] in {"critical", "high", "medium", "low"}
    assert candidate["confidence"] in {"high", "medium", "low"}


def test_risk_v1_human_output_carries_evidence(tmp_path: Path, capsys) -> None:
    source = tmp_path / "src" / "app.py"
    source.parent.mkdir()
    source.write_text("def app():\n    return 1\n")

    exit_code = main(
        [
            "bootstrap",
            str(tmp_path),
            "--rank",
            "--model",
            "risk-v1",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Coverage recommendations: 1 of 1" in output
    assert "src/app.py" in output
    assert "Coverage gap" in output
    assert "Recommended action:" in output


def test_risk_v1_explain_tracked_file_is_structured_non_candidate(
    tmp_path: Path, capsys
) -> None:
    source = tmp_path / "src" / "tracked.py"
    source.parent.mkdir()
    source.write_text("def tracked():\n    return 1\n")
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    (manifests / "tracked.manifest.yaml").write_text(
        """
schema: "2"
goal: Track source
type: feature
created: "2026-07-31T00:00:00Z"
files:
  edit:
    - path: src/tracked.py
      artifacts:
        - kind: function
          name: tracked
validate:
  - pytest tests/ -q
""".lstrip()
    )

    exit_code = main(
        [
            "bootstrap",
            str(tmp_path),
            "--rank",
            "--model",
            "risk-v1",
            "--explain",
            "src/tracked.py",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "model": "risk-v1",
        "path": "src/tracked.py",
        "eligible": False,
        "coverage_status": "tracked",
        "exclusion_reason": "fully tracked",
        "recommendation": None,
    }


def test_risk_only_flags_fail_visibly_without_risk_rank(capsys) -> None:
    exit_code = main(["bootstrap", "--model", "risk-v1"])

    assert exit_code == 2
    assert "--model risk-v1 requires --rank" in capsys.readouterr().err
