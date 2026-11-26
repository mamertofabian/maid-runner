"""Release metadata and notes for the 2.29.0 minor version."""

from pathlib import Path
import re
import subprocess

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from maid_runner import __version__


_ROOT = Path(__file__).resolve().parents[2]
_HEADING = "## [2.29.0] - 2026-11-26"


def _release_section() -> str:
    changelog = (_ROOT / "CHANGELOG.md").read_text()
    _, release = changelog.split(_HEADING, 1)
    return release.split("\n## [", 1)[0]


def test_package_lock_and_cli_report_2_29_0() -> None:
    project = tomllib.loads((_ROOT / "pyproject.toml").read_text())
    lock = tomllib.loads((_ROOT / "uv.lock").read_text())
    package = next(item for item in lock["package"] if item["name"] == "maid-runner")

    assert project["project"]["version"] == "2.29.0"
    assert package["version"] == "2.29.0"
    assert __version__ == "2.29.0"
    result = subprocess.run(
        ["maid", "--version"], check=True, capture_output=True, text=True
    )
    assert result.stdout.strip() == "maid 2.29.0"


def test_changelog_places_minor_release_after_empty_unreleased_section() -> None:
    changelog = (_ROOT / "CHANGELOG.md").read_text()

    unreleased, _ = changelog.split(_HEADING, 1)

    assert "## [Unreleased]" in unreleased
    assert "### " not in unreleased.split("## [Unreleased]", 1)[1]
    assert not re.search(r"^## \[2\.28\.2\]", changelog, re.M)


def test_release_notes_cover_antigravity_features_and_typescript_reexport_fix() -> None:
    release = _release_section()

    assert "### Added" in release
    assert "### Fixed" in release
    added_part, fixed_part = release.split("### Fixed", 1)

    for entry in (
        "**Antigravity hook scope-check support**",
        "**Antigravity workspace initialization**",
        "**Antigravity user-level onboarding skill**",
    ):
        assert entry in added_part

    for detail in (
        "`--format antigravity`",
        "`toolCall.args`",
        "`cwd`",
        "`maid init --tool antigravity`",
        "`.agents/`",
        "`AGENTS.md`",
        "`../scripts/maid`",
        "`~/.gemini/config/skills/maid-onboard`",
        "`maid skills install`",
        "`maid skills uninstall`",
    ):
        assert detail in added_part

    assert "**TypeScript function re-exports**" in fixed_part
    assert "named" in fixed_part
    assert "originating" in fixed_part
    assert "E300" in fixed_part


def test_changelog_preserves_prior_release_and_compare_links() -> None:
    changelog = (_ROOT / "CHANGELOG.md").read_text()

    assert "## [2.28.1] - 2026-10-23" in changelog
    assert "**Deno dependency-flag test discovery**" in changelog
    assert "`Deno.test({ name, fn })` remains unrecognized" in changelog
    assert (
        "[Unreleased]: https://github.com/mamertofabian/maid-runner/compare/v2.29.0...HEAD"
        in changelog
    )
    assert (
        "[2.29.0]: https://github.com/mamertofabian/maid-runner/compare/v2.28.1...v2.29.0"
        in changelog
    )
    assert (
        "[2.28.1]: https://github.com/mamertofabian/maid-runner/compare/v2.28.0...v2.28.1"
        in changelog
    )
    assert "2.28.2" not in changelog


def test_roadmap_reports_prepared_minor_version_and_antigravity_init_tool() -> None:
    roadmap = (_ROOT / "docs/ROADMAP.md").read_text()

    assert "**Current Version:** 2.29.0" in roadmap
    assert "**Last Updated:** 2026-11-26" in roadmap
    assert "The local CLI reports `maid 2.29.0`." in roadmap
    assert (
        "`maid init --tool`\n"
        "currently accepts `claude`, `codex`, `antigravity`, `cursor`, `windsurf`,\n"
        "`generic`, and `auto`."
    ) in roadmap
