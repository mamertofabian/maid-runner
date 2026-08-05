"""Behavioral contract for MAID-managed pre-commit configuration from init."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from maid_runner.cli.commands._main import main


ROOT = Path(__file__).resolve().parents[2]
CONFIG_NAME = ".pre-commit-config.yaml"
START_MARKER = "# BEGIN MAID RUNNER PRE-COMMIT"
END_MARKER = "# END MAID RUNNER PRE-COMMIT"
VERIFY_ENTRY = (
    "maid verify --summary --advisory --allow-empty --require-plan-lock --require-red-evidence "
    "--fail-fast --no-changed-scope --file-tracking-scope task "
    "--plan-lock-scope task --since HEAD"
)


def _maid_hooks(path: Path) -> list[dict]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        hook
        for repo in config["repos"]
        for hook in repo.get("hooks", [])
        if hook.get("id") == "maid-verify"
    ]


def test_init_creates_managed_maid_verify_pre_commit_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["init", "--tool", "generic"]) == 0

    config_path = tmp_path / CONFIG_NAME
    text = config_path.read_text(encoding="utf-8")
    assert text.count(START_MARKER) == 1
    assert text.count(END_MARKER) == 1
    assert _maid_hooks(config_path) == [
        {
            "id": "maid-verify",
            "name": "MAID verification (fail-fast handoff gates)",
            "entry": VERIFY_ENTRY,
            "language": "system",
            "pass_filenames": False,
            "always_run": True,
            "stages": ["pre-commit"],
        }
    ]
    output = capsys.readouterr().out
    assert "pre-commit install" in output
    assert "core.hooksPath" in output


def test_init_managed_hook_tracks_only_head_commit_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["init", "--tool", "generic"]) == 0

    assert _maid_hooks(tmp_path / CONFIG_NAME)[0]["entry"] == VERIFY_ENTRY


def test_init_appends_managed_hook_without_rewriting_existing_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    original = (
        "# keep this comment exactly\n"
        "repos:\n"
        "  - repo: https://github.com/pre-commit/pre-commit-hooks\n"
        "    rev: v5.0.0\n"
        "    hooks:\n"
        "      - id: trailing-whitespace  # keep inline comment\n"
        "default_stages: [pre-commit]\n"
    )
    config_path = tmp_path / CONFIG_NAME
    config_path.write_text(original, encoding="utf-8")

    assert main(["init", "--tool", "generic"]) == 0

    updated = config_path.read_text(encoding="utf-8")
    original_parts = original.split("default_stages:")
    assert updated.startswith(original_parts[0])
    assert updated.endswith("default_stages:" + original_parts[1])
    assert _maid_hooks(config_path)[0]["entry"] == VERIFY_ENTRY
    assert yaml.safe_load(updated)["default_stages"] == ["pre-commit"]


def test_init_force_refresh_is_byte_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--tool", "generic"]) == 0
    config_path = tmp_path / CONFIG_NAME
    first = config_path.read_bytes()

    assert main(["init", "--tool", "generic", "--force"]) == 0
    second = config_path.read_bytes()
    assert main(["init", "--tool", "generic", "--force"]) == 0

    assert config_path.read_bytes() == second == first
    assert len(_maid_hooks(config_path)) == 1


def test_init_force_refresh_replaces_only_stale_managed_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / CONFIG_NAME
    original = (
        "# user prefix\n"
        "repos:\n"
        f"{START_MARKER}\n"
        "  - repo: local\n"
        "    hooks:\n"
        "      - id: maid-verify\n"
        "        name: Old MAID hook\n"
        "        entry: maid verify --old\n"
        "        language: system\n"
        f"{END_MARKER}\n"
        "default_stages: [pre-commit]  # user suffix\n"
    )
    config_path.write_text(original, encoding="utf-8")
    prefix, rest = original.split(START_MARKER, 1)
    _, suffix = rest.split(END_MARKER, 1)

    assert main(["init", "--tool", "generic", "--force"]) == 0

    updated = config_path.read_text(encoding="utf-8")
    assert updated.startswith(prefix + START_MARKER)
    assert updated.endswith(END_MARKER + suffix)
    assert _maid_hooks(config_path)[0]["entry"] == VERIFY_ENTRY
    assert "maid verify --old" not in updated


def test_init_rejects_unmanaged_maid_verify_conflict_before_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    original = (
        "repos:\n"
        "  - repo: local\n"
        "    hooks:\n"
        "      - id: maid-verify\n"
        "        name: User-owned MAID command\n"
        "        entry: scripts/maid verify\n"
        "        language: system\n"
    )
    config_path = tmp_path / CONFIG_NAME
    config_path.write_text(original, encoding="utf-8")

    assert main(["init", "--tool", "generic"]) == 1

    assert config_path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "manifests").exists()
    assert not (tmp_path / ".maidrc.yaml").exists()
    assert "unmanaged maid-verify" in capsys.readouterr().err.lower()


@pytest.mark.parametrize("invalid", ["repos: [", "repos: not-a-list\n"])
def test_init_rejects_invalid_pre_commit_config_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    invalid: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / CONFIG_NAME
    config_path.write_text(invalid, encoding="utf-8")

    assert main(["init", "--tool", "generic"]) == 1

    assert config_path.read_text(encoding="utf-8") == invalid
    assert not (tmp_path / "manifests").exists()
    assert not (tmp_path / ".maidrc.yaml").exists()
    assert "pre-commit" in capsys.readouterr().err.lower()


@pytest.mark.parametrize(
    "markers",
    [
        f"{START_MARKER}\nrepos: []\n",
        f"{END_MARKER}\nrepos: []\n",
        f"{START_MARKER}\n{START_MARKER}\nrepos: []\n{END_MARKER}\n",
    ],
)
def test_init_rejects_malformed_managed_markers_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    markers: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / CONFIG_NAME
    config_path.write_text(markers, encoding="utf-8")

    assert main(["init", "--tool", "generic"]) == 1

    assert config_path.read_text(encoding="utf-8") == markers
    assert not (tmp_path / "manifests").exists()
    assert not (tmp_path / ".maidrc.yaml").exists()


@pytest.mark.parametrize(
    "config_text",
    [
        (
            "repos:\n"
            f"{START_MARKER}\n"
            "  - repo: local\n"
            "    hooks:\n"
            "      - id: unrelated\n"
            "        entry: true\n"
            "        language: system\n"
            f"{END_MARKER}\n"
            "  - repo: local\n"
            "    hooks:\n"
            "      - id: maid-verify\n"
            "        entry: scripts/maid verify\n"
            "        language: system\n"
        ),
        (
            f'description: "{START_MARKER}"\n'
            f'other: "{END_MARKER}"\n'
            "repos:\n"
            "  - repo: local\n"
            "    hooks:\n"
            "      - id: maid-verify\n"
            "        entry: scripts/maid verify\n"
            "        language: system\n"
        ),
    ],
)
def test_init_rejects_markers_that_do_not_own_the_reserved_hook(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    config_text: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / CONFIG_NAME
    config_path.write_text(config_text, encoding="utf-8")

    assert main(["init", "--tool", "generic"]) == 1

    assert config_path.read_text(encoding="utf-8") == config_text
    assert not (tmp_path / "manifests").exists()


@pytest.mark.parametrize(
    "config_text",
    [
        "repos: []\nrepos:\n  - repo: local\n    hooks: []\n",
        "shared: &shared []\nrepos: *shared\n",
        (
            "defaults: &defaults\n"
            "  repos:\n"
            "    - repo: local\n"
            "      hooks: []\n"
            "<<: *defaults\n"
        ),
    ],
)
def test_init_rejects_ambiguous_repos_sources_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    config_text: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / CONFIG_NAME
    config_path.write_text(config_text, encoding="utf-8")

    assert main(["init", "--tool", "generic"]) == 1

    assert config_path.read_text(encoding="utf-8") == config_text
    assert not (tmp_path / "manifests").exists()


def test_init_preserves_crlf_bytes_when_appending_managed_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    original = b"# user comment\r\nrepos:\r\n  - repo: local\r\n    hooks: []\r\n"
    config_path = tmp_path / CONFIG_NAME
    config_path.write_bytes(original)

    assert main(["init", "--tool", "generic"]) == 0

    updated = config_path.read_bytes()
    assert updated.startswith(original)
    assert b"\n" not in updated.replace(b"\r\n", b"")
    assert len(_maid_hooks(config_path)) == 1


def test_init_inserts_before_explicit_yaml_document_terminator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    original = "default_stages: [pre-commit]\n...\n"
    config_path = tmp_path / CONFIG_NAME
    config_path.write_text(original, encoding="utf-8")

    assert main(["init", "--tool", "generic"]) == 0

    updated = config_path.read_text(encoding="utf-8")
    assert updated.endswith("...\n")
    assert updated.index(START_MARKER) < updated.index("...\n")
    assert len(_maid_hooks(config_path)) == 1


@pytest.mark.parametrize(
    "config_text",
    [
        "repos: []\n",
        "repos: [{repo: local, hooks: []}]\n",
        "{repos: []}\n",
        "{default_stages: [pre-commit]}\n",
    ],
)
def test_init_rejects_flow_style_config_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    config_text: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / CONFIG_NAME
    config_path.write_text(config_text, encoding="utf-8")

    assert main(["init", "--tool", "generic"]) == 1

    assert config_path.read_text(encoding="utf-8") == config_text
    assert not (tmp_path / "manifests").exists()
    assert not (tmp_path / ".maidrc.yaml").exists()


@pytest.mark.parametrize("target_exists", [True, False])
def test_init_rejects_pre_commit_config_symlinks_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target_exists: bool,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path.parent / f"{tmp_path.name}-external-pre-commit.yaml"
    original = b"repos:\n  - repo: local\n    hooks: []\n"
    if target_exists:
        target.write_bytes(original)
    config_path = tmp_path / CONFIG_NAME
    config_path.symlink_to(target)

    assert main(["init", "--tool", "generic"]) == 1

    assert config_path.is_symlink()
    if target_exists:
        assert target.read_bytes() == original
    else:
        assert not target.exists()
    assert not (tmp_path / "manifests").exists()
    assert not (tmp_path / ".maidrc.yaml").exists()


def test_init_pre_commit_atomic_write_failure_preserves_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    original = b"repos:\n  - repo: local\n    hooks: []\n"
    config_path = tmp_path / CONFIG_NAME
    config_path.write_bytes(original)
    real_replace = os.replace

    def fail_pre_commit_replace(source: str | bytes, destination: str | bytes) -> None:
        if Path(destination) == config_path:
            raise OSError("simulated atomic replace failure")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_pre_commit_replace)

    assert main(["init", "--tool", "generic"]) == 1

    assert config_path.read_bytes() == original
    assert not list(tmp_path.glob(f".{CONFIG_NAME}.*.tmp"))
    assert not (tmp_path / "manifests").exists()
    assert not (tmp_path / ".maidrc.yaml").exists()


def test_init_pre_commit_dry_run_reports_action_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    original = "repos:\n  - repo: local\n    hooks: []\n"
    config_path = tmp_path / CONFIG_NAME
    config_path.write_text(original, encoding="utf-8")
    before = sorted(tmp_path.rglob("*"))

    assert main(["init", "--tool", "generic", "--dry-run"]) == 0

    assert config_path.read_text(encoding="utf-8") == original
    assert sorted(tmp_path.rglob("*")) == before
    assert "Would update: .pre-commit-config.yaml" in capsys.readouterr().out


def test_readme_documents_init_managed_pre_commit_behavior() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert VERIFY_ENTRY in readme
    assert "pre-commit install" in readme
    assert "core.hooksPath" in readme
    assert "preserves existing hooks" in readme
