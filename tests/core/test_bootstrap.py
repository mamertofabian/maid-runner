"""Tests for maid_runner.core.bootstrap — brownfield project onboarding."""

from __future__ import annotations

import textwrap

import yaml

from maid_runner.core._file_discovery import discover_source_files
from maid_runner.core.bootstrap import (
    BootstrapFileResult,
    BootstrapReport,
    bootstrap_project,
)


class TestBootstrapProject:
    def test_captures_simple_project(self, tmp_path):
        """Bootstrap discovers and snapshots multiple Python files."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "greet.py").write_text(
            textwrap.dedent(
                """\
                def hello(name: str) -> str:
                    return f"Hello, {name}"
            """
            )
        )
        (tmp_path / "src" / "math_utils.py").write_text(
            textwrap.dedent(
                """\
                def add(a: int, b: int) -> int:
                    return a + b
            """
            )
        )
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        report = bootstrap_project(str(tmp_path), manifest_dir=str(manifest_dir))

        assert isinstance(report, BootstrapReport)
        assert report.captured == 2
        assert report.total_artifacts >= 2  # at least hello + add
        assert report.failed == 0
        # Manifests should be written
        manifests = list(manifest_dir.glob("*.manifest.yaml"))
        assert len(manifests) == 2

    def test_dry_run_writes_nothing(self, tmp_path):
        """Dry run produces report but creates no manifest files."""
        (tmp_path / "app.py").write_text("def run(): pass\n")
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        report = bootstrap_project(
            str(tmp_path), manifest_dir=str(manifest_dir), dry_run=True
        )

        assert report.captured == 1
        assert report.total_artifacts >= 1
        manifests = list(manifest_dir.glob("*.manifest.yaml"))
        assert len(manifests) == 0

    def test_records_parse_failures(self, tmp_path):
        """Files that cause errors are recorded as failed, not silently skipped."""
        (tmp_path / "broken.py").write_bytes(b"\x80\x81\x82\x83")
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        report = bootstrap_project(str(tmp_path), manifest_dir=str(manifest_dir))

        assert report.failed == 1
        failed = [r for r in report.results if r.status == "failed"]
        assert len(failed) == 1
        assert failed[0].error is not None

    def test_skips_already_tracked(self, tmp_path):
        """Files already tracked by existing manifests are skipped."""
        (tmp_path / "greet.py").write_text("def hello(): pass\n")
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        # Create an existing snapshot manifest for greet.py
        existing = {
            "schema": "2",
            "goal": "Snapshot of greet.py",
            "type": "snapshot",
            "files": {
                "snapshot": [
                    {
                        "path": "greet.py",
                        "artifacts": [{"kind": "function", "name": "hello"}],
                    }
                ]
            },
            "validate": ["pytest tests/ -v"],
            "created": "2026-01-01T00:00:00+00:00",
        }
        (manifest_dir / "snapshot-greet.manifest.yaml").write_text(yaml.dump(existing))

        report = bootstrap_project(str(tmp_path), manifest_dir=str(manifest_dir))

        assert report.skipped == 1
        assert report.captured == 0
        skipped = [r for r in report.results if r.status == "skipped"]
        assert len(skipped) == 1

    def test_excludes_patterns(self, tmp_path):
        """Exclude patterns filter out matching files."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("def main(): pass\n")
        (tmp_path / "vendor").mkdir()
        (tmp_path / "vendor" / "lib.py").write_text("def vendored(): pass\n")
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        report = bootstrap_project(
            str(tmp_path),
            manifest_dir=str(manifest_dir),
            exclude_patterns={"vendor/*"},
        )

        assert report.captured == 1
        assert report.excluded == 1
        captured = [r for r in report.results if r.status == "captured"]
        assert captured[0].path == "src/app.py"

    def test_empty_project(self, tmp_path):
        """Project with no source files yields empty report."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        report = bootstrap_project(str(tmp_path), manifest_dir=str(manifest_dir))

        assert report.total_discovered == 0
        assert report.captured == 0
        assert report.failed == 0
        assert len(report.results) == 0

    def test_report_counts_accurate(self, tmp_path):
        """captured + skipped + failed + excluded == total_discovered."""
        (tmp_path / "good.py").write_text("def ok(): pass\n")
        (tmp_path / "broken.py").write_bytes(b"\x80\x81\x82\x83")
        (tmp_path / "vendor").mkdir()
        (tmp_path / "vendor" / "ext.py").write_text("def ext(): pass\n")
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        report = bootstrap_project(
            str(tmp_path),
            manifest_dir=str(manifest_dir),
            exclude_patterns={"vendor/*"},
        )

        assert (
            report.captured + report.skipped + report.failed + report.excluded
            == report.total_discovered
        )

    def test_excludes_test_files(self, tmp_path):
        """Test files are not snapshotted by default."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("def main(): pass\n")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_app.py").write_text("def test_main(): pass\n")
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        report = bootstrap_project(str(tmp_path), manifest_dir=str(manifest_dir))

        captured_paths = {r.path for r in report.results if r.status == "captured"}
        assert "src/app.py" in captured_paths
        assert "tests/test_app.py" not in captured_paths

    def test_manifest_content_valid(self, tmp_path):
        """Generated snapshot manifests contain valid YAML with correct structure."""
        (tmp_path / "calc.py").write_text(
            textwrap.dedent(
                """\
                def add(a: int, b: int) -> int:
                    return a + b

                class Calculator:
                    def multiply(self, x: int, y: int) -> int:
                        return x * y
            """
            )
        )
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        bootstrap_project(str(tmp_path), manifest_dir=str(manifest_dir))

        manifests = list(manifest_dir.glob("*.manifest.yaml"))
        assert len(manifests) == 1
        data = yaml.safe_load(manifests[0].read_text())
        assert data["schema"] == "2"
        assert data["type"] == "snapshot"
        assert "files" in data
        assert "snapshot" in data["files"]


class TestDiscoverSourceFilesWithExclusions:
    def test_exclude_patterns_filter_files(self, tmp_path):
        """discover_source_files respects exclude_patterns parameter."""
        (tmp_path / "app.py").write_text("x = 1\n")
        (tmp_path / "vendor").mkdir()
        (tmp_path / "vendor" / "lib.py").write_text("y = 2\n")

        files = discover_source_files(tmp_path, exclude_patterns={"vendor/*"})

        assert "app.py" in files
        assert "vendor/lib.py" not in files

    def test_no_exclude_returns_all(self, tmp_path):
        """Without exclude_patterns, all source files are returned."""
        (tmp_path / "a.py").write_text("x = 1\n")
        (tmp_path / "b.py").write_text("y = 2\n")

        files = discover_source_files(tmp_path)
        assert len(files) == 2


class TestBootstrapFileResult:
    def test_frozen_dataclass(self):
        result = BootstrapFileResult(
            path="src/app.py",
            status="captured",
            artifact_count=3,
            manifest_slug="snapshot-app",
        )
        assert result.path == "src/app.py"
        assert result.status == "captured"
        assert result.artifact_count == 3
        assert result.error is None


class TestBootstrapReport:
    def test_frozen_dataclass(self):
        report = BootstrapReport(
            results=(),
            total_discovered=0,
            captured=0,
            skipped=0,
            failed=0,
            excluded=0,
            total_artifacts=0,
        )
        assert report.total_discovered == 0
        assert report.duration_ms is None
        assert report.manifests_dir is None
