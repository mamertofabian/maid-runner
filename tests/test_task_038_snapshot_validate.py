"""Behavioral tests for existing implementation: ./maid_runner/cli/validate.py

This test file documents the actual behavior of the existing code.
"""

import json
from io import StringIO
from unittest.mock import Mock, patch

import pytest

from maid_runner.cli.validate import (
    _format_file_tracking_output,
    extract_test_files_from_command,
    _extract_from_single_command,
    validate_behavioral_tests,
    _run_directory_validation,
    run_validation,
    main,
)


class TestFormatFileTrackingOutput:
    """Tests for _format_file_tracking_output function."""

    def test_empty_analysis(self, capsys):
        """Test formatting with no files to report."""
        analysis = {
            "undeclared": [],
            "registered": [],
            "tracked": [],
            "untracked_tests": [],
        }
        _format_file_tracking_output(
            analysis=analysis, quiet=False, validation_summary=None
        )

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_undeclared_files_output(self, capsys):
        """Test formatting output for undeclared files."""
        analysis = {
            "undeclared": [
                {"file": "foo.py", "issues": ["Not in any manifest"]},
                {"file": "bar.py", "issues": ["Not tracked"]},
            ],
            "registered": [],
            "tracked": [],
            "untracked_tests": [],
        }
        _format_file_tracking_output(
            analysis=analysis, quiet=False, validation_summary=None
        )

        captured = capsys.readouterr()
        assert "🔴 UNDECLARED FILES (2 files)" in captured.out
        assert "foo.py" in captured.out
        assert "bar.py" in captured.out

    def test_registered_files_output(self, capsys):
        """Test formatting output for registered files."""
        analysis = {
            "undeclared": [],
            "registered": [
                {
                    "file": "registered.py",
                    "issues": ["Missing expectedArtifacts"],
                    "manifests": ["task-001.manifest.json"],
                }
            ],
            "tracked": [],
            "untracked_tests": [],
        }
        _format_file_tracking_output(
            analysis=analysis, quiet=False, validation_summary=None
        )

        captured = capsys.readouterr()
        assert "🟡 REGISTERED FILES (1 files)" in captured.out
        assert "registered.py" in captured.out
        assert "Missing expectedArtifacts" in captured.out

    def test_quiet_mode_suppresses_details(self, capsys):
        """Test that quiet mode shows summary but not file details."""
        analysis = {
            "undeclared": [{"file": "foo.py", "issues": ["Not in any manifest"]}],
            "registered": [],
            "tracked": [],
            "untracked_tests": [],
        }
        _format_file_tracking_output(
            analysis=analysis, quiet=True, validation_summary=None
        )

        captured = capsys.readouterr()
        assert "🔴 UNDECLARED FILES (1 files)" in captured.out
        assert "foo.py" not in captured.out

    def test_validation_summary_displayed(self, capsys):
        """Test that validation summary is displayed when provided."""
        analysis = {
            "undeclared": [{"file": "foo.py", "issues": ["Not tracked"]}],
            "registered": [],
            "tracked": [{"file": "tracked.py"}],
            "untracked_tests": [],
        }
        summary = "📊 Validation: 10/10 manifest(s) passed (100.0%)"

        _format_file_tracking_output(
            analysis=analysis, quiet=False, validation_summary=summary
        )

        captured = capsys.readouterr()
        assert summary in captured.out

    def test_untracked_tests_output(self, capsys):
        """Test formatting output for untracked test files."""
        analysis = {
            "undeclared": [],
            "registered": [],
            "tracked": [],
            "untracked_tests": ["tests/test_foo.py", "tests/test_bar.py"],
        }
        _format_file_tracking_output(
            analysis=analysis, quiet=False, validation_summary=None
        )

        captured = capsys.readouterr()
        assert "🔵 UNTRACKED TEST FILES (2 files)" in captured.out
        assert "tests/test_foo.py" in captured.out

    def test_large_list_truncation(self, capsys):
        """Test that large lists are truncated in output."""
        undeclared = [
            {"file": f"file{i}.py", "issues": ["Not tracked"]} for i in range(15)
        ]
        analysis = {
            "undeclared": undeclared,
            "registered": [],
            "tracked": [],
            "untracked_tests": [],
        }
        _format_file_tracking_output(
            analysis=analysis, quiet=False, validation_summary=None
        )

        captured = capsys.readouterr()
        assert "... and 5 more" in captured.out


class TestExtractTestFilesFromCommand:
    """Tests for extract_test_files_from_command function."""

    def test_empty_command(self):
        """Test with empty validation command."""
        result = extract_test_files_from_command(validation_command=[])
        assert result == []

    def test_legacy_format_single_file(self):
        """Test legacy format with single test file."""
        command = ["pytest", "tests/test_file.py", "-v"]
        result = extract_test_files_from_command(validation_command=command)
        assert result == ["tests/test_file.py"]

    def test_legacy_format_multiple_files(self):
        """Test legacy format with multiple test files."""
        command = ["pytest", "tests/test_one.py", "tests/test_two.py", "-v"]
        result = extract_test_files_from_command(validation_command=command)
        assert "tests/test_one.py" in result
        assert "tests/test_two.py" in result

    def test_enhanced_format_array_of_arrays(self):
        """Test enhanced format (array of command arrays)."""
        command = [["pytest", "tests/test_one.py"], ["pytest", "tests/test_two.py"]]
        result = extract_test_files_from_command(validation_command=command)
        assert "tests/test_one.py" in result
        assert "tests/test_two.py" in result

    def test_string_command_with_spaces(self):
        """Test command as string with spaces."""
        command = ["pytest tests/test_file.py -v"]
        result = extract_test_files_from_command(validation_command=command)
        assert "tests/test_file.py" in result

    def test_pytest_with_node_id(self):
        """Test pytest with node ID format (file::class::method)."""
        command = ["pytest", "tests/test_file.py::TestClass::test_method", "-v"]
        result = extract_test_files_from_command(validation_command=command)
        assert "tests/test_file.py" in result

    def test_pytest_flags_filtered_out(self):
        """Test that pytest flags are filtered out from results."""
        command = ["pytest", "tests/test_file.py", "-v", "--tb=short", "--maxfail=1"]
        result = extract_test_files_from_command(validation_command=command)
        assert result == ["tests/test_file.py"]
        assert "-v" not in result
        assert "--tb" not in result


class TestExtractFromSingleCommand:
    """Tests for _extract_from_single_command helper function."""

    def test_empty_command(self):
        """Test with empty command."""
        result = _extract_from_single_command(command=[])
        assert result == []

    def test_command_without_pytest(self):
        """Test command without pytest."""
        result = _extract_from_single_command(command=["make", "test"])
        assert result == []

    def test_single_test_file(self):
        """Test extracting single test file."""
        result = _extract_from_single_command(command=["pytest", "tests/test_foo.py"])
        assert result == ["tests/test_foo.py"]

    def test_test_directory(self):
        """Test with test directory path."""
        result = _extract_from_single_command(command=["pytest", "tests/"])
        assert result == ["tests/"]


class TestValidateBehavioralTests:
    """Tests for validate_behavioral_tests function."""

    @patch("maid_runner.validators.manifest_validator.collect_behavioral_artifacts")
    @patch("maid_runner.cli.validate.Path")
    def test_no_test_files(self, mock_path, mock_collect):
        """Test with no test files provided."""
        manifest_data = {"expectedArtifacts": {"contains": []}}

        validate_behavioral_tests(
            manifest_data=manifest_data,
            test_files=[],
            use_manifest_chain=False,
            quiet=False,
        )

        mock_collect.assert_not_called()

    @patch("maid_runner.validators.manifest_validator.collect_behavioral_artifacts")
    @patch("maid_runner.cli.validate.Path")
    def test_test_file_not_found(self, mock_path, mock_collect):
        """Test raises FileNotFoundError when test file doesn't exist."""
        mock_path.return_value.exists.return_value = False
        manifest_data = {"expectedArtifacts": {"contains": []}}

        with pytest.raises(FileNotFoundError, match="Test file not found"):
            validate_behavioral_tests(
                manifest_data=manifest_data,
                test_files=["tests/missing.py"],
                use_manifest_chain=False,
                quiet=False,
            )

    @patch("maid_runner.validators.manifest_validator.collect_behavioral_artifacts")
    @patch("maid_runner.cli._test_file_extraction.Path")
    @patch("maid_runner.cli.validate.Path")
    def test_class_not_used_raises_alignment_error(
        self, mock_path, mock_path_helper, mock_collect
    ):
        """Test that missing class usage raises AlignmentError."""
        mock_path.return_value.exists.return_value = True
        mock_path_helper.return_value.exists.return_value = True
        mock_collect.return_value = {
            "used_classes": set(),
            "used_methods": {},
            "used_functions": set(),
            "used_arguments": set(),
        }

        manifest_data = {
            "expectedArtifacts": {"contains": [{"type": "class", "name": "MyClass"}]}
        }

        from maid_runner.validators.manifest_validator import AlignmentError

        with pytest.raises(
            AlignmentError, match="Class 'MyClass' not used in behavioral tests"
        ):
            validate_behavioral_tests(
                manifest_data=manifest_data,
                test_files=["tests/test_foo.py"],
                use_manifest_chain=False,
                quiet=False,
            )

    @patch("maid_runner.validators.manifest_validator.collect_behavioral_artifacts")
    @patch("maid_runner.cli._test_file_extraction.Path")
    @patch("maid_runner.cli.validate.Path")
    def test_function_not_called_raises_alignment_error(
        self, mock_path, mock_path_helper, mock_collect
    ):
        """Test that missing function usage raises AlignmentError."""
        mock_path.return_value.exists.return_value = True
        mock_path_helper.return_value.exists.return_value = True
        mock_collect.return_value = {
            "used_classes": set(),
            "used_methods": {},
            "used_functions": set(),
            "used_arguments": set(),
        }

        manifest_data = {
            "expectedArtifacts": {
                "contains": [{"type": "function", "name": "my_function"}]
            }
        }

        from maid_runner.validators.manifest_validator import AlignmentError

        with pytest.raises(
            AlignmentError,
            match="Function 'my_function' not called in behavioral tests",
        ):
            validate_behavioral_tests(
                manifest_data=manifest_data,
                test_files=["tests/test_foo.py"],
                use_manifest_chain=False,
                quiet=False,
            )

    @patch("maid_runner.validators.manifest_validator.collect_behavioral_artifacts")
    @patch("maid_runner.cli._test_file_extraction.Path")
    @patch("maid_runner.cli.validate.Path")
    def test_self_parameter_raises_alignment_error(
        self, mock_path, mock_path_helper, mock_collect
    ):
        """Test that 'self' parameter in manifest raises AlignmentError."""
        mock_path.return_value.exists.return_value = True
        mock_path_helper.return_value.exists.return_value = True

        manifest_data = {
            "expectedArtifacts": {
                "contains": [
                    {
                        "type": "function",
                        "name": "method",
                        "class": "MyClass",
                        "args": [{"name": "self"}, {"name": "arg"}],
                    }
                ]
            }
        }

        from maid_runner.validators.manifest_validator import AlignmentError

        with pytest.raises(
            AlignmentError,
            match="Parameter 'self' should not be explicitly declared",
        ):
            validate_behavioral_tests(
                manifest_data=manifest_data,
                test_files=["tests/test_foo.py"],
                use_manifest_chain=False,
                quiet=False,
            )


class TestRunDirectoryValidation:
    """Tests for _run_directory_validation function."""

    @patch("maid_runner.utils.print_maid_not_enabled_message")
    @patch("maid_runner.cli.validate.Path")
    def test_directory_not_found(self, mock_path, mock_print):
        """Test handling when manifest directory doesn't exist."""
        mock_path.return_value.resolve.return_value.exists.return_value = False

        with pytest.raises(SystemExit) as exc_info:
            _run_directory_validation(
                manifest_dir="manifests",
                validation_mode="implementation",
                use_manifest_chain=False,
                quiet=False,
            )

        assert exc_info.value.code == 0
        mock_print.assert_called_once()

    @patch("maid_runner.utils.print_no_manifests_found_message")
    @patch("maid_runner.cli.validate.Path")
    def test_no_manifests_found(self, mock_path, mock_print):
        """Test handling when no manifest files found in directory."""
        mock_manifests_dir = Mock()
        mock_manifests_dir.exists.return_value = True
        mock_manifests_dir.glob.return_value = []
        mock_path.return_value.resolve.return_value = mock_manifests_dir

        with pytest.raises(SystemExit) as exc_info:
            _run_directory_validation(
                manifest_dir="manifests",
                validation_mode="implementation",
                use_manifest_chain=False,
                quiet=False,
            )

        assert exc_info.value.code == 0
        mock_print.assert_called_once()


class TestRunValidation:
    """Tests for run_validation function."""

    def test_manifest_not_found(self):
        """Test error when manifest file doesn't exist."""
        with pytest.raises(SystemExit) as exc_info:
            run_validation(
                manifest_path="/nonexistent/manifest.json",
                validation_mode="implementation",
                use_manifest_chain=False,
                quiet=False,
                manifest_dir=None,
                skip_file_tracking=False,
            )

        assert exc_info.value.code == 1

    @patch("maid_runner.cli.validate._run_directory_validation")
    def test_manifest_dir_delegates_to_directory_validation(self, mock_run_dir):
        """Test that manifest_dir parameter delegates to directory validation."""
        run_validation(
            manifest_path=None,
            validation_mode="implementation",
            use_manifest_chain=False,
            quiet=False,
            manifest_dir="manifests",
            skip_file_tracking=False,
        )

        mock_run_dir.assert_called_once_with(
            "manifests", "implementation", False, False
        )

    @patch("maid_runner.cli.validate.validate_schema")
    @patch("builtins.open")
    @patch("maid_runner.cli.validate.Path")
    def test_invalid_json_handled(self, mock_path, mock_open, mock_validate):
        """Test handling of invalid JSON in manifest file.

        Note: Due to exception handler ordering in run_validation, JSONDecodeError
        is caught by the generic Exception handler, which re-raises it. The specific
        json.JSONDecodeError handler is unreachable, so the exception propagates up.
        """
        mock_path.return_value.exists.return_value = True

        # Create a real file-like object that contains invalid JSON

        mock_file = StringIO("{invalid json")
        mock_open.return_value.__enter__.return_value = mock_file

        # The actual behavior is that JSONDecodeError is re-raised and propagates
        with pytest.raises(json.JSONDecodeError):
            run_validation(
                manifest_path="manifest.json",
                validation_mode="implementation",
                use_manifest_chain=False,
                quiet=False,
                manifest_dir=None,
                skip_file_tracking=False,
            )


class TestMain:
    """Tests for main CLI entry point."""

    def test_no_arguments_shows_error(self):
        """Test that no arguments shows error."""
        with patch("sys.argv", ["validate.py"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 2

    @patch("maid_runner.cli.validate.run_validation")
    def test_manifest_path_argument(self, mock_run):
        """Test main with manifest path argument."""
        mock_run.side_effect = SystemExit(0)

        with patch("sys.argv", ["validate.py", "manifests/task-001.manifest.json"]):
            with pytest.raises(SystemExit):
                main()

            mock_run.assert_called_once()
            args = mock_run.call_args
            assert args[0][0] == "manifests/task-001.manifest.json"
            assert args[0][1] == "implementation"

    @patch("maid_runner.cli.validate.run_validation")
    def test_validation_mode_behavioral(self, mock_run):
        """Test main with behavioral validation mode."""
        mock_run.side_effect = SystemExit(0)

        with patch(
            "sys.argv",
            [
                "validate.py",
                "manifests/task-001.manifest.json",
                "--validation-mode",
                "behavioral",
            ],
        ):
            with pytest.raises(SystemExit):
                main()

            args = mock_run.call_args
            assert args[0][1] == "behavioral"

    @patch("maid_runner.cli.validate.run_validation")
    def test_use_manifest_chain_flag(self, mock_run):
        """Test main with use-manifest-chain flag."""
        mock_run.side_effect = SystemExit(0)

        with patch(
            "sys.argv",
            [
                "validate.py",
                "manifests/task-001.manifest.json",
                "--use-manifest-chain",
            ],
        ):
            with pytest.raises(SystemExit):
                main()

            args = mock_run.call_args
            assert args[0][2] is True

    @patch("maid_runner.cli.validate.run_validation")
    def test_quiet_flag(self, mock_run):
        """Test main with quiet flag."""
        mock_run.side_effect = SystemExit(0)

        with patch(
            "sys.argv",
            ["validate.py", "manifests/task-001.manifest.json", "--quiet"],
        ):
            with pytest.raises(SystemExit):
                main()

            args = mock_run.call_args
            assert args[0][3] is True

    @patch("maid_runner.cli.validate.run_validation")
    def test_manifest_dir_flag(self, mock_run):
        """Test main with manifest-dir flag."""
        mock_run.side_effect = SystemExit(0)

        with patch("sys.argv", ["validate.py", "--manifest-dir", "manifests"]):
            with pytest.raises(SystemExit):
                main()

            args = mock_run.call_args
            assert args[0][4] == "manifests"

    def test_mutual_exclusivity_error(self):
        """Test that providing both manifest_path and manifest_dir raises error."""
        with patch(
            "sys.argv",
            [
                "validate.py",
                "manifests/task-001.manifest.json",
                "--manifest-dir",
                "manifests",
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 2
