"""Behavioral tests for MAID's pgTAP-to-red-evidence adapter."""

from __future__ import annotations

import argparse
import subprocess

import pytest


def _args(*psql_args: str, psql: str = "psql") -> argparse.Namespace:
    return argparse.Namespace(psql=psql, psql_args=list(psql_args))


def _completed(
    exit_code: int, *, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        ["psql"], exit_code, stdout=stdout, stderr=stderr
    )


@pytest.mark.parametrize(
    "psql_args",
    [
        (
            "--dbname",
            "postgresql://localhost/app",
            "--file=supabase/tests/demo.test.sql",
        ),
        ("-qfsupabase/tests/demo.test.sql",),
    ],
)
def test_pgtap_command_runs_psql_with_forced_failure_semantics_and_passes_output(
    psql_args: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands._main import main
    from maid_runner.cli.commands import pgtap
    from maid_runner.cli.commands.pgtap import cmd_pgtap

    assert callable(cmd_pgtap)
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object):
        calls.append(command)
        assert kwargs == {"capture_output": True, "text": True}
        return _completed(0, stdout="1..1\nok 1 - durable contract\n")

    monkeypatch.setattr(pgtap.subprocess, "run", fake_run)

    exit_code = main(["pgtap", "--", *psql_args])

    assert exit_code == 0
    assert calls == [
        [
            "psql",
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            *psql_args,
        ]
    ]
    captured = capsys.readouterr()
    assert captured.out == "1..1\nok 1 - durable contract\n"
    assert captured.err == ""


@pytest.mark.parametrize(
    "stdout,stderr",
    [
        ("1..1\nnot ok 1 - expected recovered recipient\n", ""),
        (
            "",
            "psql:tests/demo.test.sql:42: ERROR: pgTAP failures:\n"
            "not ok 2 - expected durable event\n",
        ),
    ],
)
def test_pgtap_command_maps_explicit_assertion_failure_to_red_exit_one(
    stdout: str,
    stderr: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands import pgtap
    from maid_runner.cli.commands.pgtap import cmd_pgtap

    monkeypatch.setattr(
        pgtap.subprocess,
        "run",
        lambda *args, **kwargs: _completed(3, stdout=stdout, stderr=stderr),
    )

    exit_code = cmd_pgtap(_args("--", "-f", "tests/demo.test.sql"))

    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.out == stdout
    assert captured.err.startswith(stderr)
    assert "pgTAP assertion failure" in captured.err
    assert "psql exit 3" in captured.err


@pytest.mark.parametrize(
    "psql_exit,stderr",
    [
        (1, "psql: tests/missing.sql: No such file or directory\n"),
        (2, "psql: error: connection to server failed\n"),
        (3, "psql:tests/demo.sql:8: ERROR: relation does not exist\n"),
        (3, 'ERROR: syntax error at or near "not ok 7 -"\n'),
        (3, 'ERROR: invalid input syntax for text: "pgTAP failures:"\n'),
        (3, 'ERROR: invalid input syntax for text: "x\nnot ok 7 - quoted"\n'),
        (
            3,
            'ERROR: invalid input syntax for text: "x\n'
            'ERROR: pgTAP failures: quoted payload"\n',
        ),
    ],
)
def test_pgtap_command_keeps_psql_infrastructure_and_setup_failures_invalid(
    psql_exit: int,
    stderr: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands import pgtap
    from maid_runner.cli.commands.pgtap import cmd_pgtap

    monkeypatch.setattr(
        pgtap.subprocess,
        "run",
        lambda *args, **kwargs: _completed(psql_exit, stderr=stderr),
    )

    exit_code = cmd_pgtap(_args("--", "-f", "tests/demo.test.sql"))

    assert exit_code == 2
    captured = capsys.readouterr()
    assert captured.err.startswith(stderr)
    assert f"psql exit {psql_exit}" in captured.err
    assert "invalid red-phase evidence" in captured.err


@pytest.mark.parametrize(
    "psql_args",
    [
        ("--", "--dbname", "postgresql://localhost/app"),
        ("--", "--file"),
        ("--", "-V", "-f", "tests/demo.test.sql"),
        ("--", "--version", "-f", "tests/demo.test.sql"),
        ("--", "--ver", "-f", "tests/demo.test.sql"),
        ("--", "-?", "-f", "tests/demo.test.sql"),
        ("--", "--help", "-f", "tests/demo.test.sql"),
        ("--", "--he", "-f", "tests/demo.test.sql"),
        ("--", "-l", "-f", "tests/demo.test.sql"),
        ("--", "--list", "-f", "tests/demo.test.sql"),
        ("--", "--li", "-f", "tests/demo.test.sql"),
        ("--", "-v", "ON_ERROR_STOP=0", "-f", "tests/demo.test.sql"),
        ("--", "-vON_ERROR_STOP=0", "-f", "tests/demo.test.sql"),
        ("--", "-XvON_ERROR_STOP=0", "-f", "tests/demo.test.sql"),
        ("--", "-qvON_ERROR_STOP=0", "-f", "tests/demo.test.sql"),
        ("--", "--set=on_error_stop=0", "-f", "tests/demo.test.sql"),
        ("--", "--se=on_error_stop=0", "-f", "tests/demo.test.sql"),
        ("--", "--variable=ON_ERROR_STOP=0", "-f", "tests/demo.test.sql"),
        ("--", "--var=ON_ERROR_STOP=0", "-f", "tests/demo.test.sql"),
    ],
)
def test_pgtap_command_rejects_missing_file_or_failure_semantics_override(
    psql_args: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands import pgtap
    from maid_runner.cli.commands.pgtap import cmd_pgtap

    def fail_if_run(*args: object, **kwargs: object):
        raise AssertionError("psql must not run for an unsafe adapter invocation")

    monkeypatch.setattr(pgtap.subprocess, "run", fail_if_run)

    exit_code = cmd_pgtap(_args(*psql_args))

    assert exit_code == 2
    assert "Error:" in capsys.readouterr().err


def test_pgtap_command_reports_psql_spawn_failure_as_invalid(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands import pgtap
    from maid_runner.cli.commands.pgtap import cmd_pgtap

    def raise_spawn_error(*args: object, **kwargs: object):
        raise FileNotFoundError("psql executable not found")

    monkeypatch.setattr(pgtap.subprocess, "run", raise_spawn_error)

    exit_code = cmd_pgtap(_args("--", "-f", "tests/demo.test.sql"))

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert "psql executable not found" in captured.err
