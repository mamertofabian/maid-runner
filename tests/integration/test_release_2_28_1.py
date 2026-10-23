"""Release metadata and notes for the 2.28.1 patch release."""

from pathlib import Path
import subprocess

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from maid_runner import __version__


_ROOT = Path(__file__).resolve().parents[2]
_HEADING = "## [2.28.1] - 2026-10-23"


def _release_section() -> str:
    changelog = (_ROOT / "CHANGELOG.md").read_text()
    _, release = changelog.split(_HEADING, 1)
    return release.split("\n## [", 1)[0]


def test_package_lock_and_cli_report_2_28_1():
    project = tomllib.loads((_ROOT / "pyproject.toml").read_text())
    lock = tomllib.loads((_ROOT / "uv.lock").read_text())
    package = next(p for p in lock["package"] if p["name"] == "maid-runner")

    assert project["project"]["version"] == "2.28.1"
    assert package["version"] == "2.28.1"
    assert __version__ == "2.28.1"
    result = subprocess.run(
        ["maid", "--version"], check=True, capture_output=True, text=True
    )
    assert result.stdout.strip() == "maid 2.28.1"


def test_changelog_dates_2_28_1_below_an_empty_unreleased_section():
    changelog = (_ROOT / "CHANGELOG.md").read_text()

    unreleased, _ = changelog.split(_HEADING, 1)

    assert "## [Unreleased]" in unreleased
    assert "### " not in unreleased.split("## [Unreleased]", 1)[1]
    assert "## [2.28.0] - 2026-10-02" in changelog


def test_release_notes_name_every_post_2_28_0_fix():
    release = _release_section()

    for entry in (
        "Deno dependency-flag test discovery",
        "Deno.test declarations",
        "Optional xdist hooks",
        "Literal descriptions in promotion",
        "Dependency-prerequisite revision guidance",
        "Path-loaded Python hook identity",
        "Project launcher in agent guidance",
        "Subproject Node environments in snapshots",
        "Snapshot Git identity",
        "Selected superseding drafts",
        "TypeScript identifier defaults",
        "Python variadic parameters",
        "Nested union and Literal signatures",
        "Imported annotation types",
        "PEP 695 type aliases",
        "Protocol interface signatures",
        "Unavailable coverage instrumentation",
        "Read-only sibling dependencies during stash revision",
        "Stash-restoration red attribution",
        "Unittest and scoped plan-lock inputs",
        "Scope-check outside the project root",
    ):
        assert f"**{entry}**" in release


def test_release_notes_list_fixes_without_new_features():
    release = _release_section()

    assert "### Fixed" in release
    assert "### Added" not in release


def test_release_notes_keep_exact_deno_flag_and_declaration_details():
    release = _release_section()

    for detail in (
        "`--no-lock`",
        "`--cached-only`",
        "`--no-remote`",
        "`--no-npm`",
        "`--node-modules-dir`",
        "`--frozen`",
        "`Deno.test`",
    ):
        assert detail in release
    assert "`Deno.test({ name, fn })` remains unrecognized" in release


def test_changelog_links_compare_2_28_1_against_2_28_0():
    changelog = (_ROOT / "CHANGELOG.md").read_text()

    assert (
        "[Unreleased]: https://github.com/mamertofabian/maid-runner/compare/v2.28.1...HEAD"
        in changelog
    )
    assert (
        "[2.28.1]: https://github.com/mamertofabian/maid-runner/compare/v2.28.0...v2.28.1"
        in changelog
    )
    assert (
        "[2.28.0]: https://github.com/mamertofabian/maid-runner/compare/v2.27.6...v2.28.0"
        in changelog
    )


def test_roadmap_reports_prepared_release_version_and_date():
    roadmap = (_ROOT / "docs/ROADMAP.md").read_text()

    assert "**Current Version:** 2.28.1" in roadmap
    assert "**Last Updated:** 2026-10-23" in roadmap
    assert "The local CLI reports `maid 2.28.1`." in roadmap
