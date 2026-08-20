"""Behavioral coverage for ownership-safe uninstall on native Windows."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

from maid_runner.cli.commands._main import main


WINDOWS_ONLY = pytest.mark.skipif(os.name != "nt", reason="native Windows behavior")


@WINDOWS_ONLY
def test_init_uninstall_completes_on_windows_and_preserves_project_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    custom_manifest = tmp_path / "manifests" / "custom.manifest.yaml"

    assert main(["init", "--tool", "generic"]) == 0
    custom_manifest.write_text("schema: '2'\ngoal: keep me\ntype: feature\n")

    assert main(["init", "--uninstall", "--tool", "generic"]) == 0

    assert custom_manifest.read_text() == "schema: '2'\ngoal: keep me\ntype: feature\n"
    assert not (tmp_path / ".maidrc.yaml").exists()
    assert not (tmp_path / "docs" / "draft-manifest-workflow.md").exists()
    assert not (tmp_path / "docs" / "manifest-outcome-records.md").exists()


@WINDOWS_ONLY
def test_skills_uninstall_completes_on_windows_and_preserves_custom_skills(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    custom_skill = home / ".codex" / "skills" / "custom" / "SKILL.md"

    assert main(["skills", "install", "--target-root", str(home)]) == 0
    custom_skill.parent.mkdir(parents=True)
    custom_skill.write_text("keep me\n")

    assert main(["skills", "uninstall", "--target-root", str(home)]) == 0

    assert custom_skill.read_text() == "keep me\n"
    assert not (home / ".claude" / "skills" / "maid-onboard").exists()
    assert not (home / ".codex" / "skills" / "maid-onboard").exists()


@WINDOWS_ONLY
def test_init_uninstall_rejects_windows_junction_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--tool", "codex"]) == 0
    skills = tmp_path / ".codex" / "skills"
    outside = tmp_path / "outside-skills"
    skills.rename(outside)
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(skills), str(outside)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"junction creation unavailable: {result.stderr or result.stdout}")
    outside_skill = next(outside.rglob("SKILL.md"))
    original = outside_skill.read_bytes()

    assert main(["init", "--uninstall", "--tool", "codex"]) == 1

    assert outside_skill.read_bytes() == original
    assert skills.exists()


@WINDOWS_ONLY
def test_init_uninstall_rejects_leaf_edit_at_mutation_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from maid_runner.core import uninstall as uninstall_module

    monkeypatch.chdir(tmp_path)
    assert main(["init", "--tool", "generic"]) == 0
    config = tmp_path / ".maidrc.yaml"
    original = config.read_bytes()
    original_replace = uninstall_module.os.replace
    injected = False

    def edit_leaf_before_replace(source: object, destination: object) -> None:
        nonlocal injected
        if not injected and Path(source) == config:
            injected = True
            config.write_bytes(original + b"concurrent user edit\n")
        original_replace(source, destination)

    monkeypatch.setattr(uninstall_module.os, "replace", edit_leaf_before_replace)

    assert main(["init", "--uninstall", "--tool", "generic"]) == 1

    assert injected
    assert config.is_file()
    assert config.read_bytes() == original + b"concurrent user edit\n"
    assert not list(config.parent.glob(".*.maid-uninstall"))


@WINDOWS_ONLY
def test_skills_uninstall_restores_visible_path_when_cleanup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from maid_runner.core import uninstall as uninstall_module

    home = tmp_path / "home"
    assert main(["skills", "install", "--target-root", str(home)]) == 0
    installed = home / ".claude" / "skills" / "maid-onboard"
    original_rmtree = uninstall_module.shutil.rmtree

    def fail_quarantine_cleanup(path: object, *args: object, **kwargs: object) -> None:
        if str(path).endswith(".maid-uninstall"):
            raise OSError("simulated locked descendant")
        original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(uninstall_module.shutil, "rmtree", fail_quarantine_cleanup)

    assert main(["skills", "uninstall", "--target-root", str(home)]) == 1

    assert (installed / "SKILL.md").is_file()
    assert not list(installed.parent.glob(".*.maid-uninstall"))


@WINDOWS_ONLY
def test_skills_uninstall_rollback_never_overwrites_new_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from maid_runner.core import uninstall as uninstall_module

    home = tmp_path / "home"
    assert main(["skills", "install", "--target-root", str(home)]) == 0
    installed = home / ".claude" / "skills" / "maid-onboard"
    original_rmtree = uninstall_module.shutil.rmtree
    original_rename = uninstall_module.os.rename
    injected = False

    def fail_quarantine_cleanup(path: object, *args: object, **kwargs: object) -> None:
        if str(path).endswith(".maid-uninstall"):
            raise OSError("simulated locked descendant")
        original_rmtree(path, *args, **kwargs)

    def create_destination_before_restore(source: object, destination: object) -> None:
        nonlocal injected
        destination_path = Path(destination)
        if not injected and destination_path == installed:
            injected = True
            destination_path.mkdir()
            (destination_path / "USER.md").write_text("new user data\n")
        original_rename(source, destination)

    monkeypatch.setattr(uninstall_module.shutil, "rmtree", fail_quarantine_cleanup)
    monkeypatch.setattr(
        uninstall_module.os, "rename", create_destination_before_restore
    )

    assert main(["skills", "uninstall", "--target-root", str(home)]) == 1

    assert injected
    assert (installed / "USER.md").read_text() == "new user data\n"
    quarantines = list(installed.parent.glob(".*.maid-uninstall"))
    assert len(quarantines) == 1
    assert (quarantines[0] / "SKILL.md").is_file()


@WINDOWS_ONLY
def test_init_uninstall_preserves_concurrent_replacement_edit_during_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from maid_runner.core import uninstall as uninstall_module

    monkeypatch.chdir(tmp_path)
    assert main(["init", "--tool", "generic"]) == 0
    config = tmp_path / ".gitignore"
    original = config.read_bytes()
    original_unlink = uninstall_module.os.unlink
    original_replace = uninstall_module.os.replace
    cleanup_failed = False
    injected = False

    def fail_old_quarantine_cleanup(
        path: object, *args: object, **kwargs: object
    ) -> None:
        nonlocal cleanup_failed
        path_name = Path(path).name
        if (
            not cleanup_failed
            and path_name.startswith("..gitignore.")
            and path_name.endswith(".maid-uninstall")
        ):
            cleanup_failed = True
            raise OSError("simulated locked old file")
        original_unlink(path, *args, **kwargs)

    def edit_replacement_before_quarantine(source: object, destination: object) -> None:
        nonlocal injected
        source_path = Path(source)
        if cleanup_failed and not injected and source_path == config:
            injected = True
            config.write_bytes(config.read_bytes() + b"concurrent replacement edit\n")
        original_replace(source, destination)

    monkeypatch.setattr(uninstall_module.os, "unlink", fail_old_quarantine_cleanup)
    monkeypatch.setattr(
        uninstall_module.os, "replace", edit_replacement_before_quarantine
    )

    assert main(["init", "--uninstall", "--tool", "generic"]) == 1

    assert cleanup_failed and injected
    assert config.read_bytes() == original
    quarantines = list(config.parent.glob(".*.maid-uninstall"))
    assert len(quarantines) == 1
    assert quarantines[0].read_bytes().endswith(b"concurrent replacement edit\n")


@WINDOWS_ONLY
def test_init_uninstall_restores_original_when_replacement_validation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.core import uninstall as uninstall_module

    monkeypatch.chdir(tmp_path)
    assert main(["init", "--tool", "generic"]) == 0
    config = tmp_path / ".gitignore"
    original = config.read_bytes()
    original_unlink = uninstall_module.os.unlink
    original_lstat = Path.lstat
    old_quarantine: Path | None = None
    failed_path: Path | None = None

    def fail_old_quarantine_cleanup(
        path: object, *args: object, **kwargs: object
    ) -> None:
        nonlocal old_quarantine
        path_obj = Path(path)
        if (
            old_quarantine is None
            and path_obj.name.startswith("..gitignore.")
            and path_obj.name.endswith(".maid-uninstall")
        ):
            old_quarantine = path_obj
            raise OSError("simulated locked old file")
        original_unlink(path, *args, **kwargs)

    def fail_replacement_quarantine_lstat(
        path: Path, *args: object, **kwargs: object
    ) -> os.stat_result:
        nonlocal failed_path
        if (
            old_quarantine is not None
            and path != old_quarantine
            and path.name.startswith("..gitignore.")
            and path.name.endswith(".maid-uninstall")
        ):
            failed_path = path
            raise PermissionError("simulated replacement inspection failure")
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(uninstall_module.os, "unlink", fail_old_quarantine_cleanup)
    monkeypatch.setattr(Path, "lstat", fail_replacement_quarantine_lstat)

    assert main(["init", "--uninstall", "--tool", "generic"]) == 1

    assert failed_path is not None
    assert config.read_bytes() == original
    assert failed_path.exists()
    assert str(failed_path) in capsys.readouterr().err


@WINDOWS_ONLY
def test_init_uninstall_reports_both_quarantines_when_nested_restore_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.core import uninstall as uninstall_module

    monkeypatch.chdir(tmp_path)
    assert main(["init", "--tool", "generic"]) == 0
    config = tmp_path / ".gitignore"
    original = config.read_bytes()
    original_unlink = uninstall_module.os.unlink
    original_replace = uninstall_module.os.replace
    original_rename = uninstall_module.os.rename
    old_quarantine: Path | None = None
    replacement_edited = False
    destination_injected = False

    def fail_old_quarantine_cleanup(
        path: object, *args: object, **kwargs: object
    ) -> None:
        nonlocal old_quarantine
        path_obj = Path(path)
        if (
            old_quarantine is None
            and path_obj.name.startswith("..gitignore.")
            and path_obj.name.endswith(".maid-uninstall")
        ):
            old_quarantine = path_obj
            raise OSError("simulated locked old file")
        original_unlink(path, *args, **kwargs)

    def edit_replacement_before_quarantine(source: object, destination: object) -> None:
        nonlocal replacement_edited
        if (
            old_quarantine is not None
            and not replacement_edited
            and Path(source) == config
        ):
            replacement_edited = True
            config.write_bytes(config.read_bytes() + b"concurrent replacement edit\n")
        original_replace(source, destination)

    def create_destination_before_restore(source: object, destination: object) -> None:
        nonlocal destination_injected
        if (
            replacement_edited
            and not destination_injected
            and Path(destination) == config
        ):
            destination_injected = True
            config.write_bytes(b"new destination data\n")
        original_rename(source, destination)

    monkeypatch.setattr(uninstall_module.os, "unlink", fail_old_quarantine_cleanup)
    monkeypatch.setattr(
        uninstall_module.os, "replace", edit_replacement_before_quarantine
    )
    monkeypatch.setattr(
        uninstall_module.os, "rename", create_destination_before_restore
    )

    assert main(["init", "--uninstall", "--tool", "generic"]) == 1

    assert destination_injected
    assert config.read_bytes() == b"new destination data\n"
    quarantines = list(config.parent.glob(".*.maid-uninstall"))
    assert len(quarantines) == 2
    assert any(path.read_bytes() == original for path in quarantines)
    assert any(
        path.read_bytes().endswith(b"concurrent replacement edit\n")
        for path in quarantines
    )
    error = capsys.readouterr().err
    assert all(str(path) in error for path in quarantines)


def test_windows_ci_runs_uninstall_portability_regressions() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/maid-test.yml").read_text())
    windows_job = workflow["jobs"]["windows-init-portability"]
    commands = "\n".join(str(step.get("run", "")) for step in windows_job["steps"])

    assert "tests/cli/test_init_windows_portability.py" in commands
    assert "tests/cli/test_uninstall_windows_portability.py" in commands
