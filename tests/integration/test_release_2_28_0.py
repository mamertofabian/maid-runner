"""Release metadata and notes for the Rust/Solidity minor release."""

from pathlib import Path
import re
import subprocess

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from maid_runner import __version__


def test_package_lock_and_cli_report_2_28_0():
    root = Path(__file__).resolve().parents[2]
    project = tomllib.loads((root / "pyproject.toml").read_text())
    lock = tomllib.loads((root / "uv.lock").read_text())
    package = next(p for p in lock["package"] if p["name"] == "maid-runner")

    assert project["project"]["version"] == "2.28.0"
    assert package["version"] == "2.28.0"
    assert __version__ == "2.28.0"
    result = subprocess.run(
        ["maid", "--version"], check=True, capture_output=True, text=True
    )
    assert result.stdout.strip() == "maid 2.28.0"


def test_release_notes_include_plugins_and_complete_pending_inventory():
    root = Path(__file__).resolve().parents[2]
    changelog = (root / "CHANGELOG.md").read_text()
    assert "## [2.28.0] - 2026-10-02" in changelog
    unreleased, release = changelog.split("## [2.28.0] - 2026-10-02", 1)
    assert "## [Unreleased]" in unreleased
    assert "### Added" not in unreleased
    release = release.split("\n## [", 1)[0]
    for entry in (
        "Rust Cargo validation support",
        "Solidity Foundry validation support",
        "Compiler-backed TypeScript return contracts",
        "Task-scoped deep verification",
        "Plan revision context",
        "Promotion evidence preservation",
        "GitHub workflow triggers",
        "Pytest command integrity",
        "Deno full-permission test discovery",
        "Vitest command coverage",
        "Node module test locks",
        "Python Playwright assertions",
        "Python variadic tuple annotations",
        "JavaScript and TypeScript assertion boundaries",
        "JSX raw ampersands",
        "Generated Supabase TypeScript headers",
    ):
        assert f"**{entry}**" in release
    for detail in (
        "maid-validator-rust",
        "maid-validator-solidity",
        "`cargo test`",
        "`forge test`",
        "`.rs`",
        "`.sol`",
        "inline",
    ):
        assert detail in release
    assert (
        "[Unreleased]: https://github.com/mamertofabian/maid-runner/compare/v2.28.0...HEAD"
        in changelog
    )
    assert (
        "[2.28.0]: https://github.com/mamertofabian/maid-runner/compare/v2.27.6...v2.28.0"
        in changelog
    )
    assert not re.search(r"^## \[2\.27\.7\]", changelog, re.M)


def test_roadmap_reports_prepared_release_version_and_date():
    root = Path(__file__).resolve().parents[2]
    roadmap = (root / "docs/ROADMAP.md").read_text()
    assert "**Current Version:** 2.28.0" in roadmap
    assert "**Last Updated:** 2026-10-02" in roadmap
    assert "The local CLI reports `maid 2.28.0`." in roadmap
