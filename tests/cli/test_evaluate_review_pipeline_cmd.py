"""Behavioral tests for `maid evaluate prompt|validate|render`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from maid_runner.cli.commands._main import build_parser, main


def test_prompt_writes_request_json_with_evidence_items(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from maid_runner.cli.commands.evaluate import cmd_evaluate

    monkeypatch.chdir(tmp_path)
    manifest_path = _write_project(tmp_path)

    assert main(["evaluate", "prompt", str(manifest_path)]) == 0

    request_path = tmp_path / ".maid" / "run-review-request.json"
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    evidence_ids = [item["evidence_id"] for item in payload["evidence_items"]]
    assert payload["manifest_slug"] == "demo-task"
    assert payload["evaluation"]["manifest_slug"] == "demo-task"
    assert "revision-1" in evidence_ids
    assert "outcome-lesson-1" in evidence_ids
    assert "finding-1" in evidence_ids
    assert "cite evidence ids" in payload["instructions"].lower()
    assert callable(cmd_evaluate)


def test_validate_fails_nonzero_listing_fabrication_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.chdir(tmp_path)
    manifest_path = _write_project(tmp_path)
    request_path = tmp_path / ".maid" / "request.json"
    assert (
        main(["evaluate", "prompt", str(manifest_path), "--output", str(request_path)])
        == 0
    )
    request = json.loads(request_path.read_text(encoding="utf-8"))
    valid_review = tmp_path / ".maid" / "valid-review.json"
    invalid_review = tmp_path / ".maid" / "invalid-review.json"
    _write_json(valid_review, _faithful_review(request))
    _write_json(
        invalid_review,
        {
            "confidence": "certain",
            "findings": [
                {
                    "severity": "critical",
                    "summary": "src/fabricated.py is untested.",
                    "citations": ["missing-id"],
                }
            ],
        },
    )

    assert (
        main(
            [
                "evaluate",
                "validate",
                str(invalid_review),
                "--request",
                str(request_path),
            ]
        )
        == 2
    )
    error = capsys.readouterr().err
    assert "invalid confidence" in error
    assert "invalid severity" in error
    assert "unknown evidence id" in error
    assert "unevidenced file path" in error

    assert (
        main(
            ["evaluate", "validate", str(valid_review), "--request", str(request_path)]
        )
        == 0
    )
    assert "valid" in capsys.readouterr().out.lower()


def test_render_fails_closed_on_invalid_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.chdir(tmp_path)
    manifest_path = _write_project(tmp_path)
    assert main(["evaluate", "prompt", str(manifest_path)]) == 0
    request_path = tmp_path / ".maid" / "run-review-request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    invalid_review = tmp_path / ".maid" / "invalid-review.json"
    valid_review = tmp_path / ".maid" / "valid-review.json"
    _write_json(
        invalid_review,
        {
            "confidence": "medium",
            "findings": [
                {"severity": "warning", "summary": "No citation", "citations": []}
            ],
        },
    )
    _write_json(valid_review, _faithful_review(request))

    assert (
        main(
            ["evaluate", "render", str(invalid_review), "--request", str(request_path)]
        )
        == 2
    )
    default_output = tmp_path / ".maid" / "run-reviews" / "demo-task.md"
    assert not default_output.exists()
    assert "missing evidence citations" in capsys.readouterr().err

    assert (
        main(["evaluate", "render", str(valid_review), "--request", str(request_path)])
        == 0
    )
    markdown = default_output.read_text(encoding="utf-8")
    assert markdown.startswith("# LLM-Generated Advisory Run Review\n")
    assert "## Deterministic Counts" in markdown


def test_prompt_diff_file_becomes_diff_evidence_item(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    manifest_path = _write_project(tmp_path)
    diff_path = tmp_path / "review.diff"
    diff_path.write_text(
        "diff --git a/src/demo.py b/src/demo.py\n+return 2\n", encoding="utf-8"
    )
    request_path = tmp_path / ".maid" / "request.json"

    assert (
        main(
            [
                "evaluate",
                "prompt",
                str(manifest_path),
                "--diff-file",
                str(diff_path),
                "--output",
                str(request_path),
            ]
        )
        == 0
    )

    payload = json.loads(request_path.read_text(encoding="utf-8"))
    diff_item = next(
        item for item in payload["evidence_items"] if item["evidence_id"] == "diff"
    )
    assert diff_item["kind"] == "diff"
    assert "diff --git" in diff_item["text"]


def test_prompt_project_root_resolves_relative_manifest_from_other_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    other_cwd = tmp_path / "outside"
    other_cwd.mkdir()
    _write_project(project_root)
    request_path = tmp_path / "request.json"
    monkeypatch.chdir(other_cwd)

    assert (
        main(
            [
                "evaluate",
                "prompt",
                "manifests/demo-task.manifest.yaml",
                "--project-root",
                str(project_root),
                "--output",
                str(request_path),
            ]
        )
        == 0
    )

    payload = json.loads(request_path.read_text(encoding="utf-8"))
    evidence_ids = {item["evidence_id"] for item in payload["evidence_items"]}
    assert payload["evaluation"]["manifest_path"] == "manifests/demo-task.manifest.yaml"
    assert "revision-1" in evidence_ids


def test_validate_fails_closed_on_malformed_request_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.chdir(tmp_path)
    review_path = tmp_path / ".maid" / "review.json"
    request_path = tmp_path / ".maid" / "request.json"
    _write_json(
        review_path,
        {
            "confidence": "high",
            "findings": [
                {
                    "severity": "info",
                    "summary": "Looks grounded.",
                    "citations": ["123"],
                }
            ],
        },
    )
    _write_json(
        request_path,
        {
            "schema_version": "1",
            "manifest_slug": "demo-task",
            "evaluation": {},
            "evidence_items": [
                {"evidence_id": 123, "kind": "finding", "text": "Looks grounded."},
                "not an evidence item",
            ],
            "instructions": "cite evidence ids",
        },
    )

    assert (
        main(["evaluate", "validate", str(review_path), "--request", str(request_path)])
        == 2
    )
    assert "Malformed run review request" in capsys.readouterr().err


def test_pipeline_offers_no_model_or_credential_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = build_parser()
    for subcommand, args in {
        "prompt": ["manifests/demo-task.manifest.yaml"],
        "validate": ["review.json", "--request", "request.json"],
        "render": ["review.json", "--request", "request.json"],
    }.items():
        parsed = parser.parse_args(["evaluate", subcommand, *args])
        names = vars(parsed)
        assert "provider" not in names
        assert "model" not in names
        assert "api_key" not in names
        assert "url" not in names

    monkeypatch.chdir(tmp_path)
    manifest_path = _write_project(tmp_path)
    request_path = tmp_path / ".maid" / "request.json"
    assert (
        main(["evaluate", "prompt", str(manifest_path), "--output", str(request_path)])
        == 0
    )
    request = json.loads(request_path.read_text(encoding="utf-8"))
    review_path = tmp_path / ".maid" / "review.json"
    _write_json(review_path, _faithful_review(request))
    assert (
        main(["evaluate", "validate", str(review_path), "--request", str(request_path)])
        == 0
    )
    assert (
        main(["evaluate", "render", str(review_path), "--request", str(request_path)])
        == 0
    )


def _write_project(project_root: Path) -> Path:
    (project_root / "src").mkdir(parents=True)
    (project_root / "tests").mkdir()
    (project_root / "src" / "demo.py").write_text(
        "def demo() -> int:\n    return 1\n", encoding="utf-8"
    )
    (project_root / "tests" / "test_demo.py").write_text(
        "from src.demo import demo\n\n\ndef test_demo_contract():\n    assert demo() == 1\n",
        encoding="utf-8",
    )
    manifest_path = project_root / "manifests" / "demo-task.manifest.yaml"
    manifest_path.parent.mkdir()
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Demo task",
                "type": "feature",
                "created": "2026-07-06T00:00:00Z",
                "files": {
                    "create": [
                        {
                            "path": "src/demo.py",
                            "artifacts": [{"kind": "function", "name": "demo"}],
                        }
                    ],
                    "read": ["tests/test_demo.py"],
                },
                "validate": ["uv run pytest -q tests/test_demo.py"],
                "outcome": {
                    "status": "completed",
                    "summary": "Done",
                    "lessons": [
                        {
                            "lesson_type": "validation-evidence",
                            "summary": "Keep validation evidence grounded.",
                        }
                    ],
                    "review_notes": [
                        {
                            "source": "implementation-review",
                            "severity": "info",
                            "summary": "Review found no blockers.",
                        }
                    ],
                    "validation": [
                        {
                            "command": [
                                "uv",
                                "run",
                                "pytest",
                                "-q",
                                "tests/test_demo.py",
                            ],
                            "status": "passed",
                            "summary": "Focused tests passed.",
                        }
                    ],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    _write_lock(project_root)
    return manifest_path


def _write_lock(project_root: Path) -> None:
    lock_path = project_root / ".maid" / "plan-locks" / "demo-task.lock.json"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(
        json.dumps(
            {
                "manifest_path": "manifests/demo-task.manifest.yaml",
                "manifest_hash": "hash",
                "test_hashes": {},
                "created_at": "2026-07-06T00:00:00Z",
                "revision": 2,
                "revisions": [
                    {
                        "prior_manifest_hash": "old",
                        "prior_test_hashes": {},
                        "revised_at": "2026-07-06T00:00:00Z",
                        "reason": "Removed old fallback test.",
                        "agent": None,
                        "contract_delta": {
                            "artifacts_added": [],
                            "artifacts_removed": [],
                            "files_added": [],
                            "files_removed": [],
                            "validate_commands_added": [],
                            "validate_commands_removed": [
                                "uv run pytest -q tests/old_demo.py"
                            ],
                        },
                    }
                ],
                "red_evidence": {
                    "red": True,
                    "captured_at": "2026-07-06T00:00:00Z",
                    "commands": [
                        {
                            "command": "uv run pytest -q tests/test_demo.py",
                            "exit_code": 1,
                            "output_tail": "assert 1 == 2",
                            "classification": "red",
                        }
                    ],
                },
                "agent": {"model": "gpt-5-codex", "source": "flags"},
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _faithful_review(request: dict) -> dict:
    first_evidence_id = request["evidence_items"][0]["evidence_id"]
    return {
        "confidence": "medium",
        "summary": "The request evidence supports this advisory finding.",
        "findings": [
            {
                "severity": "warning",
                "summary": "Review cites only supplied evidence.",
                "citations": [first_evidence_id],
            }
        ],
    }


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
