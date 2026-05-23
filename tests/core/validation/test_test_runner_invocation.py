"""Focused characterization tests for test-runner invocation detection."""

from maid_runner.core._test_runner_invocation import (
    _has_non_executing_test_runner_mode,
    _has_test_runner_selector,
    _runs_django_test_runner,
    _test_runner_invocation,
    _test_runner_target_scan_segment,
)


def test_invocation_unwraps_uv_python_module_pytest():
    invocation = _test_runner_invocation(
        ["uv", "run", "python", "-m", "pytest", "tests/test_gate.py", "-q"]
    )

    assert invocation == ("pytest", ["tests/test_gate.py", "-q"])


def test_invocation_unwraps_docker_django_manage_py():
    assert (
        _runs_django_test_runner(
            [
                "docker",
                "exec",
                "tools-api",
                "python",
                "manage.py",
                "test",
                "app.tests.test_gate",
            ]
        )
        is True
    )


def test_target_scan_segment_strips_package_runner_wrapper():
    segment = _test_runner_target_scan_segment(
        ["pnpm", "vitest", "run", "src/current.test.ts"]
    )

    assert segment == ["vitest", "run", "src/current.test.ts"]


def test_invocation_unwraps_package_runner_options_before_exec():
    invocation = _test_runner_invocation(
        [
            "pnpm",
            "--dir",
            "frontend",
            "exec",
            "vitest",
            "run",
            "tests/current.test.ts",
        ]
    )

    assert invocation == ("vitest", ["run", "tests/current.test.ts"])


def test_target_scan_preserves_package_runner_cwd_option_before_exec():
    segment = _test_runner_target_scan_segment(
        [
            "pnpm",
            "--dir",
            "frontend",
            "exec",
            "vitest",
            "run",
            "tests/current.test.ts",
        ]
    )

    assert segment == ["--dir", "frontend", "vitest", "run", "tests/current.test.ts"]


def test_non_executing_mode_detects_pytest_addopts_collect_only():
    assert (
        _has_non_executing_test_runner_mode(
            ["env", "PYTEST_ADDOPTS=--collect-only", "python", "-m", "pytest", "tests"]
        )
        is True
    )


def test_selector_detection_rejects_clustered_pytest_short_selector():
    assert _has_test_runner_selector(["pytest", "-qksmoke", "tests"]) is True
