"""Behavioral tests for task-095: CLI Registration for `maid manifest create` command.

These tests verify that the `manifest create` subcommand is properly registered
in the CLI with all required arguments and flags, and dispatches to the correct handler.

Tests focus on CLI registration behavior (argparse setup), NOT the underlying
implementation logic (which is covered by later tasks).
"""

import subprocess
import sys

import pytest


class TestManifestCreateSubcommandExists:
    """Verify the manifest create subcommand is registered."""

    def test_manifest_create_help_works(self):
        """Running `maid manifest create --help` should succeed."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "--help",
            ],
            capture_output=True,
            text=True,
        )

        # Should exit with code 0 (help displayed successfully)
        assert result.returncode == 0
        # Help text should mention 'create' and key arguments
        assert "create" in result.stdout.lower() or "manifest" in result.stdout.lower()

    def test_manifest_subcommand_exists(self):
        """Running `maid manifest --help` should show create as a subcommand."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "--help",
            ],
            capture_output=True,
            text=True,
        )

        # Should exit with code 0
        assert result.returncode == 0
        # Should mention 'create' as a subcommand
        assert "create" in result.stdout


class TestRequiredArguments:
    """Verify required arguments are enforced."""

    def test_file_path_is_required(self):
        """Command fails without file_path argument."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "--goal",
                "Test goal",
            ],
            capture_output=True,
            text=True,
        )

        # Should fail due to missing required positional argument
        assert result.returncode != 0
        assert (
            "file_path" in result.stderr.lower() or "required" in result.stderr.lower()
        )

    def test_goal_flag_is_required(self):
        """Command fails without --goal flag."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "src/test.py",
            ],
            capture_output=True,
            text=True,
        )

        # Should fail due to missing required --goal argument
        assert result.returncode != 0
        assert "--goal" in result.stderr or "required" in result.stderr.lower()


class TestArtifactsFlag:
    """Verify --artifacts flag accepts JSON string."""

    def test_artifacts_flag_recognized(self):
        """The --artifacts flag is recognized by the parser."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "--help",
            ],
            capture_output=True,
            text=True,
        )

        assert "--artifacts" in result.stdout

    def test_artifacts_accepts_json_string(self):
        """The --artifacts flag accepts a JSON string value."""
        # This tests argument parsing, not execution
        # The handler import will fail (expected in TDD red phase)
        # but argparse should accept the argument format
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "src/test.py",
                "--goal",
                "Test goal",
                "--artifacts",
                '[{"type": "function", "name": "test_func"}]',
                "--dry-run",  # Avoid actual file writing
            ],
            capture_output=True,
            text=True,
        )

        # Should NOT fail with "unrecognized arguments"
        assert "unrecognized arguments: --artifacts" not in result.stderr


class TestTaskTypeFlag:
    """Verify --task-type flag with choices."""

    def test_task_type_flag_recognized(self):
        """The --task-type flag is recognized by the parser."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "--help",
            ],
            capture_output=True,
            text=True,
        )

        assert "--task-type" in result.stdout

    @pytest.mark.parametrize("task_type", ["create", "edit", "refactor"])
    def test_task_type_accepts_valid_choices(self, task_type):
        """The --task-type flag accepts valid choices: create, edit, refactor."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "src/test.py",
                "--goal",
                "Test goal",
                "--task-type",
                task_type,
                "--dry-run",
            ],
            capture_output=True,
            text=True,
        )

        # Should NOT fail with invalid choice error
        assert f"invalid choice: '{task_type}'" not in result.stderr

    def test_task_type_rejects_invalid_choice(self):
        """The --task-type flag rejects invalid choices."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "src/test.py",
                "--goal",
                "Test goal",
                "--task-type",
                "invalid_type",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
        )

        # Should fail with invalid choice error
        assert result.returncode != 0
        assert "invalid choice" in result.stderr.lower()


class TestForceSupersededFlag:
    """Verify --force-supersede flag accepts string."""

    def test_force_supersede_flag_recognized(self):
        """The --force-supersede flag is recognized by the parser."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "--help",
            ],
            capture_output=True,
            text=True,
        )

        assert "--force-supersede" in result.stdout

    def test_force_supersede_accepts_string(self):
        """The --force-supersede flag accepts a manifest filename."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "src/test.py",
                "--goal",
                "Test goal",
                "--force-supersede",
                "task-050-previous.manifest.json",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
        )

        assert "unrecognized arguments: --force-supersede" not in result.stderr


class TestTestFileFlag:
    """Verify --test-file flag accepts string."""

    def test_test_file_flag_recognized(self):
        """The --test-file flag is recognized by the parser."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "--help",
            ],
            capture_output=True,
            text=True,
        )

        assert "--test-file" in result.stdout

    def test_test_file_accepts_string(self):
        """The --test-file flag accepts a test file path."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "src/test.py",
                "--goal",
                "Test goal",
                "--test-file",
                "tests/test_my_module.py",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
        )

        assert "unrecognized arguments: --test-file" not in result.stderr


class TestReadonlyFilesFlag:
    """Verify --readonly-files flag accepts string."""

    def test_readonly_files_flag_recognized(self):
        """The --readonly-files flag is recognized by the parser."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "--help",
            ],
            capture_output=True,
            text=True,
        )

        assert "--readonly-files" in result.stdout

    def test_readonly_files_accepts_string(self):
        """The --readonly-files flag accepts a comma-separated list."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "src/test.py",
                "--goal",
                "Test goal",
                "--readonly-files",
                "src/utils.py,src/types.py",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
        )

        assert "unrecognized arguments: --readonly-files" not in result.stderr


class TestOutputDirFlag:
    """Verify --output-dir flag with default value."""

    def test_output_dir_flag_recognized(self):
        """The --output-dir flag is recognized by the parser."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "--help",
            ],
            capture_output=True,
            text=True,
        )

        assert "--output-dir" in result.stdout

    def test_output_dir_help_shows_default(self):
        """The --output-dir help text mentions the default value."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "--help",
            ],
            capture_output=True,
            text=True,
        )

        # Help should mention manifests as default
        assert "manifests" in result.stdout

    def test_output_dir_accepts_custom_path(self):
        """The --output-dir flag accepts a custom directory path."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "src/test.py",
                "--goal",
                "Test goal",
                "--output-dir",
                "custom/manifest/dir",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
        )

        assert "unrecognized arguments: --output-dir" not in result.stderr


class TestTaskNumberFlag:
    """Verify --task-number flag accepts integer."""

    def test_task_number_flag_recognized(self):
        """The --task-number flag is recognized by the parser."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "--help",
            ],
            capture_output=True,
            text=True,
        )

        assert "--task-number" in result.stdout

    def test_task_number_accepts_integer(self):
        """The --task-number flag accepts an integer value."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "src/test.py",
                "--goal",
                "Test goal",
                "--task-number",
                "100",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
        )

        assert "unrecognized arguments: --task-number" not in result.stderr

    def test_task_number_rejects_non_integer(self):
        """The --task-number flag rejects non-integer values."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "src/test.py",
                "--goal",
                "Test goal",
                "--task-number",
                "not_a_number",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
        )

        # Should fail due to invalid integer
        assert result.returncode != 0
        assert (
            "invalid int value" in result.stderr.lower()
            or "invalid" in result.stderr.lower()
        )


class TestJsonFlag:
    """Verify --json flag is a boolean flag."""

    def test_json_flag_recognized(self):
        """The --json flag is recognized by the parser."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "--help",
            ],
            capture_output=True,
            text=True,
        )

        assert "--json" in result.stdout

    def test_json_flag_is_boolean(self):
        """The --json flag works as a boolean (no value required)."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "src/test.py",
                "--goal",
                "Test goal",
                "--json",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
        )

        assert "unrecognized arguments: --json" not in result.stderr


class TestQuietFlag:
    """Verify --quiet flag is a boolean flag."""

    def test_quiet_flag_recognized(self):
        """The --quiet flag is recognized by the parser."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "--help",
            ],
            capture_output=True,
            text=True,
        )

        assert "--quiet" in result.stdout or "-q" in result.stdout

    def test_quiet_flag_is_boolean(self):
        """The --quiet flag works as a boolean (no value required)."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "src/test.py",
                "--goal",
                "Test goal",
                "--quiet",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
        )

        assert "unrecognized arguments: --quiet" not in result.stderr


class TestDryRunFlag:
    """Verify --dry-run flag is a boolean flag."""

    def test_dry_run_flag_recognized(self):
        """The --dry-run flag is recognized by the parser."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "--help",
            ],
            capture_output=True,
            text=True,
        )

        assert "--dry-run" in result.stdout

    def test_dry_run_flag_is_boolean(self):
        """The --dry-run flag works as a boolean (no value required)."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "src/test.py",
                "--goal",
                "Test goal",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
        )

        assert "unrecognized arguments: --dry-run" not in result.stderr


class TestHandlerDispatch:
    """Verify dispatch to correct handler module."""

    def test_dispatches_to_manifest_create_module(self):
        """When invoked, tries to import from maid_runner.cli.manifest_create."""
        # This test verifies the dispatch mechanism is set up correctly.
        # In the TDD red phase, the import will fail because the module doesn't exist.
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "src/test.py",
                "--goal",
                "Test goal",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
        )

        # At minimum, we expect it to try importing the handler
        # In TDD red phase, this could be:
        # - ModuleNotFoundError for manifest_create
        # - ImportError if handler function doesn't exist
        # - Or success if implemented
        # The key assertion is that argparse accepted all arguments
        # (if we get here without argparse errors, registration is correct)

        # Check that argparse didn't reject any arguments
        assert "unrecognized arguments" not in result.stderr
        assert "error: invalid choice" not in result.stderr

        # The expected error in TDD red phase is related to the handler module
        # Either it doesn't exist (ModuleNotFoundError) or it's not implemented
        # This is acceptable - it means CLI registration is complete
        if result.returncode != 0:
            # Should be a handler-related error, not argparse error
            assert (
                "manifest_create" in result.stderr
                or "run_create_manifest" in result.stderr
                or "ModuleNotFoundError" in result.stderr
                or "ImportError" in result.stderr
                or "No module named" in result.stderr
                or "cannot import" in result.stderr.lower()
            )


class TestHelpTextQuality:
    """Verify help text provides useful information."""

    def test_help_text_describes_file_path(self):
        """Help text describes the file_path positional argument."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "--help",
            ],
            capture_output=True,
            text=True,
        )

        # Should describe what file_path is for
        assert "file" in result.stdout.lower()

    def test_help_text_describes_goal(self):
        """Help text describes the --goal flag."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "--help",
            ],
            capture_output=True,
            text=True,
        )

        # Should mention goal
        assert "goal" in result.stdout.lower()

    def test_help_text_shows_all_flags(self):
        """Help text includes all registered flags."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "--help",
            ],
            capture_output=True,
            text=True,
        )

        expected_flags = [
            "--goal",
            "--artifacts",
            "--task-type",
            "--force-supersede",
            "--test-file",
            "--readonly-files",
            "--output-dir",
            "--task-number",
            "--json",
            "--quiet",
            "--dry-run",
        ]

        for flag in expected_flags:
            assert flag in result.stdout, f"Expected {flag} in help text"


class TestAllFlagsWithValidValues:
    """Integration test: verify all flags work together."""

    def test_all_flags_accepted_together(self):
        """All flags can be used together without argparse errors."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "src/auth/service.py",
                "--goal",
                "Add AuthService class",
                "--artifacts",
                '[{"type": "class", "name": "AuthService"}]',
                "--task-type",
                "create",
                "--force-supersede",
                "task-050-old.manifest.json",
                "--test-file",
                "tests/test_auth_service.py",
                "--readonly-files",
                "src/utils.py,src/types.py",
                "--output-dir",
                "manifests",
                "--task-number",
                "95",
                "--json",
                "--quiet",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
        )

        # Should NOT have any argparse errors
        assert "unrecognized arguments" not in result.stderr
        assert "error: invalid choice" not in result.stderr
        assert "error: argument" not in result.stderr or "--goal" not in result.stderr
