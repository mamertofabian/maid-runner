from pathlib import Path

from maid_runner.core._test_command_batching import (
    _batch_compatible_test_commands,
    _batch_group_key,
    _can_batch,
    _dedupe_commands,
    _prune_covered_pytest_commands,
)


def test_batch_group_key_normalizes_uv_pytest_runner_aliases_in_uv_project():
    assert _batch_group_key(
        ("uv", "run", "pytest", "tests/test_a.py"),
        is_uv_project=lambda cwd: True,
    ) == ("pytest", ("uv", "run", "pytest"), ())
    assert _batch_group_key(
        ("uv", "run", "python", "-m", "pytest", "tests/test_a.py"),
        is_uv_project=lambda cwd: True,
    ) == ("pytest", ("uv", "run", "pytest"), ())


def test_can_batch_rejects_empty_mixed_and_non_combinable_commands():
    assert _can_batch([]) is False
    assert _can_batch([("pytest", "tests/test_a.py"), ("echo", "ok")]) is False
    assert (
        _can_batch(
            [
                ("pytest", "tests/test_a.py", "--lf"),
                ("pytest", "tests/test_b.py", "--lf"),
            ]
        )
        is False
    )


def test_batch_compatible_test_commands_combines_pytest_verbosity_differences():
    assert _batch_compatible_test_commands(
        [
            ("pytest", "tests/test_a.py", "-q"),
            ("pytest", "tests/test_b.py", "-vv"),
        ]
    ) == ("pytest", "tests/test_a.py", "tests/test_b.py")


def test_batch_compatible_test_commands_combines_vitest_targets_with_same_options():
    assert _batch_compatible_test_commands(
        [
            ("npx", "vitest", "run", "tests/a.test.ts", "--reporter=verbose"),
            ("npx", "vitest", "run", "tests/b.test.ts", "--reporter=verbose"),
        ]
    ) == (
        "npx",
        "vitest",
        "run",
        "tests/a.test.ts",
        "tests/b.test.ts",
        "--reporter=verbose",
    )


def test_batch_group_key_groups_pnpm_vitest_commands_by_runner_and_options():
    assert _batch_group_key(
        ("pnpm", "exec", "vitest", "run", "tests/a.test.ts", "--reporter=verbose")
    ) == ("vitest", ("pnpm", "exec", "vitest", "run"), ("--reporter=verbose",))


def test_dedupe_commands_keeps_stateful_pytest_duplicates():
    commands = [
        (("pytest", "tests/test_a.py"), "a"),
        (("pytest", "tests/test_a.py"), "duplicate"),
        (("pytest", "tests/test_a.py", "--lf"), "stateful-a"),
        (("pytest", "tests/test_a.py", "--lf"), "stateful-b"),
        (("python", "-c", "raise SystemExit(0)"), "noop-a"),
        (("python", "-c", "raise SystemExit(0)"), "noop-b"),
    ]

    assert _dedupe_commands(commands, cwd=Path(".")) == [
        (("pytest", "tests/test_a.py"), "a"),
        (("pytest", "tests/test_a.py", "--lf"), "stateful-a"),
        (("pytest", "tests/test_a.py", "--lf"), "stateful-b"),
        (("python", "-c", "raise SystemExit(0)"), "noop-a"),
    ]


def test_prune_covered_pytest_commands_keeps_focused_targets_over_directory_target():
    commands = [
        (("pytest", "tests/", "-v"), "broad"),
        (("pytest", "tests/test_a.py", "-q"), "focused"),
        (("python", "-c", "raise SystemExit(0)"), "noop"),
    ]

    assert _prune_covered_pytest_commands(commands, cwd=Path(".")) == [
        (("pytest", "tests/test_a.py", "-q"), "focused"),
        (("python", "-c", "raise SystemExit(0)"), "noop"),
    ]
