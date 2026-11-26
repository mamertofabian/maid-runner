"""Release metadata and notes for the 2.28.2 patch version."""

from pathlib import Path
import subprocess

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from maid_runner import __version__


_ROOT = Path(__file__).resolve().parents[2]
_HEADING = "## [2.28.2] - 2026-11-26"


def _release_section() -> str:
    changelog = (_ROOT / "CHANGELOG.md").read_text()
    _, release = changelog.split(_HEADING, 1)
    return release.split("\n## [", 1)[0]


def test_package_lock_and_cli_report_2_28_2():
    project = tomllib.loads((_ROOT / "pyproject.toml").read_text())
    lock = tomllib.loads((_ROOT / "uv.lock").read_text())
    package = next(item for item in lock["package"] if item["name"] == "maid-runner")

    assert project["project"]["version"] == "2.28.2"
    assert package["version"] == "2.28.2"
    assert __version__ == "2.28.2"
    result = subprocess.run(
        ["maid", "--version"], check=True, capture_output=True, text=True
    )
    assert result.stdout.strip() == "maid 2.28.2"


def test_changelog_places_patch_after_empty_unreleased_section():
    changelog = (_ROOT / "CHANGELOG.md").read_text()

    unreleased, _ = changelog.split(_HEADING, 1)

    assert "## [Unreleased]" in unreleased
    assert "### " not in unreleased.split("## [Unreleased]", 1)[1]


def test_patch_notes_describe_the_named_function_reexport_fix():
    release = _release_section()

    assert "### Fixed" in release
    assert "**TypeScript function re-exports**" in release
    assert "named" in release
    assert "originating" in release
    assert "E300" in release


def test_changelog_preserves_prior_release_and_compare_links():
    changelog = (_ROOT / "CHANGELOG.md").read_text()

    assert "## [2.28.1] - 2026-10-23" in changelog
    assert "**Deno dependency-flag test discovery**" in changelog
    assert "`Deno.test({ name, fn })` remains unrecognized" in changelog
    assert (
        "[Unreleased]: https://github.com/mamertofabian/maid-runner/compare/v2.28.2...HEAD"
        in changelog
    )
    assert (
        "[2.28.2]: https://github.com/mamertofabian/maid-runner/compare/v2.28.1...v2.28.2"
        in changelog
    )
    assert (
        "[2.28.1]: https://github.com/mamertofabian/maid-runner/compare/v2.28.0...v2.28.1"
        in changelog
    )


def test_roadmap_reports_prepared_patch_version():
    roadmap = (_ROOT / "docs/ROADMAP.md").read_text()

    assert "**Current Version:** 2.28.2" in roadmap
    assert "**Last Updated:** 2026-11-26" in roadmap
    assert "The local CLI reports `maid 2.28.2`." in roadmap
