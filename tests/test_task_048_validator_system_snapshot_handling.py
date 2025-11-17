"""
Behavioral tests for task-048: Add special validation handling for system-snapshot taskType.

Tests verify that:
1. _should_skip_behavioral_validation() correctly identifies system snapshots
2. _should_skip_implementation_validation() correctly identifies system snapshots
3. System snapshots are handled correctly by the skip functions
4. Regular manifests continue to work as before
"""

from maid_runner.validators.manifest_validator import (
    _is_system_manifest,
    _should_skip_behavioral_validation,
    _should_skip_implementation_validation,
)


class TestShouldSkipBehavioralValidation:
    """Test suite for _should_skip_behavioral_validation() function."""

    def test_function_exists(self):
        """Verify _should_skip_behavioral_validation function exists."""
        assert callable(_should_skip_behavioral_validation)

    def test_skips_for_system_snapshot_manifest(self):
        """Verify behavioral validation is skipped for system-snapshot manifests."""
        system_manifest = {
            "version": "1",
            "goal": "System snapshot",
            "taskType": "system-snapshot",
            "readonlyFiles": [],
            "systemArtifacts": [],
            "validationCommands": [],
        }

        result = _should_skip_behavioral_validation(system_manifest)
        assert result is True

    def test_does_not_skip_for_regular_manifests(self):
        """Verify behavioral validation is NOT skipped for regular manifests."""
        regular_manifests = [
            {
                "version": "1",
                "goal": "Regular edit",
                "taskType": "edit",
                "readonlyFiles": [],
                "expectedArtifacts": {"file": "test.py", "contains": []},
                "validationCommand": ["pytest", "tests/"],
            },
            {
                "version": "1",
                "goal": "Regular create",
                "taskType": "create",
                "readonlyFiles": [],
                "expectedArtifacts": {"file": "test.py", "contains": []},
                "validationCommand": ["pytest", "tests/"],
            },
            {
                "version": "1",
                "goal": "Regular snapshot",
                "taskType": "snapshot",
                "readonlyFiles": [],
                "expectedArtifacts": {"file": "test.py", "contains": []},
                "validationCommand": ["pytest", "tests/"],
            },
        ]

        for manifest in regular_manifests:
            result = _should_skip_behavioral_validation(manifest)
            assert (
                result is False
            ), f"Should not skip for taskType: {manifest['taskType']}"

    def test_uses_is_system_manifest_logic(self):
        """Verify function uses _is_system_manifest() to determine skip."""
        # Manifest with systemArtifacts but no system-snapshot taskType
        manifest = {
            "version": "1",
            "goal": "Test",
            "taskType": "edit",  # Not system-snapshot
            "readonlyFiles": [],
            "systemArtifacts": [],
            "validationCommands": [],
        }

        # Should still skip if it's identified as a system manifest
        if _is_system_manifest(manifest):
            assert _should_skip_behavioral_validation(manifest) is True
        else:
            assert _should_skip_behavioral_validation(manifest) is False


class TestShouldSkipImplementationValidation:
    """Test suite for _should_skip_implementation_validation() function."""

    def test_function_exists(self):
        """Verify _should_skip_implementation_validation function exists."""
        assert callable(_should_skip_implementation_validation)

    def test_skips_for_system_snapshot_manifest(self):
        """Verify implementation validation is skipped for system-snapshot manifests."""
        system_manifest = {
            "version": "1",
            "goal": "System snapshot",
            "taskType": "system-snapshot",
            "readonlyFiles": [],
            "systemArtifacts": [],
            "validationCommands": [],
        }

        result = _should_skip_implementation_validation(system_manifest)
        assert result is True

    def test_does_not_skip_for_regular_manifests(self):
        """Verify implementation validation is NOT skipped for regular manifests."""
        regular_manifests = [
            {
                "version": "1",
                "goal": "Regular edit",
                "taskType": "edit",
                "readonlyFiles": [],
                "expectedArtifacts": {"file": "test.py", "contains": []},
                "validationCommand": ["pytest", "tests/"],
            },
            {
                "version": "1",
                "goal": "Regular create",
                "taskType": "create",
                "readonlyFiles": [],
                "expectedArtifacts": {"file": "test.py", "contains": []},
                "validationCommand": ["pytest", "tests/"],
            },
            {
                "version": "1",
                "goal": "Regular snapshot",
                "taskType": "snapshot",
                "readonlyFiles": [],
                "expectedArtifacts": {"file": "test.py", "contains": []},
                "validationCommand": ["pytest", "tests/"],
            },
        ]

        for manifest in regular_manifests:
            result = _should_skip_implementation_validation(manifest)
            assert (
                result is False
            ), f"Should not skip for taskType: {manifest['taskType']}"

    def test_uses_is_system_manifest_logic(self):
        """Verify function uses _is_system_manifest() to determine skip."""
        # Manifest with systemArtifacts
        manifest = {
            "version": "1",
            "goal": "Test",
            "taskType": "system-snapshot",
            "readonlyFiles": [],
            "systemArtifacts": [],
            "validationCommands": [],
        }

        # Should skip if it's a system manifest
        if _is_system_manifest(manifest):
            assert _should_skip_implementation_validation(manifest) is True


class TestCLIIntegration:
    """Integration tests for CLI handling of system manifests."""

    def test_cli_validates_system_manifest_successfully(self, tmp_path, capsys):
        """Verify CLI validates system manifests without implementation checks."""
        import json
        from maid_runner.cli.validate import run_validation

        # Create a system manifest without implementation files
        manifest_path = tmp_path / "system.manifest.json"
        system_manifest = {
            "version": "1",
            "goal": "System snapshot",
            "taskType": "system-snapshot",
            "readonlyFiles": [],
            "systemArtifacts": [
                {
                    "file": "nonexistent/file.py",
                    "contains": [{"type": "function", "name": "test"}],
                }
            ],
            "validationCommands": [["pytest", "tests/"]],
        }

        with open(manifest_path, "w") as f:
            json.dump(system_manifest, f)

        # Should validate successfully even though files don't exist
        run_validation(
            str(manifest_path),
            validation_mode="implementation",
            use_manifest_chain=False,
            quiet=False,
        )

        # Check output message
        captured = capsys.readouterr()
        assert "System manifest validation PASSED" in captured.out
        assert "schema validation only" in captured.out

    def test_cli_validates_regular_manifest_normally(self, tmp_path):
        """Verify CLI still validates regular manifests normally."""
        import json
        from maid_runner.cli.validate import run_validation

        # Create a regular manifest with missing implementation
        manifest_path = tmp_path / "regular.manifest.json"
        regular_manifest = {
            "version": "1",
            "goal": "Regular manifest",
            "taskType": "edit",
            "readonlyFiles": [],
            "editableFiles": ["nonexistent.py"],
            "expectedArtifacts": {
                "file": "nonexistent.py",
                "contains": [{"type": "function", "name": "test"}],
            },
            "validationCommand": ["pytest", "tests/"],
        }

        with open(manifest_path, "w") as f:
            json.dump(regular_manifest, f)

        # Should fail because implementation file doesn't exist
        import sys
        from io import StringIO

        old_stderr = sys.stderr
        sys.stderr = StringIO()

        try:
            run_validation(
                str(manifest_path),
                validation_mode="implementation",
                use_manifest_chain=False,
                quiet=False,
            )
            # Should have exited, but if not, fail the test
            assert False, "Expected validation to fail for missing implementation"
        except SystemExit as e:
            # Expected to exit with error code
            assert e.code != 0
        finally:
            sys.stderr = old_stderr
