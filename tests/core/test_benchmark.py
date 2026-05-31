"""Tests for local MAID benchmark report generation."""

from __future__ import annotations

import subprocess


def test_benchmark_stage_commands_cover_validation_test_and_verify_gates():
    from maid_runner.core.benchmark import benchmark_stage_commands

    commands = benchmark_stage_commands("custom-manifests/")

    assert [name for name, _command in commands] == [
        "schema",
        "behavioral",
        "implementation",
        "maid_test",
        "maid_verify",
    ]
    assert commands[0][1] == (
        "maid",
        "validate",
        "--manifest-dir",
        "custom-manifests/",
        "--mode",
        "schema",
        "--quiet",
    )
    assert commands[3][1] == (
        "maid",
        "test",
        "--manifest-dir",
        "custom-manifests/",
        "--json",
    )
    assert commands[4][1] == (
        "maid",
        "verify",
        "--manifest-dir",
        "custom-manifests/",
        "--keep-going",
        "--no-changed-scope",
        "--advisory",
        "--json",
    )


def test_run_benchmark_records_every_stage_and_failed_exit_code(tmp_path, monkeypatch):
    from maid_runner.core.benchmark import run_benchmark

    observed: list[tuple[str, ...]] = []

    def fake_run(command, **kwargs):
        observed.append(tuple(command))
        return subprocess.CompletedProcess(
            args=command,
            returncode=1 if "--mode" in command and "behavioral" in command else 0,
            stdout='{"success": false}' if "behavioral" in command else "",
            stderr="behavioral failed" if "behavioral" in command else "",
        )

    monkeypatch.setattr("maid_runner.core.benchmark.subprocess.run", fake_run)

    report = run_benchmark(
        [tmp_path],
        command_prefix=("uv", "run", "--project", "/runner"),
        manifest_dir="manifests/",
        repeat=1,
    )

    project = report["projects"][0]
    behavioral = project["stages"][1]

    assert report["success"] is False
    assert project["success"] is False
    assert len(project["stages"]) == 5
    assert behavioral["stage"] == "behavioral"
    assert behavioral["success"] is False
    assert behavioral["exit_code"] == 1
    assert behavioral["stderr_tail"] == "behavioral failed"
    assert len(observed) == 5
    assert observed[0][:5] == ("uv", "run", "--project", "/runner", "maid")


def test_format_benchmark_markdown_summarizes_projects_and_failures():
    from maid_runner.core.benchmark import format_benchmark_markdown

    report = {
        "success": False,
        "projects": [
            {
                "path": ".",
                "success": False,
                "stages": [
                    {
                        "stage": "schema",
                        "success": True,
                        "duration_ms": 120.0,
                        "exit_code": 0,
                        "command": ["maid", "validate", "--mode", "schema"],
                    },
                    {
                        "stage": "behavioral",
                        "success": False,
                        "duration_ms": 250.0,
                        "exit_code": 1,
                        "command": ["maid", "validate", "--mode", "behavioral"],
                    },
                ],
            }
        ],
    }

    markdown = format_benchmark_markdown(report)

    assert "| Project | Stage | Status | Duration | Exit | Command |" in markdown
    assert (
        "| . | schema | PASS | 120ms | 0 | `maid validate --mode schema` |" in markdown
    )
    assert (
        "| . | behavioral | FAIL | 250ms | 1 | " "`maid validate --mode behavioral` |"
    ) in markdown
