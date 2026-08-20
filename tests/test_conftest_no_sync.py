"""Behavioral contract for isolated pytest payload bootstrap policy."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    ("uv_no_sync", "expect_sync"),
    [("1", False), (None, True), ("0", True)],
)
def test_payload_sync_fixture_honors_explicit_no_sync_policy(
    tmp_path: Path,
    uv_no_sync: str | None,
    expect_sync: bool,
) -> None:
    project = tmp_path / f"case-{uv_no_sync or 'absent'}"
    tests = project / "tests"
    scripts = project / "scripts"
    tests.mkdir(parents=True)
    scripts.mkdir()
    shutil.copy2(Path("tests/conftest.py"), tests / "conftest.py")
    (scripts / "__init__.py").write_text("", encoding="utf-8")
    (scripts / "sync_claude_files.py").write_text(
        "from pathlib import Path\n\n"
        "def main():\n"
        "    output = Path('maid_runner/claude/manifest.json')\n"
        "    output.parent.mkdir(parents=True, exist_ok=True)\n"
        "    output.write_text('{}', encoding='utf-8')\n",
        encoding="utf-8",
    )
    (tests / "test_payload_state.py").write_text(
        "import os\n"
        "from pathlib import Path\n\n"
        "def test_payload_state():\n"
        "    expected = os.environ['EXPECT_PAYLOAD_SYNC'] == '1'\n"
        "    assert Path('maid_runner/claude/manifest.json').exists() is expected\n",
        encoding="utf-8",
    )
    environment = dict(os.environ)
    environment["EXPECT_PAYLOAD_SYNC"] = "1" if expect_sync else "0"
    if uv_no_sync is not None:
        environment["UV_NO_SYNC"] = uv_no_sync
    else:
        environment.pop("UV_NO_SYNC", None)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
