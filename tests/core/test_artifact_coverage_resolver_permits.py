"""Behavioral regression for persistent resolver child-permit starvation."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_xdist_coverage_keeps_nested_process_capacity_with_persistent_resolvers(
    tmp_path: Path,
) -> None:
    from maid_runner.core._runtime_command_executor import (
        SubprocessRuntimeCommandExecutor,
    )

    pytest.importorskip("fcntl")
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable")
    typescript = subprocess.run(
        [node, "-e", "require.resolve('typescript')"],
        check=False,
        capture_output=True,
        text=True,
    )
    if typescript.returncode != 0:
        pytest.skip("TypeScript npm dependency is unavailable")

    project = tmp_path / "project"
    sources = tuple(project / "src" / f"{name}.py" for name in ("alpha", "beta"))
    tests = tuple(project / "tests" / f"test_{name}.py" for name in ("alpha", "beta"))
    sources[0].parent.mkdir(parents=True)
    tests[0].parent.mkdir(parents=True)
    for name, source, test_file in zip(("alpha", "beta"), sources, tests):
        source.write_text(f"def {name}():\n    return '{name}'\n")
        test_file.write_text(
            "import os\n"
            "import signal\n"
            "import subprocess\n"
            "import sys\n"
            "import time\n"
            "from pathlib import Path\n\n"
            "from maid_runner.core.ts_compiler_resolver import "
            "resolve_import_with_compiler\n"
            f"from src.{name} import {name}\n\n"
            f"def test_{name}_after_persistent_resolver():\n"
            "    root = Path.cwd()\n"
            f"    resolve_import_with_compiler('@missing/{name}', 'src/{name}', root / '{name}')\n"
            "    ready = root / '.pytest_cache' / f'{os.environ[\"PYTEST_XDIST_WORKER\"]}.resolver-ready'\n"
            "    ready.parent.mkdir(exist_ok=True)\n"
            "    ready.touch()\n"
            "    def fail_if_starved(_signum, _frame):\n"
            "        raise TimeoutError('nested subprocess permit was starved')\n"
            "    signal.signal(signal.SIGALRM, fail_if_starved)\n"
            "    signal.alarm(3)\n"
            "    try:\n"
            "        while len(tuple(ready.parent.glob('*.resolver-ready'))) < 2:\n"
            "            time.sleep(0.01)\n"
            "        subprocess.run([sys.executable, '-c', 'pass'], check=True)\n"
            "    finally:\n"
            "        signal.alarm(0)\n"
            f"    assert {name}() == '{name}'\n"
        )

    record = SubprocessRuntimeCommandExecutor().execute(
        (
            "tests/",
            "-q",
            "-n",
            "2",
            "--dist",
            "loadscope",
        ),
        {str(source.resolve()) for source in sources},
        project,
        timeout_seconds=15,
    )

    assert record.returncode == 0, record.stderr or record.stdout
    for source in sources:
        execution = record.execution_data[str(source.resolve())]
        assert execution.executed_lines
        assert source.stem in execution.called_qualnames
