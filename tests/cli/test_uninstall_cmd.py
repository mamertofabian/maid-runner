"""Behavioral contract for ownership-safe MAID payload uninstall commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maid_runner.cli.commands._main import main


MAID_SECTION_START = "<!-- BEGIN MAID RUNNER -->"
MAID_SECTION_END = "<!-- END MAID RUNNER -->"
PRE_COMMIT_START = "# BEGIN MAID RUNNER PRE-COMMIT"
PRE_COMMIT_END = "# END MAID RUNNER PRE-COMMIT"
GITIGNORE_START = "# BEGIN MAID RUNNER GENERATED FILES"
GITIGNORE_END = "# END MAID RUNNER GENERATED FILES"


def _platform_supports_symlinks(tmp_path: Path) -> bool:
    probe = tmp_path / "_symlink_probe"
    try:
        probe.symlink_to(tmp_path)
    except (OSError, NotImplementedError):
        return False
    probe.unlink()
    return True


def _commands(value: object) -> list[str]:
    if isinstance(value, dict):
        commands = [value["command"]] if isinstance(value.get("command"), str) else []
        for child in value.values():
            commands.extend(_commands(child))
        return commands
    if isinstance(value, list):
        return [command for child in value for command in _commands(child)]
    return []


def test_uninstall_onboard_skill_removes_only_owned_user_level_skills(
    tmp_path: Path,
) -> None:
    from maid_runner.core.uninstall import UninstallReport
    from maid_runner.core.skill_install import (
        install_onboard_skill,
        uninstall_onboard_skill,
    )

    payload = tmp_path / "payload"
    for tool in ("claude", "codex"):
        source = payload / tool / "maid-onboard"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text(f"{tool} onboard\n")
    home = tmp_path / "home"
    install_onboard_skill(home, payload, False)
    custom = home / ".codex" / "skills" / "custom-skill" / "SKILL.md"
    custom.parent.mkdir(parents=True)
    custom.write_text("keep me\n")

    preview: UninstallReport = uninstall_onboard_skill(home, payload, True)
    assert (home / ".claude" / "skills" / "maid-onboard").is_dir()
    report: UninstallReport = uninstall_onboard_skill(home, payload, False)

    assert preview == report
    assert isinstance(report, UninstallReport)
    assert sorted(report.removed) == [
        ".claude/skills/maid-onboard",
        ".codex/skills/maid-onboard",
    ]
    assert report.preserved == []
    assert report.missing == []
    assert not (home / ".claude" / "skills" / "maid-onboard").exists()
    assert not (home / ".codex" / "skills" / "maid-onboard").exists()
    assert custom.read_text() == "keep me\n"


def test_uninstall_onboard_skill_preserves_modified_user_level_copy(
    tmp_path: Path,
) -> None:
    from maid_runner.core.uninstall import UninstallReport
    from maid_runner.core.skill_install import (
        install_onboard_skill,
        uninstall_onboard_skill,
    )

    payload = tmp_path / "payload"
    for tool in ("claude", "codex"):
        source = payload / tool / "maid-onboard"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text(f"{tool} onboard\n")
    home = tmp_path / "home"
    install_onboard_skill(home, payload, False)
    modified = home / ".codex" / "skills" / "maid-onboard" / "SKILL.md"
    modified.write_text("local customization\n")

    preview: UninstallReport = uninstall_onboard_skill(home, payload, True)
    report: UninstallReport = uninstall_onboard_skill(home, payload, False)

    assert preview == report
    assert ".claude/skills/maid-onboard" in report.removed
    assert ".codex/skills/maid-onboard" in report.preserved
    assert modified.read_text() == "local customization\n"


def test_uninstall_onboard_skill_removes_owned_links_without_following_targets(
    tmp_path: Path,
) -> None:
    from maid_runner.core.uninstall import UninstallReport
    from maid_runner.core.skill_install import (
        install_onboard_skill,
        uninstall_onboard_skill,
    )

    payload = tmp_path / "payload"
    for tool in ("claude", "codex"):
        source = payload / tool / "maid-onboard"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text(f"{tool} onboard\n")
    home = tmp_path / "home"
    if not _platform_supports_symlinks(tmp_path):
        pytest.skip("platform does not support symbolic links")
    install_onboard_skill(home, payload, True)
    installed = home / ".codex" / "skills" / "maid-onboard" / "SKILL.md"
    assert installed.is_symlink()
    redirected_target = tmp_path / "redirected-skill.md"
    redirected_target.write_text("local redirected skill\n")
    installed.unlink()
    installed.symlink_to(redirected_target)

    report: UninstallReport = uninstall_onboard_skill(home, payload, False)

    assert ".claude/skills/maid-onboard" in report.removed
    assert ".codex/skills/maid-onboard" in report.preserved
    assert installed.is_symlink()
    assert redirected_target.read_text() == "local redirected skill\n"
    assert (payload / "codex" / "maid-onboard" / "SKILL.md").read_text() == (
        "codex onboard\n"
    )

    for tool, boundary in (
        ("claude", "agent-root"),
        ("claude", "skills"),
        ("codex", "agent-root"),
        ("codex", "skills"),
    ):
        boundary_home = tmp_path / f"{tool}-{boundary}"
        install_onboard_skill(boundary_home, payload, False)
        linked_parent = (
            boundary_home / f".{tool}"
            if boundary == "agent-root"
            else boundary_home / f".{tool}" / "skills"
        )
        outside_parent = tmp_path / f"outside-{tool}-{boundary}"
        linked_parent.rename(outside_parent)
        linked_parent.symlink_to(outside_parent, target_is_directory=True)
        outside_skill = outside_parent / (
            Path("skills/maid-onboard/SKILL.md")
            if boundary == "agent-root"
            else Path("maid-onboard/SKILL.md")
        )

        boundary_report = uninstall_onboard_skill(boundary_home, payload, False)

        assert f".{tool}/skills/maid-onboard" in boundary_report.preserved
        assert outside_skill.is_file()

    late_change_home = tmp_path / "late-change-home"
    install_onboard_skill(late_change_home, payload, False)
    import maid_runner.core.skill_install as skill_install_module

    original_remove = skill_install_module._remove_owned_skill_tree

    def modify_after_comparison(target_root, destination, source):
        (destination / "concurrent-user-file.txt").write_text("keep concurrent\n")
        return original_remove(target_root, destination, source)

    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(
            skill_install_module, "_remove_owned_skill_tree", modify_after_comparison
        )
        with pytest.raises(ValueError, match="changed after uninstall planning"):
            uninstall_onboard_skill(late_change_home, payload, False)
    assert (
        late_change_home
        / ".claude"
        / "skills"
        / "maid-onboard"
        / "concurrent-user-file.txt"
    ).is_file()

    fallback_home = tmp_path / "fallback-home"
    install_onboard_skill(fallback_home, payload, False)
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(
            skill_install_module,
            "_supports_descriptor_relative_skill_removal",
            lambda: False,
        )
        with pytest.raises(OSError, match="refusing pathname-based mutation"):
            uninstall_onboard_skill(fallback_home, payload, False)
    assert (
        fallback_home / ".claude" / "skills" / "maid-onboard" / "SKILL.md"
    ).is_file()


def test_skills_uninstall_dry_run_is_non_mutating_and_repeatable(
    tmp_path: Path, capsys
) -> None:
    home = tmp_path / "home"
    assert main(["skills", "install", "--target-root", str(home)]) == 0
    capsys.readouterr()

    assert main(["skills", "uninstall", "--target-root", str(home), "--dry-run"]) == 0
    dry_run_output = capsys.readouterr().out
    assert "Would remove" in dry_run_output
    assert (home / ".claude" / "skills" / "maid-onboard").is_dir()
    assert (home / ".codex" / "skills" / "maid-onboard").is_dir()

    assert main(["skills", "uninstall", "--target-root", str(home)]) == 0
    assert "Removed" in capsys.readouterr().out
    assert main(["skills", "uninstall", "--target-root", str(home)]) == 0
    assert "No installed" in capsys.readouterr().out


def test_init_uninstall_removes_all_owned_agent_payloads_and_guidance(
    tmp_path: Path, monkeypatch
) -> None:
    from maid_runner.cli.commands.init import uninstall_init_payload
    from maid_runner.core.uninstall import UninstallReport

    monkeypatch.chdir(tmp_path)
    claude_settings = tmp_path / ".claude" / "settings.json"
    claude_settings.parent.mkdir(parents=True)
    claude_settings.write_text(
        json.dumps(
            {
                "permissions": {"allow": ["Bash(pytest:*)"]},
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Read",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python user-hook.py",
                                }
                            ],
                        }
                    ]
                },
            }
        )
    )
    (tmp_path / "CLAUDE.md").write_text("Claude prefix\n\nClaude suffix\n")
    (tmp_path / "AGENTS.md").write_text("Agent prefix\n\nAgent suffix\n")
    assert main(["init", "--tool", "claude"]) == 0
    assert main(["init", "--tool", "codex", "--force"]) == 0
    assert main(["init", "--tool", "cursor", "--force"]) == 0
    custom = tmp_path / ".codex" / "skills" / "custom-skill" / "SKILL.md"
    custom.parent.mkdir(parents=True)
    custom.write_text("keep custom\n")
    merged_settings = json.loads(claude_settings.read_text())
    maid_entry = next(
        entry
        for entry in merged_settings["hooks"]["PreToolUse"]
        if "maid hook scope-check --stdin" in _commands(entry)
    )
    maid_entry["hooks"].append(
        {"type": "command", "command": "python sibling-user-hook.py"}
    )
    unrelated_empty = {
        "matcher": "UserTool",
        "hooks": [],
        "metadata": {"owner": "user"},
    }
    merged_settings["hooks"]["PreToolUse"].append(unrelated_empty)
    merged_settings["hooks"]["UserPromptSubmit"] = []
    claude_settings.write_text(json.dumps(merged_settings))

    preview: UninstallReport = uninstall_init_payload(
        tmp_path, ("claude", "codex", "cursor"), True
    )
    assert (tmp_path / ".claude" / "manifest.json").is_file()
    assert (tmp_path / ".codex" / "manifest.json").is_file()
    assert (tmp_path / ".cursor" / "manifest.json").is_file()
    report: UninstallReport = uninstall_init_payload(
        tmp_path, ("claude", "codex", "cursor"), False
    )

    assert preview == report
    assert ".claude/manifest.json" in report.removed
    assert ".codex/manifest.json" in report.removed
    assert ".cursor/manifest.json" in report.removed
    assert not (tmp_path / ".claude" / "skills" / "maid-planner").exists()
    assert not (tmp_path / ".codex" / "skills" / "maid-planner").exists()
    assert custom.read_text() == "keep custom\n"
    settings = json.loads(claude_settings.read_text())
    assert settings["permissions"] == {"allow": ["Bash(pytest:*)"]}
    assert "maid hook scope-check --stdin" not in _commands(settings)
    assert "python user-hook.py" in _commands(settings)
    assert "python sibling-user-hook.py" in _commands(settings)
    assert unrelated_empty in settings["hooks"]["PreToolUse"]
    assert settings["hooks"]["UserPromptSubmit"] == []
    assert MAID_SECTION_START not in (tmp_path / "CLAUDE.md").read_text()
    assert MAID_SECTION_END not in (tmp_path / "CLAUDE.md").read_text()
    assert (tmp_path / "CLAUDE.md").read_text().split() == [
        "Claude",
        "prefix",
        "Claude",
        "suffix",
    ]
    assert MAID_SECTION_START not in (tmp_path / "AGENTS.md").read_text()
    assert MAID_SECTION_END not in (tmp_path / "AGENTS.md").read_text()


def test_init_uninstall_removes_shared_scaffold_but_preserves_project_data(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".gitignore").write_text("dist/\n")
    (tmp_path / ".gitignore").chmod(0o640)
    (tmp_path / ".pre-commit-config.yaml").write_text(
        "repos:\n"
        "  - repo: https://example.com/user-hooks\n"
        "    rev: v1\n"
        "    hooks:\n"
        "      - id: user-hook\n"
    )
    assert main(["init", "--tool", "generic"]) == 0
    user_manifest = tmp_path / "manifests" / "keep.manifest.yaml"
    user_manifest.write_text("schema: '2'\ngoal: keep\ntype: feature\ncreated: now\n")
    user_draft = tmp_path / "manifests" / "drafts" / "keep.md"
    user_draft.write_text("keep draft\n")

    assert main(["init", "--uninstall"]) == 0

    assert not (tmp_path / ".maidrc.yaml").exists()
    assert not (tmp_path / "docs" / "draft-manifest-workflow.md").exists()
    assert not (tmp_path / "docs" / "manifest-outcome-records.md").exists()
    assert not (tmp_path / "manifests" / "drafts" / "README.md").exists()
    assert user_manifest.read_text().startswith("schema")
    assert user_draft.read_text() == "keep draft\n"
    gitignore = (tmp_path / ".gitignore").read_text()
    assert gitignore.strip() == "dist/"
    assert GITIGNORE_START not in gitignore
    assert GITIGNORE_END not in gitignore
    assert (tmp_path / ".gitignore").stat().st_mode & 0o777 == 0o640
    pre_commit = (tmp_path / ".pre-commit-config.yaml").read_text()
    assert "https://example.com/user-hooks" in pre_commit
    assert "user-hook" in pre_commit
    assert PRE_COMMIT_START not in pre_commit
    assert PRE_COMMIT_END not in pre_commit
    assert "maid-verify" not in pre_commit


def test_init_uninstall_preserves_modified_generated_files_and_reports_them(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--tool", "generic"]) == 0
    config = tmp_path / ".maidrc.yaml"
    config.write_text(config.read_text() + "custom: true\n")
    workflow = tmp_path / "docs" / "draft-manifest-workflow.md"
    workflow.write_text(workflow.read_text() + "\nLocal policy.\n")

    from maid_runner.cli.commands.init import uninstall_init_payload
    from maid_runner.core.uninstall import UninstallReport

    preview: UninstallReport = uninstall_init_payload(tmp_path, ("generic",), True)
    assert config.is_file()
    report: UninstallReport = uninstall_init_payload(tmp_path, ("generic",), False)

    assert preview == report
    assert isinstance(report, UninstallReport)
    assert ".maidrc.yaml" in report.preserved
    assert "docs/draft-manifest-workflow.md" in report.preserved
    assert config.is_file()
    assert workflow.is_file()


def test_init_uninstall_selected_tool_boundaries_are_isolated(
    tmp_path: Path, monkeypatch
) -> None:
    agent_manifests = {
        "claude": Path(".claude/manifest.json"),
        "codex": Path(".codex/manifest.json"),
        "cursor": Path(".cursor/manifest.json"),
    }
    for selected_tool in ("claude", "codex", "cursor", "generic"):
        project = tmp_path / selected_tool
        project.mkdir()
        monkeypatch.chdir(project)
        assert main(["init", "--tool", "claude"]) == 0
        assert main(["init", "--tool", "codex", "--force"]) == 0
        assert main(["init", "--tool", "cursor", "--force"]) == 0

        assert main(["init", "--uninstall", "--tool", selected_tool]) == 0

        for tool, manifest_path in agent_manifests.items():
            assert (project / manifest_path).exists() is (
                selected_tool == "generic" or selected_tool != tool
            )
        assert (project / ".maidrc.yaml").exists() is (selected_tool != "generic")
        assert (project / "docs" / "draft-manifest-workflow.md").exists() is (
            selected_tool != "generic"
        )


def test_init_uninstall_rejects_malformed_markers_before_any_removal(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    marker_surfaces = (
        (Path("CLAUDE.md"), MAID_SECTION_END),
        (Path("AGENTS.md"), MAID_SECTION_END),
        (Path(".gitignore"), GITIGNORE_END),
        (Path(".pre-commit-config.yaml"), PRE_COMMIT_END),
    )
    for index, (relative_path, end_marker) in enumerate(marker_surfaces):
        project = tmp_path / f"marker-{index}"
        project.mkdir()
        monkeypatch.chdir(project)
        assert main(["init", "--tool", "claude"]) == 0
        assert main(["init", "--tool", "codex", "--force"]) == 0
        marker_path = project / relative_path
        marker_path.write_text(marker_path.read_text().replace(end_marker, "", 1))
        codex_skill = project / ".codex" / "skills" / "maid-planner" / "SKILL.md"

        assert main(["init", "--uninstall"]) == 1

        assert codex_skill.is_file()
        assert (project / ".claude" / "manifest.json").is_file()
        assert (project / ".maidrc.yaml").is_file()
        assert "malformed" in capsys.readouterr().err.lower()


def test_init_uninstall_rejects_unsafe_installed_manifests_without_mutation(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    cases: tuple[tuple[str, object], ...] = (
        ("invalid-json", "{not json"),
        ("wrong-type", {"skills": {"distributable": "maid-planner"}}),
        ("parent-traversal", {"skills": {"distributable": ["../../outside"]}}),
        ("non-normalized", {"skills": {"distributable": ["nested/../outside"]}}),
        ("absolute", {"skills": {"distributable": ["ABSOLUTE_PATH"]}}),
        ("agent-root", {"root": {"distributable": ["."]}}),
    )
    for case_name, manifest_data in cases:
        project = tmp_path / case_name
        project.mkdir()
        monkeypatch.chdir(project)
        assert main(["init", "--tool", "codex"]) == 0
        skill = project / ".codex" / "skills" / "maid-planner" / "SKILL.md"
        manifest_path = project / ".codex" / "manifest.json"
        if manifest_data == "{not json":
            manifest_path.write_text(str(manifest_data))
        else:
            if case_name == "absolute":
                manifest_data = {
                    "skills": {"distributable": [str(project / "outside-abs")]}
                }
            manifest_path.write_text(json.dumps(manifest_data))
        outside = project / "outside"
        outside.write_text("keep outside\n")
        custom = project / ".codex" / "custom-user-file.txt"
        custom.write_text("keep custom\n")

        assert main(["init", "--uninstall", "--tool", "codex"]) == 1

        assert skill.is_file()
        assert outside.read_text() == "keep outside\n"
        assert custom.read_text() == "keep custom\n"
        assert manifest_path.is_file()
        capsys.readouterr()


def test_init_uninstall_rejects_symlinked_agent_boundaries_without_mutation(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    if not _platform_supports_symlinks(tmp_path):
        pytest.skip("platform does not support symbolic links")
    for boundary in ("skills", "agent-root"):
        project = tmp_path / boundary
        project.mkdir()
        monkeypatch.chdir(project)
        assert main(["init", "--tool", "codex"]) == 0
        if boundary == "skills":
            linked_path = project / ".codex" / "skills"
            outside = project / "outside-skills"
            owned = outside / "maid-planner" / "SKILL.md"
        else:
            linked_path = project / ".codex"
            outside = project / "outside-codex"
            owned = outside / "skills" / "maid-planner" / "SKILL.md"
        linked_path.rename(outside)
        linked_path.symlink_to(outside, target_is_directory=True)

        assert main(["init", "--uninstall", "--tool", "codex"]) == 1

        assert linked_path.is_symlink()
        assert owned.is_file()
        assert "symlink" in capsys.readouterr().err.lower()


def test_init_uninstall_revalidates_plan_before_applying_mutations(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    if not _platform_supports_symlinks(tmp_path):
        pytest.skip("platform does not support symbolic links")
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--tool", "codex"]) == 0
    config = tmp_path / ".maidrc.yaml"
    outside = tmp_path / "outside-skills"
    outside_skill = outside / "maid-planner" / "SKILL.md"
    outside_skill.parent.mkdir(parents=True)
    outside_skill.write_text("outside user data\n")

    import maid_runner.cli.commands.init as init_module

    original_deduplicate = init_module._deduplicate_operations

    def swap_boundary_after_planning(operations):
        planned = original_deduplicate(operations)
        skills = tmp_path / ".codex" / "skills"
        hidden = tmp_path / "original-skills"
        skills.rename(hidden)
        skills.symlink_to(outside, target_is_directory=True)
        config.write_text(config.read_text() + "concurrent user edit\n")
        return planned

    monkeypatch.setattr(
        init_module, "_deduplicate_operations", swap_boundary_after_planning
    )

    assert main(["init", "--uninstall"]) == 1

    assert outside_skill.read_text() == "outside user data\n"
    assert "concurrent user edit" in config.read_text()
    assert (tmp_path / ".codex" / "manifest.json").is_file()
    assert "changed after uninstall planning" in capsys.readouterr().err.lower()
    monkeypatch.setattr(init_module, "_deduplicate_operations", original_deduplicate)

    source_race = tmp_path / "source-race"
    source_race.mkdir()
    monkeypatch.chdir(source_race)
    assert main(["init", "--tool", "generic"]) == 0
    original_new_operation = init_module._new_uninstall_operation

    def edit_marker_before_snapshot(path, replacement=None, **kwargs):
        if path.name == ".gitignore" and kwargs.get("expected_source") is not None:
            path.write_text(path.read_text() + "concurrent marker edit\n")
        return original_new_operation(path, replacement, **kwargs)

    monkeypatch.setattr(
        init_module, "_new_uninstall_operation", edit_marker_before_snapshot
    )
    assert main(["init", "--uninstall"]) == 1
    assert "concurrent marker edit" in (source_race / ".gitignore").read_text()
    assert (source_race / ".maidrc.yaml").is_file()
    assert "changed while uninstall was planning" in capsys.readouterr().err.lower()

    snapshot_race = tmp_path / "snapshot-race"
    snapshot_race.mkdir()
    monkeypatch.chdir(snapshot_race)
    assert main(["init", "--tool", "generic"]) == 0
    marker = snapshot_race / ".gitignore"
    original_lstat = Path.lstat
    marker_lstat_calls = 0

    def edit_marker_between_snapshot_stats(path, *args, **kwargs):
        nonlocal marker_lstat_calls
        if path == marker:
            marker_lstat_calls += 1
            if marker_lstat_calls == 2:
                path.write_text(path.read_text() + "interleaved user edit\n")
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(init_module, "_new_uninstall_operation", original_new_operation)
    monkeypatch.setattr(Path, "lstat", edit_marker_between_snapshot_stats)
    assert main(["init", "--uninstall"]) == 1
    assert "interleaved user edit" in marker.read_text()
    assert (snapshot_race / ".maidrc.yaml").is_file()

    scaffold_race = tmp_path / "scaffold-race"
    scaffold_race.mkdir()
    monkeypatch.chdir(scaffold_race)
    assert main(["init", "--tool", "generic"]) == 0
    config_target = scaffold_race / ".maidrc.yaml"
    config_lstat_calls = 0

    def edit_scaffold_between_snapshot_stats(path, *args, **kwargs):
        nonlocal config_lstat_calls
        if path == config_target:
            config_lstat_calls += 1
            if config_lstat_calls == 2:
                path.write_text(path.read_text() + "interleaved scaffold edit\n")
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", edit_scaffold_between_snapshot_stats)
    assert main(["init", "--uninstall"]) == 1
    assert "interleaved scaffold edit" in config_target.read_text()
    assert (scaffold_race / "docs" / "draft-manifest-workflow.md").is_file()

    apply_race = tmp_path / "apply-race"
    apply_race.mkdir()
    monkeypatch.chdir(apply_race)
    assert main(["init", "--tool", "codex"]) == 0
    original_apply = init_module._apply_uninstall_operation
    changed = False

    def edit_directory_before_apply(project_root, operation):
        nonlocal changed
        if not changed and operation.replacement is None and operation.path.is_dir():
            (operation.path / "concurrent-user-file.txt").write_text("keep me\n")
            changed = True
        return original_apply(project_root, operation)

    monkeypatch.setattr(init_module, "_new_uninstall_operation", original_new_operation)
    monkeypatch.setattr(
        init_module, "_apply_uninstall_operation", edit_directory_before_apply
    )
    assert main(["init", "--uninstall", "--tool", "codex"]) == 1
    assert list(apply_race.rglob("concurrent-user-file.txt"))
    assert (apply_race / ".codex" / "manifest.json").is_file()

    fallback = tmp_path / "fallback"
    fallback.mkdir()
    monkeypatch.chdir(fallback)
    assert main(["init", "--tool", "codex"]) == 0
    monkeypatch.setattr(init_module, "_apply_uninstall_operation", original_apply)
    monkeypatch.setattr(
        init_module, "_supports_descriptor_relative_mutation", lambda: False
    )
    assert main(["init", "--uninstall", "--tool", "codex"]) == 1
    assert (fallback / ".codex" / "manifest.json").is_file()
    assert "refusing pathname-based mutation" in capsys.readouterr().err.lower()
