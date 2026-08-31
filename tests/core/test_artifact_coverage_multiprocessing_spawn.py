"""Behavioral regression for spawn-based children under artifact coverage."""

from __future__ import annotations

from pathlib import Path


def test_artifact_coverage_preserves_overlapping_spawn_children(
    tmp_path: Path,
) -> None:
    from maid_runner.core._runtime_command_executor import (
        SubprocessRuntimeCommandExecutor,
    )

    project = tmp_path / "project"
    source = project / "src" / "target.py"
    test_file = project / "tests" / "test_spawn.py"
    source.parent.mkdir(parents=True)
    test_file.parent.mkdir(parents=True)
    source.write_text(
        "def observed(value: str) -> str:\n" "    return value\n",
        encoding="utf-8",
    )
    test_file.write_text(
        "import multiprocessing\n"
        "import sys\n\n"
        "from src.target import observed\n\n"
        "def child(ready, release, results, value):\n"
        "    ready.put(value)\n"
        "    if not release.wait(5):\n"
        "        raise TimeoutError('overlapping child was not released')\n"
        "    results.put(observed(value))\n\n"
        "def test_spawned_children_overlap():\n"
        "    context = multiprocessing.get_context('spawn')\n"
        "    ready = context.Queue()\n"
        "    release = context.Event()\n"
        "    results = context.Queue()\n"
        "    children = [\n"
        "        context.Process(target=child, args=(ready, release, results, value))\n"
        "        for value in ('first', 'second')\n"
        "    ]\n"
        "    original_argv = sys.argv\n"
        "    sys.argv = ['consumer-entrypoint', '--unrelated-child-argument']\n"
        "    try:\n"
        "        children[0].start()\n"
        "        assert ready.get(timeout=5) == 'first'\n"
        "        children[1].start()\n"
        "        assert ready.get(timeout=5) == 'second'\n"
        "        assert all(child_process.is_alive() for child_process in children)\n"
        "        release.set()\n"
        "        for child_process in children:\n"
        "            child_process.join(timeout=5)\n"
        "        assert [child_process.exitcode for child_process in children] == [0, 0]\n"
        "        assert sorted([results.get(timeout=5), results.get(timeout=5)]) == [\n"
        "            'first',\n"
        "            'second',\n"
        "        ]\n"
        "        assert observed('parent') == 'parent'\n"
        "    finally:\n"
        "        sys.argv = original_argv\n"
        "        release.set()\n"
        "        for child_process in children:\n"
        "            if child_process.is_alive():\n"
        "                child_process.terminate()\n"
        "                child_process.join(timeout=2)\n",
        encoding="utf-8",
    )

    record = SubprocessRuntimeCommandExecutor().execute(
        ("tests/test_spawn.py", "-q"),
        {str(source.resolve())},
        project,
        timeout_seconds=30,
    )

    assert record.returncode == 0, record.stderr or record.stdout
    execution = record.execution_data[str(source.resolve())]
    assert execution.executed_lines
    assert "observed" in execution.called_qualnames
