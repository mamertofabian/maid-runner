"""Tests for CLI 'maid manifest from-diff' command."""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path

import yaml


def _git(project_dir: Path, *argv: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test User",
            *argv,
        ],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _init_repo(project_dir: Path) -> None:
    _git(project_dir, "init")


def _commit_all(project_dir: Path, message: str = "commit") -> str:
    _git(project_dir, "add", ".")
    _git(project_dir, "commit", "-m", message)
    return _git(project_dir, "rev-parse", "HEAD")


def _write(project_dir: Path, rel_path: str, content: str) -> None:
    path = project_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _repo_with_worktree_change(project_dir: Path) -> None:
    _init_repo(project_dir)
    _write(project_dir, "src/base.py", "def base() -> None:\n    return None\n")
    _commit_all(project_dir, "baseline")
    _write(project_dir, "src/base.py", "def base() -> str:\n    return 'changed'\n")
    _write(project_dir, "src/new.py", "def new_func() -> bool:\n    return True\n")


def _repo_with_evidenced_worktree_change(project_dir: Path) -> None:
    _init_repo(project_dir)
    _write(project_dir, "src/base.py", "def base() -> None:\n    return None\n")
    _write(
        project_dir,
        "tests/test_base.py",
        "from src.base import base\n\n\ndef test_base():\n    assert base() is None\n",
    )
    _commit_all(project_dir, "baseline")
    _write(project_dir, "src/base.py", "def base() -> str:\n    return 'changed'\n")


def test_manifest_from_diff_dry_run_json_writes_nothing(tmp_path, monkeypatch, capsys):
    from maid_runner.cli.commands._main import main

    _repo_with_worktree_change(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "manifest",
            "from-diff",
            "--worktree",
            "--slug",
            "demo",
            "--dry-run",
            "--json",
        ]
    )

    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["metadata"]["generated_by"] == "maid-manifest-from-diff"
    assert data["metadata"]["needs_review"] is True
    assert not (tmp_path / "manifests").exists()


def test_manifest_from_diff_dry_run_rejects_empty_diff(tmp_path, monkeypatch, capsys):
    from maid_runner.cli.commands._main import main

    _init_repo(tmp_path)
    _write(tmp_path, "src/base.py", "def base() -> None:\n    return None\n")
    _commit_all(tmp_path, "baseline")
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "manifest",
            "from-diff",
            "--worktree",
            "--slug",
            "demo",
            "--dry-run",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "No changed files" in captured.err
    assert captured.out == ""
    assert not (tmp_path / "manifests").exists()


def test_manifest_from_diff_writes_default_draft_and_json_result(
    tmp_path, monkeypatch, capsys
):
    from maid_runner.cli.commands._main import main

    _repo_with_worktree_change(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        ["manifest", "from-diff", "--worktree", "--slug", "demo", "--json"]
    )

    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["path"] == "manifests/drafts/demo.manifest.yaml"
    output = tmp_path / result["path"]
    data = yaml.safe_load(output.read_text())
    assert data["goal"] == "TODO: describe this change"
    assert data["files"]["create"][0]["path"] == "src/new.py"


def test_manifest_from_diff_default_output_preserves_evidenced_validate_suggestion(
    tmp_path, monkeypatch, capsys
):
    from maid_runner.cli.commands._main import main

    _repo_with_evidenced_worktree_change(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        ["manifest", "from-diff", "--worktree", "--slug", "demo", "--json"]
    )

    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    data = yaml.safe_load((tmp_path / result["path"]).read_text())
    assert data["validate"] == [
        "pytest tests/test_base.py -v",
        "maid validate manifests/drafts/demo.manifest.yaml --mode schema --quiet",
    ]
    assert data["metadata"]["needs_review"] is True


def test_manifest_from_diff_custom_output_sets_validate_command(
    tmp_path, monkeypatch, capsys
):
    from maid_runner.cli.commands._main import main

    _repo_with_worktree_change(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "manifest",
            "from-diff",
            "--worktree",
            "--slug",
            "demo",
            "--output",
            "manifests/drafts/custom.manifest.yaml",
            "--dry-run",
            "--json",
        ]
    )

    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["validate"] == [
        "maid validate manifests/drafts/custom.manifest.yaml --mode schema --quiet"
    ]


def test_manifest_from_diff_custom_output_preserves_evidenced_validate_suggestion(
    tmp_path, monkeypatch, capsys
):
    from maid_runner.cli.commands._main import main

    _repo_with_evidenced_worktree_change(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "manifest",
            "from-diff",
            "--worktree",
            "--slug",
            "demo",
            "--output",
            "manifests/drafts/custom.manifest.yaml",
            "--dry-run",
            "--json",
        ]
    )

    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["validate"] == [
        "pytest tests/test_base.py -v",
        "maid validate manifests/drafts/custom.manifest.yaml --mode schema --quiet",
    ]
    assert data["metadata"]["needs_review"] is True


def test_manifest_from_diff_quotes_spaced_slug_validate_command(
    tmp_path, monkeypatch, capsys
):
    from maid_runner.cli.commands._main import main

    _repo_with_worktree_change(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "manifest",
            "from-diff",
            "--worktree",
            "--slug",
            "my demo",
            "--dry-run",
            "--json",
        ]
    )

    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert shlex.split(data["validate"][0]) == [
        "maid",
        "validate",
        "manifests/drafts/my demo.manifest.yaml",
        "--mode",
        "schema",
        "--quiet",
    ]


def test_manifest_from_diff_requires_exactly_one_baseline(
    tmp_path, monkeypatch, capsys
):
    from maid_runner.cli.commands._main import main

    _repo_with_worktree_change(tmp_path)
    monkeypatch.chdir(tmp_path)

    missing = main(["manifest", "from-diff", "--slug", "demo"])
    missing_err = capsys.readouterr().err
    multiple = main(
        ["manifest", "from-diff", "--worktree", "--since", "HEAD", "--slug", "demo"]
    )
    multiple_err = capsys.readouterr().err

    assert missing == 2
    assert multiple == 2
    assert "pass the task baseline explicitly" in missing_err
    assert "will not guess main, dev, or a remote branch" in missing_err
    assert "pass the task baseline explicitly" in multiple_err
    assert not (tmp_path / "manifests").exists()


def test_manifest_from_diff_counts_empty_string_baseline_flags(
    tmp_path, monkeypatch, capsys
):
    from maid_runner.cli.commands._main import main

    _repo_with_worktree_change(tmp_path)
    monkeypatch.chdir(tmp_path)

    since_empty = main(
        ["manifest", "from-diff", "--worktree", "--since", "", "--slug", "demo"]
    )
    since_empty_err = capsys.readouterr().err
    base_ref_empty = main(
        ["manifest", "from-diff", "--worktree", "--base-ref", "", "--slug", "demo"]
    )
    base_ref_empty_err = capsys.readouterr().err

    assert since_empty == 2
    assert base_ref_empty == 2
    assert "pass the task baseline explicitly" in since_empty_err
    assert "pass the task baseline explicitly" in base_ref_empty_err
    assert not (tmp_path / "manifests").exists()


def test_manifest_from_diff_cmd_manifest_rejects_missing_baseline(capsys):
    import argparse

    from maid_runner.cli.commands.manifest import cmd_manifest

    exit_code = cmd_manifest(
        argparse.Namespace(
            manifest_command="from-diff",
            since=None,
            base_ref=None,
            worktree=False,
            slug="demo",
            output=None,
            force=False,
            dry_run=True,
            json=False,
        )
    )

    assert exit_code == 2
    assert "pass the task baseline explicitly" in capsys.readouterr().err


def test_manifest_from_diff_build_parser_registers_subcommand():
    from maid_runner.cli.commands._main import build_parser

    parser = build_parser()
    args = parser.parse_args(
        [
            "manifest",
            "from-diff",
            "--worktree",
            "--slug",
            "demo",
            "--dry-run",
            "--json",
        ]
    )

    assert args.command == "manifest"
    assert args.manifest_command == "from-diff"
    assert args.worktree is True
    assert args.slug == "demo"


def test_manifest_from_diff_invalid_commitish_exits_without_writing(
    tmp_path, monkeypatch, capsys
):
    from maid_runner.cli.commands._main import main

    _repo_with_worktree_change(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        ["manifest", "from-diff", "--since", "not-a-commit", "--slug", "demo"]
    )

    assert exit_code == 2
    assert "not-a-commit" in capsys.readouterr().err
    assert not (tmp_path / "manifests").exists()


def test_manifest_from_diff_refuses_existing_output_without_force(
    tmp_path, monkeypatch, capsys
):
    from maid_runner.cli.commands._main import main

    _repo_with_worktree_change(tmp_path)
    output = tmp_path / "manifests" / "drafts" / "custom.manifest.yaml"
    output.parent.mkdir(parents=True)
    output.write_text("existing\n")
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "manifest",
            "from-diff",
            "--worktree",
            "--slug",
            "demo",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 2
    assert "already exists" in capsys.readouterr().err
    assert output.read_text() == "existing\n"


def test_manifest_from_diff_force_overwrites_existing_output(
    tmp_path, monkeypatch, capsys
):
    from maid_runner.cli.commands._main import main

    _repo_with_worktree_change(tmp_path)
    output = tmp_path / "manifests" / "drafts" / "custom.manifest.yaml"
    output.parent.mkdir(parents=True)
    output.write_text("existing\n")
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "manifest",
            "from-diff",
            "--worktree",
            "--slug",
            "demo",
            "--output",
            str(output),
            "--force",
        ]
    )

    assert exit_code == 0
    assert "wrote" in capsys.readouterr().out.lower()
    assert yaml.safe_load(output.read_text())["metadata"]["needs_review"] is True


def test_manifest_from_diff_rejects_active_manifest_output(
    tmp_path, monkeypatch, capsys
):
    from maid_runner.cli.commands._main import main

    _repo_with_worktree_change(tmp_path)
    output = tmp_path / "manifests" / "active.manifest.yaml"
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "manifest",
            "from-diff",
            "--worktree",
            "--slug",
            "demo",
            "--output",
            str(output),
            "--force",
        ]
    )

    assert exit_code == 2
    assert "manifests/drafts" in capsys.readouterr().err
    assert not output.exists()


def test_manifest_from_diff_rejects_draft_output_outside_project(
    tmp_path, monkeypatch, capsys
):
    from maid_runner.cli.commands._main import main

    _repo_with_worktree_change(tmp_path)
    output = (
        tmp_path.parent / "other" / "manifests" / "drafts" / "outside.manifest.yaml"
    )
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "manifest",
            "from-diff",
            "--worktree",
            "--slug",
            "demo",
            "--output",
            str(output),
            "--force",
        ]
    )

    assert exit_code == 2
    assert "manifests/drafts" in capsys.readouterr().err
    assert not output.exists()
