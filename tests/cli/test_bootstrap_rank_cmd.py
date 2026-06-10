"""Tests for CLI ranked bootstrap adoption planning."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from maid_runner.cli.commands._main import build_parser
from maid_runner.cli.commands.bootstrap import cmd_bootstrap


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


def _commit_all(project_dir: Path, message: str) -> None:
    _git(project_dir, "add", ".")
    _git(project_dir, "commit", "-m", message)


def test_bootstrap_rank_json_dispatches_through_main(tmp_path, monkeypatch, capsys):
    from maid_runner.cli.commands._main import main

    _init_repo(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "target.py").write_text("def target() -> None:\n    pass\n")
    (tmp_path / "src" / "importer.py").write_text(
        "from src.target import target\n\n\ndef use() -> None:\n    target()\n"
    )
    _commit_all(tmp_path, "initial")
    monkeypatch.chdir(tmp_path)

    exit_code = main(["bootstrap", "--rank", "--limit", "5", "--json"])

    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["limit"] == 5
    assert data["total_candidates"] == 2
    assert data["candidates"][0] == {
        "rank": 1,
        "path": "src/target.py",
        "churn": 1,
        "inbound_refs": 1,
        "public_artifacts": 1,
    }
    assert "score" not in data["candidates"][0]
    assert not list((tmp_path / "manifests").glob("*.manifest.yaml"))


def test_bootstrap_rank_parser_registers_flags():
    parser = build_parser()

    args = parser.parse_args(["bootstrap", "--rank", "--limit", "5"])

    assert args.rank is True
    assert args.limit == 5
    assert callable(cmd_bootstrap)


def test_bootstrap_rank_default_limit_is_twenty(tmp_path, monkeypatch, capsys):
    from maid_runner.cli.commands._main import main

    for index in range(21):
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / f"module_{index:02d}.py").write_text(
            f"VALUE_{index} = {index}\n"
        )
    monkeypatch.chdir(tmp_path)

    exit_code = main(["bootstrap", "--rank", "--json"])

    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["limit"] == 20
    assert data["total_candidates"] == 21
    assert len(data["candidates"]) == 20


def test_bootstrap_rank_human_output_lists_raw_signal_values(
    tmp_path, monkeypatch, capsys
):
    from maid_runner.cli.commands._main import main

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def run() -> None:\n    pass\n")
    monkeypatch.chdir(tmp_path)

    exit_code = main(["bootstrap", str(tmp_path), "--rank"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Ranked bootstrap candidates: 1 of 1" in output
    assert "1. src/app.py" in output
    assert "churn=0" in output
    assert "inbound_refs=0" in output
    assert "public_artifacts=1" in output
