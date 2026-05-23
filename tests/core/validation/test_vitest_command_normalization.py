from maid_runner.core._vitest_command_normalization import _normalize_vitest_command


def test_normalize_vitest_command_accepts_npx_and_direct_run_forms():
    assert _normalize_vitest_command(
        ("npx", "vitest", "run", "tests/a.test.ts", "--reporter=verbose")
    ) == (
        ("npx", "vitest", "run"),
        ("tests/a.test.ts",),
        ("--reporter=verbose",),
    )
    assert _normalize_vitest_command(
        ("vitest", "run", "tests/a.test.ts", "--reporter", "verbose")
    ) == (
        ("vitest", "run"),
        ("tests/a.test.ts",),
        ("--reporter", "verbose"),
    )


def test_normalize_vitest_command_preserves_value_and_standalone_flags():
    assert _normalize_vitest_command(
        (
            "npx",
            "vitest",
            "run",
            "tests/a.test.ts",
            "--config",
            "vitest.config.ts",
            "--environment=jsdom",
            "--passWithNoTests",
            "--silent",
        )
    ) == (
        ("npx", "vitest", "run"),
        ("tests/a.test.ts",),
        (
            "--config",
            "vitest.config.ts",
            "--environment=jsdom",
            "--passWithNoTests",
            "--silent",
        ),
    )


def test_normalize_vitest_command_rejects_unbatchable_shapes():
    assert _normalize_vitest_command(()) is None
    assert _normalize_vitest_command(("vitest", "run", "--silent")) is None
    assert _normalize_vitest_command(("npx", "vitest", "tests/a.test.ts")) is None
    assert _normalize_vitest_command(("pnpm", "vitest", "tests/a.test.ts")) is None
    assert (
        _normalize_vitest_command(("pnpm", "exec", "vitest", "tests/a.test.ts")) is None
    )
    assert (
        _normalize_vitest_command(
            ("npx", "vitest", "run", "tests/a.test.ts", "--config")
        )
        is None
    )
    assert (
        _normalize_vitest_command(
            ("npx", "vitest", "run", "tests/a.test.ts", "--environment=")
        )
        is None
    )
    assert (
        _normalize_vitest_command(
            ("npx", "vitest", "run", "tests/a.test.ts", "--shard=1/2")
        )
        is None
    )
    assert (
        _normalize_vitest_command(
            ("npx", "vitest", "run", "tests/a.test.ts", "--allowOnly")
        )
        is None
    )
