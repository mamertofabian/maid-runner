"""Tests for the `maid benchmark` CLI command."""

from __future__ import annotations

import argparse
import json


def test_cmd_benchmark_writes_json_and_markdown_outputs(tmp_path, monkeypatch, capsys):
    from maid_runner.cli.commands.benchmark import cmd_benchmark

    report = {
        "success": True,
        "projects": [
            {
                "path": ".",
                "success": True,
                "stages": [],
            }
        ],
    }

    def fake_run_benchmark(*args, **kwargs):
        return report

    def fake_format_benchmark_markdown(value):
        assert value is report
        return "| Project | Stage |\n"

    monkeypatch.setattr(
        "maid_runner.cli.commands.benchmark.run_benchmark",
        fake_run_benchmark,
    )
    monkeypatch.setattr(
        "maid_runner.cli.commands.benchmark.format_benchmark_markdown",
        fake_format_benchmark_markdown,
    )

    json_output = tmp_path / "benchmark.json"
    markdown_output = tmp_path / "benchmark.md"

    exit_code = cmd_benchmark(
        argparse.Namespace(
            projects=["."],
            manifest_dir="manifests/",
            command_prefix=[],
            repeat=1,
            json_output=str(json_output),
            markdown_output=str(markdown_output),
            json=False,
        )
    )

    assert exit_code == 0
    assert json.loads(json_output.read_text(encoding="utf-8")) == report
    assert markdown_output.read_text(encoding="utf-8") == "| Project | Stage |\n"
    assert capsys.readouterr().out == "| Project | Stage |\n\n"


def test_cmd_benchmark_returns_failure_when_stage_fails(monkeypatch, capsys):
    from maid_runner.cli.commands.benchmark import cmd_benchmark

    report = {
        "success": False,
        "projects": [
            {
                "path": ".",
                "success": False,
                "stages": [
                    {
                        "stage": "maid_verify",
                        "success": False,
                        "exit_code": 1,
                    }
                ],
            }
        ],
    }

    monkeypatch.setattr(
        "maid_runner.cli.commands.benchmark.run_benchmark",
        lambda *args, **kwargs: report,
    )
    monkeypatch.setattr(
        "maid_runner.cli.commands.benchmark.format_benchmark_markdown",
        lambda value: "markdown should not print in json mode",
    )

    exit_code = cmd_benchmark(
        argparse.Namespace(
            projects=[],
            manifest_dir="manifests/",
            command_prefix=[],
            repeat=1,
            json_output=None,
            markdown_output=None,
            json=True,
        )
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert payload["projects"][0]["stages"][0]["success"] is False
