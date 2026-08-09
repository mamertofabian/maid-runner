"""Behavioral compatibility tests for historical MAID pre-commit markers."""

from pathlib import Path

import pytest

from maid_runner.cli.commands._main import main


START_MARKER = "# BEGIN MAID RUNNER PRE-COMMIT"
END_MARKER = "# END MAID RUNNER PRE-COMMIT"


def test_init_force_normalizes_legacy_generated_pre_commit_markers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--tool", "generic"]) == 0
    config_path = tmp_path / ".pre-commit-config.yaml"
    canonical = config_path.read_text(encoding="utf-8")
    legacy = (
        "# user prefix\n"
        + canonical.replace(START_MARKER, f"  {START_MARKER}", 1).replace(
            "entry: maid verify --profile pre-commit --since HEAD",
            "entry: maid verify --legacy",
            1,
        )
        + "  - repo: https://example.com/user-hooks\n"
        + "    rev: v1\n"
        + "    hooks:\n"
        + "      - id: user-hook\n"
    )
    config_path.write_text(legacy, encoding="utf-8")
    prefix, after_start = legacy.split(f"  {START_MARKER}", 1)
    _, suffix = after_start.split(END_MARKER, 1)

    assert main(["init", "--tool", "generic", "--force"]) == 0

    normalized = config_path.read_text(encoding="utf-8")
    assert normalized.startswith(prefix + START_MARKER)
    assert normalized.endswith(END_MARKER + suffix)
    assert normalized.count(START_MARKER) == 1
    assert normalized.count(END_MARKER) == 1
    assert f"  {START_MARKER}" not in normalized
    assert "maid verify --legacy" not in normalized
    assert "https://example.com/user-hooks" in normalized
    assert "user-hook" in normalized
    first_refresh = config_path.read_bytes()

    assert main(["init", "--tool", "generic", "--force"]) == 0
    assert config_path.read_bytes() == first_refresh


def test_init_uninstall_accepts_legacy_generated_pre_commit_markers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--tool", "claude"]) == 0
    assert main(["init", "--tool", "codex", "--force"]) == 0
    capsys.readouterr()

    config = tmp_path / ".pre-commit-config.yaml"
    current = config.read_text()
    legacy = current.replace(START_MARKER, f"  {START_MARKER}", 1)
    user_yaml = (
        "  - repo: https://example.com/user-hooks\n"
        "    rev: v1\n"
        "    hooks:\n"
        "      - id: user-hook\n"
    )
    config.write_text(legacy + user_yaml)
    custom_skill = tmp_path / ".codex" / "skills" / "cloudflare" / "SKILL.md"
    custom_skill.parent.mkdir(parents=True)
    custom_skill.write_text("keep cloudflare skill\n")
    active_manifest = tmp_path / "manifests" / "keep.manifest.yaml"
    active_manifest.write_text("schema: '2'\ngoal: keep\ntype: feature\ncreated: now\n")
    custom_draft = tmp_path / "manifests" / "drafts" / "keep.md"
    custom_draft.write_text("keep draft\n")
    before = {
        "config": config.read_bytes(),
        "skill": custom_skill.read_bytes(),
        "manifest": active_manifest.read_bytes(),
        "draft": custom_draft.read_bytes(),
    }

    assert main(["init", "--uninstall", "--dry-run"]) == 0
    assert "Would remove: .pre-commit-config.yaml#maid-managed-block" in (
        capsys.readouterr().out
    )
    assert config.read_bytes() == before["config"]
    assert (tmp_path / ".codex" / "manifest.json").is_file()

    assert main(["init", "--uninstall"]) == 0
    assert "Removed: .pre-commit-config.yaml#maid-managed-block" in (
        capsys.readouterr().out
    )
    assert START_MARKER not in config.read_text()
    assert END_MARKER not in config.read_text()
    assert "https://example.com/user-hooks" in config.read_text()
    assert "user-hook" in config.read_text()
    assert custom_skill.read_bytes() == before["skill"]
    assert active_manifest.read_bytes() == before["manifest"]
    assert custom_draft.read_bytes() == before["draft"]
    assert main(["init", "--uninstall"]) == 0
    assert "No installed MAID init payload found" in capsys.readouterr().out


def test_init_uninstall_rejects_legacy_marker_block_without_reserved_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--tool", "generic"]) == 0
    capsys.readouterr()
    config = tmp_path / ".pre-commit-config.yaml"
    legacy_non_owner = (
        config.read_text()
        .replace(START_MARKER, f"  {START_MARKER}", 1)
        .replace("id: maid-verify", "id: unrelated-hook", 1)
    )
    config.write_text(legacy_non_owner)
    scaffold = tmp_path / ".maidrc.yaml"
    before_scaffold = scaffold.read_bytes()

    assert main(["init", "--uninstall", "--dry-run"]) == 1

    assert config.read_text() == legacy_non_owner
    assert scaffold.read_bytes() == before_scaffold
    assert "managed block must contain exactly one maid-verify hook" in (
        capsys.readouterr().err
    )


def test_init_and_uninstall_reject_nonhistorical_indented_pre_commit_markers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for case in (
        "unsupported-both",
        "quoted",
        "canonical-plus-quoted",
        "historical-plus-unsupported",
    ):
        project = tmp_path / case
        project.mkdir()
        monkeypatch.chdir(project)
        assert main(["init", "--tool", "generic"]) == 0
        config_path = project / ".pre-commit-config.yaml"
        canonical = config_path.read_text()
        if case == "unsupported-both":
            malformed = canonical.replace(
                START_MARKER, f"    {START_MARKER}", 1
            ).replace(END_MARKER, f"    {END_MARKER}", 1)
        elif case == "quoted":
            unmarked = canonical.replace(f"{START_MARKER}\n", "", 1).replace(
                f"{END_MARKER}\n", "", 1
            )
            malformed = (
                f'description: "{START_MARKER}"\nother: "{END_MARKER}"\n{unmarked}'
            )
        elif case == "canonical-plus-quoted":
            malformed = (
                f'description: "{START_MARKER}"\nother: "{END_MARKER}"\n{canonical}'
            )
        else:
            malformed = (
                canonical.replace(START_MARKER, f"  {START_MARKER}", 1)
                + f"    {START_MARKER}\n"
                + f"    {END_MARKER}\n"
            )
        config_path.write_text(malformed)
        config_before = config_path.read_bytes()
        scaffold = project / ".maidrc.yaml"
        scaffold_before = scaffold.read_bytes()

        assert main(["init", "--tool", "generic", "--force"]) == 1
        assert main(["init", "--uninstall"]) == 1

        assert config_path.read_bytes() == config_before
        assert scaffold.read_bytes() == scaffold_before
