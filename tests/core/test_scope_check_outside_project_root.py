"""Scope-check decisions for paths that live outside the project root."""

from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ACTIVE_MANIFEST = "manifests/demo.manifest.yaml"


def _make_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "repo"
    manifest_path = project_root / ACTIVE_MANIFEST
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        """schema: "2"
goal: "Demo outside-root task"
type: feature
created: "2026-10-08T00:00:00Z"
files:
  edit:
    - path: src/existing.py
      artifacts:
        - kind: function
          name: existing
validate:
  - uv run python -m pytest -q tests/test_existing.py
"""
    )
    return project_root


def test_scope_check_allows_absolute_path_outside_project_root(
    tmp_path: Path,
) -> None:
    from maid_runner.core.scope_check import scope_check_path

    project_root = _make_project(tmp_path)
    outside = tmp_path / "elsewhere" / "CLAUDE.md"

    decision = scope_check_path(str(outside), ACTIVE_MANIFEST, project_root)

    assert decision.decision == "allow"
    assert decision.reason == "outside-project-root"
    assert decision.active_manifest == ACTIVE_MANIFEST


def test_scope_check_allows_relative_escape_outside_project_root(
    tmp_path: Path,
) -> None:
    from maid_runner.core.scope_check import scope_check_path

    project_root = _make_project(tmp_path)

    decision = scope_check_path("../sibling/notes.md", ACTIVE_MANIFEST, project_root)

    assert decision.decision == "allow"
    assert decision.reason == "outside-project-root"


def test_scope_check_allows_outside_project_root_under_strict(
    tmp_path: Path,
) -> None:
    from maid_runner.core.scope_check import scope_check_path

    project_root = _make_project(tmp_path)
    outside = str(tmp_path / "plans" / "plan.md")

    decision = scope_check_path(outside, ACTIVE_MANIFEST, project_root, strict=True)

    assert (decision.decision, decision.reason) == ("allow", "outside-project-root")


def test_scope_check_strict_without_active_task_denies_outside_path(
    tmp_path: Path,
) -> None:
    from maid_runner.core.scope_check import scope_check_path

    project_root = _make_project(tmp_path)
    outside = str(tmp_path / "plans" / "plan.md")

    decision = scope_check_path(outside, None, project_root, strict=True)

    assert (decision.decision, decision.reason) == ("deny", "no-active-task")


def test_scope_check_still_denies_undeclared_absolute_path_inside_project_root(
    tmp_path: Path,
) -> None:
    from maid_runner.core.scope_check import scope_check_path

    project_root = _make_project(tmp_path)

    undeclared = scope_check_path(
        str(project_root / "src" / "other.py"), ACTIVE_MANIFEST, project_root
    )
    declared = scope_check_path(
        str(project_root / "src" / "existing.py"), ACTIVE_MANIFEST, project_root
    )

    assert undeclared.decision == "deny"
    assert undeclared.reason.startswith(f"out-of-scope for {ACTIVE_MANIFEST}")
    assert (declared.decision, declared.reason) == ("allow", "in-scope")


def test_scope_check_treats_symlink_escape_as_outside_project_root(
    tmp_path: Path,
) -> None:
    from maid_runner.core.scope_check import scope_check_path

    project_root = _make_project(tmp_path)
    external = tmp_path / "external"
    external.mkdir()
    (project_root / "linked").symlink_to(external, target_is_directory=True)

    decision = scope_check_path("linked/scratch.md", ACTIVE_MANIFEST, project_root)

    assert decision.decision == "allow"
    assert decision.reason == "outside-project-root"


def test_scope_check_skips_outside_allow_when_root_does_not_own_active_manifest(
    tmp_path: Path,
) -> None:
    from maid_runner.core.scope_check import scope_check_path

    project_root = _make_project(tmp_path)
    subdirectory = project_root / "src"
    subdirectory.mkdir()
    absolute_manifest = str(project_root / ACTIVE_MANIFEST)

    decision = scope_check_path(
        str(project_root / "README.md"),
        absolute_manifest,
        subdirectory,
        strict=True,
    )

    assert decision.decision == "deny"
    assert decision.reason != "outside-project-root"


def test_scope_check_skips_outside_allow_when_root_is_the_manifests_directory(
    tmp_path: Path,
) -> None:
    from maid_runner.core.scope_check import scope_check_path

    project_root = _make_project(tmp_path)
    absolute_manifest = str(project_root / ACTIVE_MANIFEST)

    decision = scope_check_path(
        str(project_root / "src" / "undeclared.py"),
        absolute_manifest,
        project_root / "manifests",
        strict=True,
    )

    assert decision.decision == "deny"
    assert decision.reason != "outside-project-root"


def test_scope_check_unloadable_active_manifest_fails_closed_under_strict(
    tmp_path: Path,
) -> None:
    from maid_runner.core.scope_check import scope_check_path

    project_root = _make_project(tmp_path)
    foreign_root = tmp_path / "foreign"
    foreign_root.mkdir()

    decision = scope_check_path(
        str(project_root / "src" / "other.py"),
        ACTIVE_MANIFEST,
        foreign_root,
        strict=True,
    )

    assert decision.decision == "deny"
    assert decision.reason.startswith("internal-error:")


def test_scope_check_unresolvable_path_is_not_allowed_as_outside_under_strict(
    tmp_path: Path,
) -> None:
    from maid_runner.core.scope_check import scope_check_path

    project_root = _make_project(tmp_path)

    decision = scope_check_path(
        "src/a\x00b.py", ACTIVE_MANIFEST, project_root, strict=True
    )

    assert decision.decision == "deny"
    assert decision.reason != "outside-project-root"


def test_hook_allows_claude_edit_envelope_for_file_outside_project_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands.hook import cmd_hook

    project_root = _make_project(tmp_path)
    plan_file = tmp_path / "home" / ".claude" / "plans" / "plan.md"
    monkeypatch.chdir(project_root)
    monkeypatch.setenv("MAID_ACTIVE_MANIFEST", ACTIVE_MANIFEST)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Edit",
                    "tool_input": {"file_path": str(plan_file)},
                }
            )
        ),
    )
    args = SimpleNamespace(
        hook_command="scope-check", stdin=True, path=None, strict=False
    )

    exit_code = cmd_hook(args)
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload == {
        "decision": "allow",
        "reason": "outside-project-root",
        "active_manifest": ACTIVE_MANIFEST,
    }


def test_hook_from_subdirectory_does_not_allow_repo_files_as_outside_under_strict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands.hook import cmd_hook

    project_root = _make_project(tmp_path)
    subdirectory = project_root / "src" / "nested"
    subdirectory.mkdir(parents=True)
    monkeypatch.chdir(subdirectory)
    monkeypatch.setenv("MAID_ACTIVE_MANIFEST", str(project_root / ACTIVE_MANIFEST))
    args = SimpleNamespace(
        hook_command="scope-check",
        stdin=False,
        path=str(project_root / "src" / "other.py"),
        strict=True,
    )

    exit_code = cmd_hook(args)
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["decision"] == "deny"
