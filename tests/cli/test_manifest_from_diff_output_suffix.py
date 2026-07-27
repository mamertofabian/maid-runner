"""Tests for 'maid manifest from-diff' output-suffix rejection.

``write_from_diff_manifest`` emits YAML, and ``load_manifest_raw`` dispatches on
the exact lowercase output suffix when reading the file back, so any suffix the
reader does not map to the yaml format must be rejected before the command has
any filesystem effect.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest


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


def _repo_with_worktree_change(project_dir: Path) -> None:
    """Give from-diff a non-empty diff to render."""
    _git(project_dir, "init")
    base = project_dir / "src" / "base.py"
    base.parent.mkdir(parents=True, exist_ok=True)
    base.write_text("def base() -> None:\n    return None\n")
    _git(project_dir, "add", ".")
    _git(project_dir, "commit", "-m", "baseline")
    base.write_text("def base() -> str:\n    return 'changed'\n")


def _from_diff_args(output: Path | str, *extra: str) -> argparse.Namespace:
    """Parse a real from-diff command line, so flag wiring stays covered."""
    from maid_runner.cli.commands._main import build_parser

    return build_parser().parse_args(
        [
            "manifest",
            "from-diff",
            "--worktree",
            "--slug",
            "demo",
            "--output",
            str(output),
            *extra,
        ]
    )


def test_from_diff_rejects_unsupported_output_suffix_without_writing(
    tmp_path, monkeypatch, capsys
):
    from maid_runner.cli.commands.manifest import cmd_manifest

    _repo_with_worktree_change(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = cmd_manifest(_from_diff_args("manifests/drafts/x.json"))

    assert exit_code == 2
    assert ".json" in capsys.readouterr().err
    # The writer mkdirs its parent before writing, so an untouched manifests/
    # tree proves the rejection landed ahead of every filesystem effect.
    assert not (tmp_path / "manifests").exists()


def test_from_diff_suffix_rejection_is_distinct_from_containment_rejection(
    tmp_path, monkeypatch, capsys
):
    from maid_runner.cli.commands.manifest import cmd_manifest

    _repo_with_worktree_change(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = cmd_manifest(_from_diff_args("manifests/drafts/x.json"))

    assert exit_code == 2
    error = capsys.readouterr().err
    assert ".json" in error
    assert "must be under manifests/drafts/" not in error


def test_from_diff_force_does_not_touch_existing_file_with_unsupported_suffix(
    tmp_path, monkeypatch, capsys
):
    from maid_runner.cli.commands.manifest import cmd_manifest

    _repo_with_worktree_change(tmp_path)
    output = tmp_path / "manifests" / "drafts" / "x.json"
    output.parent.mkdir(parents=True)
    output.write_text("sentinel\n")
    monkeypatch.chdir(tmp_path)

    exit_code = cmd_manifest(_from_diff_args(output, "--force"))

    assert exit_code == 2
    assert ".json" in capsys.readouterr().err
    # A write-then-restore rollback would satisfy a bare "file absent" check.
    assert output.read_text() == "sentinel\n"


def test_from_diff_still_rejects_output_outside_drafts_directory(
    tmp_path, monkeypatch, capsys
):
    from maid_runner.cli.commands.manifest import cmd_manifest

    _repo_with_worktree_change(tmp_path)
    output = tmp_path / "manifests" / "active.manifest.yaml"
    monkeypatch.chdir(tmp_path)

    exit_code = cmd_manifest(_from_diff_args(output, "--force"))

    assert exit_code == 2
    assert "manifests/drafts" in capsys.readouterr().err
    assert not output.exists()


def test_from_diff_accepts_default_yaml_draft_path(tmp_path, monkeypatch, capsys):
    from maid_runner.cli.commands.manifest import cmd_manifest
    from maid_runner.core.manifest import load_manifest_raw

    _repo_with_worktree_change(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = cmd_manifest(_from_diff_args("manifests/drafts/demo.manifest.yaml"))

    assert exit_code == 0
    written = tmp_path / "manifests" / "drafts" / "demo.manifest.yaml"
    data = load_manifest_raw(written)
    assert "manifests/drafts/demo.manifest.yaml" in " ".join(data["validate"])
    assert "wrote" in capsys.readouterr().out.lower()


def test_from_diff_accepts_yml_output_suffix(tmp_path, monkeypatch, capsys):
    from maid_runner.cli.commands.manifest import cmd_manifest
    from maid_runner.core.manifest import load_manifest_raw

    _repo_with_worktree_change(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = cmd_manifest(_from_diff_args("manifests/drafts/custom.manifest.yml"))

    assert exit_code == 0
    written = tmp_path / "manifests" / "drafts" / "custom.manifest.yml"
    assert load_manifest_raw(written)["schema"] == "2"
    capsys.readouterr()


def test_from_diff_rejects_suffixless_output_path(tmp_path, monkeypatch, capsys):
    from maid_runner.cli.commands.manifest import cmd_manifest

    _repo_with_worktree_change(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = cmd_manifest(_from_diff_args("manifests/drafts/noextension"))

    assert exit_code == 2
    error = capsys.readouterr().err
    # Pin the reason, not just the exit code: a suffixless path is inside
    # manifests/drafts/, so rejecting it with the containment wording would
    # misdiagnose the failure.
    assert "unsupported output suffix" in error
    assert "must be under manifests/drafts/" not in error
    assert not (tmp_path / "manifests" / "drafts" / "noextension").exists()


def test_from_diff_rejects_uppercase_yaml_output_suffix(tmp_path, monkeypatch, capsys):
    from maid_runner.cli.commands.manifest import cmd_manifest

    _repo_with_worktree_change(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = cmd_manifest(_from_diff_args("manifests/drafts/custom.YAML"))

    assert exit_code == 2
    assert ".YAML" in capsys.readouterr().err
    assert not (tmp_path / "manifests" / "drafts" / "custom.YAML").exists()


def test_from_diff_dry_run_rejects_unsupported_output_suffix(
    tmp_path, monkeypatch, capsys
):
    from maid_runner.cli.commands.manifest import cmd_manifest

    _repo_with_worktree_change(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = cmd_manifest(_from_diff_args("manifests/drafts/x.json", "--dry-run"))

    assert exit_code == 2
    captured = capsys.readouterr()
    assert ".json" in captured.err
    # --dry-run must not hand back a manifest whose own validate command points
    # at a file MAID cannot load.
    assert "manifests/drafts/x.json --mode schema" not in captured.out


def test_write_from_diff_manifest_rejects_unsupported_suffix_for_library_callers(
    tmp_path, monkeypatch
):
    from maid_runner.core.manifest_from_diff import (
        FromDiffRenderError,
        write_from_diff_manifest,
    )

    monkeypatch.chdir(tmp_path)
    output = tmp_path / "manifests" / "drafts" / "library.json"

    with pytest.raises(FromDiffRenderError) as excinfo:
        write_from_diff_manifest({"not": "a valid manifest"}, output)

    # Naming the suffix rather than a schema error proves the guard runs first.
    assert ".json" in str(excinfo.value)
    assert not output.exists()
    # The writer mkdirs its parent before writing, so the guard must also
    # precede that for callers who never go through the CLI.
    assert not output.parent.exists()


def test_validate_from_diff_output_suffix_accepts_every_reader_yaml_suffix():
    from maid_runner.core.manifest import _SUFFIX_FORMATS
    from maid_runner.core.manifest_from_diff import validate_from_diff_output_suffix

    yaml_suffixes = [
        suffix
        for suffix, output_format in _SUFFIX_FORMATS.items()
        if output_format == "yaml"
    ]
    assert yaml_suffixes, "reader must map at least one suffix to the yaml format"

    for suffix in yaml_suffixes:
        assert validate_from_diff_output_suffix(f"manifests/drafts/x{suffix}") is None


def test_validate_from_diff_output_suffix_rejects_reader_suffixes_it_cannot_emit():
    from maid_runner.core.manifest import _SUFFIX_FORMATS
    from maid_runner.core.manifest_from_diff import (
        FromDiffRenderError,
        validate_from_diff_output_suffix,
    )

    non_yaml_suffixes = [
        suffix
        for suffix, output_format in _SUFFIX_FORMATS.items()
        if output_format != "yaml"
    ]
    assert ".json" in non_yaml_suffixes, "reader must still dispatch .json to json"

    for suffix in non_yaml_suffixes:
        with pytest.raises(FromDiffRenderError) as excinfo:
            validate_from_diff_output_suffix(f"manifests/drafts/x{suffix}")
        assert suffix in str(excinfo.value)
