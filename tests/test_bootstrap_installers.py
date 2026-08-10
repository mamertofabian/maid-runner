import os
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WEBSITE = ROOT / "website"
INSTALL_SH = WEBSITE / "install.sh"
INSTALL_PS1 = WEBSITE / "install.ps1"
INSTALLER_WORKFLOW = ROOT / ".github" / "workflows" / "test-installers.yml"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _run_shell_installer(
    tmp_path: Path, *arguments: str
) -> subprocess.CompletedProcess:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    environment = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "FAKE_BIN": str(fake_bin),
        "INSTALL_LOG": str(tmp_path / "install.log"),
        "PATH": f"{fake_bin}:/usr/bin:/bin",
    }
    return subprocess.run(
        ["/bin/sh", str(INSTALL_SH), *arguments],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def _fake_uv_script() -> str:
    return """#!/bin/sh
set -eu
printf 'uv %s\\n' "$*" >> "$INSTALL_LOG"
if [ "$*" = "tool dir --bin" ]; then
    printf '%s\\n' "$FAKE_BIN"
fi
"""


def test_shell_installer_uses_existing_uv_installs_requested_version_and_verifies_maid(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(fake_bin / "uv", _fake_uv_script())
    _write_executable(
        fake_bin / "maid",
        '#!/bin/sh\nprintf \'maid %s\\n\' "$*" >> "$INSTALL_LOG"\n',
    )

    result = _run_shell_installer(tmp_path, "--version", "2.25.0")

    assert result.returncode == 0, result.stderr
    calls = (tmp_path / "install.log").read_text(encoding="utf-8")
    assert "uv tool install --python 3.12 maid-runner==2.25.0" in calls
    assert "uv tool update-shell" in calls
    assert "uv tool dir --bin" in calls
    assert "maid --version" in calls
    assert "MAID Runner is ready" in result.stdout


def test_shell_installer_bootstraps_uv_when_missing(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_uv_source = tmp_path / "fake-uv"
    fake_maid_source = tmp_path / "fake-maid"
    _write_executable(fake_uv_source, _fake_uv_script())
    _write_executable(
        fake_maid_source,
        '#!/bin/sh\nprintf \'maid %s\\n\' "$*" >> "$INSTALL_LOG"\n',
    )
    _write_executable(
        fake_bin / "curl",
        """#!/bin/sh
set -eu
printf 'curl %s\\n' "$*" >> "$INSTALL_LOG"
cat <<'INSTALL_UV'
mkdir -p "$HOME/.local/bin"
cp "$FAKE_UV_SOURCE" "$HOME/.local/bin/uv"
cp "$FAKE_MAID_SOURCE" "$FAKE_BIN/maid"
chmod +x "$HOME/.local/bin/uv" "$FAKE_BIN/maid"
INSTALL_UV
""",
    )

    environment = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "FAKE_BIN": str(fake_bin),
        "FAKE_UV_SOURCE": str(fake_uv_source),
        "FAKE_MAID_SOURCE": str(fake_maid_source),
        "INSTALL_LOG": str(tmp_path / "install.log"),
        "PATH": f"{fake_bin}:/usr/bin:/bin",
    }
    result = subprocess.run(
        ["/bin/sh", str(INSTALL_SH)],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    calls = (tmp_path / "install.log").read_text(encoding="utf-8")
    assert "curl -LsSf https://astral.sh/uv/install.sh" in calls
    assert "uv tool install --python 3.12 maid-runner" in calls
    assert "maid --version" in calls


def test_shell_installer_rejects_unsafe_or_incomplete_arguments(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(fake_bin / "uv", _fake_uv_script())

    for arguments in (
        ("--version", "2.25.0;echo unsafe"),
        ("--version",),
        ("--version", "--help"),
        ("--version", "-"),
        ("--version", "."),
        ("--unknown",),
    ):
        result = _run_shell_installer(tmp_path, *arguments)
        assert result.returncode != 0
        assert "Usage:" in result.stderr

    assert not (tmp_path / "install.log").exists()


def test_shell_installer_propagates_download_and_tool_failures(tmp_path: Path) -> None:
    download_case = tmp_path / "download"
    download_bin = download_case / "bin"
    download_bin.mkdir(parents=True)
    _write_executable(download_bin / "curl", "#!/bin/sh\nexit 22\n")

    download_result = _run_shell_installer(download_case)

    assert download_result.returncode != 0
    assert "MAID Runner is ready" not in download_result.stdout
    assert not (download_case / "install.log").exists()

    tool_case = tmp_path / "tool"
    tool_bin = tool_case / "bin"
    tool_bin.mkdir(parents=True)
    _write_executable(
        tool_bin / "uv",
        '#!/bin/sh\nprintf \'uv %s\\n\' "$*" >> "$INSTALL_LOG"\nexit 9\n',
    )
    _write_executable(
        tool_bin / "maid",
        '#!/bin/sh\nprintf \'maid %s\\n\' "$*" >> "$INSTALL_LOG"\n',
    )

    tool_result = _run_shell_installer(tool_case)

    assert tool_result.returncode == 9
    assert "MAID Runner is ready" not in tool_result.stdout
    calls = (tool_case / "install.log").read_text(encoding="utf-8")
    assert "uv tool install --python 3.12 maid-runner" in calls
    assert "maid --version" not in calls


def test_powershell_installer_contract_is_auditable_and_fail_closed() -> None:
    installer = INSTALL_PS1.read_text(encoding="utf-8")

    for required in (
        '$ErrorActionPreference = "Stop"',
        "Set-StrictMode -Version Latest",
        "Get-Command uv -ErrorAction SilentlyContinue",
        "https://astral.sh/uv/install.ps1",
        "Invoke-Expression $uvInstaller",
        "& uv tool install --python 3.12 $packageRequirement",
        "& uv tool update-shell",
        "& uv tool dir --bin",
        "Get-Command maid -ErrorAction SilentlyContinue",
        "& maid --version",
        'Write-Host "MAID Runner is ready."',
    ):
        assert required in installer

    assert installer.count("$LASTEXITCODE -ne 0") >= 4
    assert "^[0-9A-Za-z][0-9A-Za-z.!+_-]*$" in installer
    assert "http://" not in installer


def test_shell_installer_passes_shellcheck() -> None:
    result = subprocess.run(
        ["shellcheck", str(INSTALL_SH)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_readme_and_landing_page_publish_bootstrap_installers_as_primary() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    homepage = (WEBSITE / "index.html").read_text(encoding="utf-8")
    quickstart = homepage.split('id="quickstart"', 1)[1].split('class="final-cta"', 1)[
        0
    ]
    shell_command = "curl -LsSf https://maidrunner.dev/install.sh | sh"
    powershell_command = "irm https://maidrunner.dev/install.ps1 | iex"

    assert INSTALL_SH.is_file()
    assert INSTALL_PS1.is_file()
    for document in (readme, quickstart):
        assert shell_command in document
        assert powershell_command in document
        assert document.index(shell_command) < document.index("uv tool install")
        assert document.index(powershell_command) < document.index(
            "pip install maid-runner"
        )
        assert "maid init" in document

    assert "--version 2.25.0" in readme
    assert "<details>" in readme
    assert "Alternative installation methods" in readme


def test_installer_smoke_workflow_runs_local_scripts_on_all_supported_platforms() -> (
    None
):
    workflow = yaml.safe_load(INSTALLER_WORKFLOW.read_text(encoding="utf-8"))
    trigger = workflow.get("on", workflow.get(True, {}))
    jobs = workflow["jobs"]

    assert workflow["permissions"] == {"contents": "read"}
    assert set(trigger) == {"push", "pull_request", "workflow_dispatch"}
    assert trigger["push"]["branches"] == ["main"]
    for event in ("push", "pull_request"):
        assert trigger[event]["paths"] == [
            "website/install.sh",
            "website/install.ps1",
            ".github/workflows/test-installers.yml",
        ]

    assert set(jobs["unix"]["strategy"]["matrix"]["os"]) == {
        "ubuntu-latest",
        "macos-latest",
    }
    assert jobs["unix"]["runs-on"] == "${{ matrix.os }}"
    assert jobs["windows"]["runs-on"] == "windows-latest"

    unix_commands = "\n".join(step.get("run", "") for step in jobs["unix"]["steps"])
    windows_commands = "\n".join(
        step.get("run", "") for step in jobs["windows"]["steps"]
    )
    assert "sh website/install.sh" in unix_commands
    assert "./website/install.ps1" in windows_commands
