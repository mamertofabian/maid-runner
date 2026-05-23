from maid_runner.core._test_command_batching import _batch_compatible_test_commands
from maid_runner.core._vitest_command_normalization import _normalize_vitest_command
from maid_runner.core.result import TestRunResult
from maid_runner.core.test_runner import run_tests
from maid_runner.core.types import TestStream


def test_normalize_vitest_command_accepts_pnpm_exec_and_pnpm_direct_forms():
    assert _normalize_vitest_command(
        ("pnpm", "exec", "vitest", "run", "src/a.test.ts", "--reporter=verbose")
    ) == (
        ("pnpm", "exec", "vitest", "run"),
        ("src/a.test.ts",),
        ("--reporter=verbose",),
    )
    assert _normalize_vitest_command(
        ("pnpm", "vitest", "run", "src/b.test.ts", "--environment", "jsdom")
    ) == (
        ("pnpm", "vitest", "run"),
        ("src/b.test.ts",),
        ("--environment", "jsdom"),
    )


def test_normalize_vitest_command_rejects_non_run_pnpm_vitest_forms():
    assert (
        _normalize_vitest_command(("pnpm", "exec", "vitest", "src/a.test.ts")) is None
    )
    assert _normalize_vitest_command(("pnpm", "vitest", "src/a.test.ts")) is None
    assert (
        _normalize_vitest_command(
            ("pnpm", "exec", "vitest", "run", "src/a.test.ts", "--shard=1/2")
        )
        is None
    )
    assert (
        _normalize_vitest_command(
            (
                "pnpm",
                "--dir",
                "frontend",
                "exec",
                "vitest",
                "run",
                "src/a.test.ts",
            )
        )
        is None
    )


def test_batch_compatible_test_commands_combines_pnpm_exec_vitest_targets():
    assert _batch_compatible_test_commands(
        [
            ("pnpm", "exec", "vitest", "run", "src/a.test.ts", "--reporter=verbose"),
            ("pnpm", "exec", "vitest", "run", "src/b.test.ts", "--reporter=verbose"),
            ("pnpm", "exec", "vitest", "run", "src/a.test.ts", "--reporter=verbose"),
        ]
    ) == (
        "pnpm",
        "exec",
        "vitest",
        "run",
        "src/a.test.ts",
        "src/b.test.ts",
        "--reporter=verbose",
    )


def test_run_tests_batches_pnpm_vitest_commands_from_active_manifests(
    monkeypatch,
    tmp_path,
):
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    for slug, target in (("first", "src/a.test.ts"), ("second", "src/b.test.ts")):
        (manifests / f"{slug}.manifest.yaml").write_text(
            f"""schema: "2"
goal: "Batch pnpm Vitest"
type: snapshot
files:
  create:
    - path: src/{slug}.ts
      artifacts:
        - kind: function
          name: {slug}
validate:
  - pnpm exec vitest run {target} --reporter=verbose
"""
        )

    observed: list[tuple[str, ...]] = []

    def fake_run_command(command, **kwargs):
        observed.append(command)
        return TestRunResult(
            manifest_slug=kwargs.get("manifest_slug", ""),
            command=command,
            exit_code=0,
            stdout="",
            stderr="",
            duration_ms=1.0,
            stream=kwargs.get("stream", TestStream.IMPLEMENTATION),
        )

    monkeypatch.setattr("maid_runner.core.test_runner.run_command", fake_run_command)

    result = run_tests(manifest_dir="manifests", project_root=tmp_path)

    assert result.success is True
    assert result.total == 1
    assert result.results[0].manifest_slug == "batch"
    assert observed == [
        (
            "pnpm",
            "exec",
            "vitest",
            "run",
            "src/a.test.ts",
            "src/b.test.ts",
            "--reporter=verbose",
        )
    ]
