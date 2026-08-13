"""Behavioral contract for declaration-bound knockout evidence caches."""

from __future__ import annotations

from pathlib import Path

import yaml

from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import TestRunResult
from maid_runner.core.types import TestStream


class _RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def execute(
        self,
        command,
        project_root,
        manifest_slug,
        environment_overrides=None,
        environment_removals=(),
    ) -> TestRunResult:
        root = Path(project_root)
        mutated = (
            'raise NotImplementedError("maid-knockout")'
            in (root / "src/target.py").read_text()
        )
        self.calls.append((manifest_slug, tuple(command)))
        return TestRunResult(
            manifest_slug=manifest_slug,
            command=tuple(command),
            exit_code=1 if mutated else 0,
            stdout="",
            stderr="",
            duration_ms=1.0,
            stream=TestStream.IMPLEMENTATION,
        )


def test_knockout_cache_does_not_cross_distinct_declaration_sets(
    tmp_path: Path,
) -> None:
    from maid_runner.core.knockout import run_knockout

    first, second = _write_project(tmp_path)
    executor = _RecordingExecutor()

    first_report = run_knockout(
        first,
        tmp_path,
        executor=executor,
        allow_dirty=True,
    )
    second_report = run_knockout(
        second,
        tmp_path,
        executor=executor,
        allow_dirty=True,
    )

    assert first_report.success is True
    assert second_report.success is True
    assert [slug for slug, _command in executor.calls] == [
        "first",
        "first",
        "first",
        "second",
        "second",
        "second",
    ]
    assert second_report.results[0].cache_hit is False


def _write_project(root: Path):
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "manifests").mkdir()
    (root / ".venv/bin").mkdir(parents=True)
    (root / ".venv/pyvenv.cfg").write_text(
        "home = /usr\ninclude-system-site-packages = false\n"
    )
    (root / ".venv/bin/python").write_text("#!/bin/sh\n")
    (root / "src/target.py").write_text("def target() -> str:\n    return 'target'\n")
    (root / "tests/test_target.py").write_text(
        "from src.target import target\n\n"
        "def test_target():\n"
        "    assert target() == 'target'\n"
    )
    manifests = []
    for slug in ("first", "second"):
        payload = {
            "schema": "2",
            "goal": f"Knock out target for {slug}",
            "type": "fix",
            "created": "2026-08-13T12:46:00Z",
            "files": {
                "edit": [
                    {
                        "path": "src/target.py",
                        "artifacts": [
                            {
                                "kind": "function",
                                "name": "target",
                                "args": [],
                                "returns": "str",
                            }
                        ],
                    }
                ],
                "read": ["tests/test_target.py"],
            },
            "validate": [f"{slug}-check tests/test_target.py"],
        }
        path = root / f"manifests/{slug}.manifest.yaml"
        path.write_text(yaml.safe_dump(payload, sort_keys=False))
        manifests.append(load_manifest(path))
    return tuple(manifests)
