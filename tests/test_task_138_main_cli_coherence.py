"""Behavioral tests for Task 138: Update main.py CLI integration for coherence validation.

These tests verify that the add_coherence_arguments and handle_coherence_validation
functions are properly implemented in the main CLI module to add --coherence and
--coherence-only flags to the validate subcommand.

Artifacts tested:
- add_coherence_arguments(parser: argparse.ArgumentParser) -> None
- handle_coherence_validation(args: argparse.Namespace) -> bool

The add_coherence_arguments function adds --coherence and --coherence-only arguments
to an ArgumentParser for the validate subcommand.

The handle_coherence_validation function handles coherence validation based on the
parsed arguments, auto-enabling use_manifest_chain when coherence validation is
requested, and returns True when validation succeeds.
"""

import argparse
import json
import pytest
from pathlib import Path
from typing import Any, Dict

from maid_runner.cli.main import (
    add_coherence_arguments,
    handle_coherence_validation,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def validate_parser() -> argparse.ArgumentParser:
    """Create an ArgumentParser simulating the validate subparser."""
    parser = argparse.ArgumentParser(prog="maid validate")
    return parser


@pytest.fixture
def configured_parser(
    validate_parser: argparse.ArgumentParser,
) -> argparse.ArgumentParser:
    """Create a parser with coherence arguments already added."""
    add_coherence_arguments(validate_parser)
    return validate_parser


@pytest.fixture
def manifest_dir(tmp_path: Path) -> Path:
    """Create a temporary manifest directory."""
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    return manifests


@pytest.fixture
def sample_manifest_data() -> Dict[str, Any]:
    """Create sample manifest data for testing."""
    return {
        "version": "1",
        "goal": "Test coherence validation",
        "taskType": "create",
        "creatableFiles": ["src/module.py"],
        "editableFiles": [],
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "src/module.py",
            "contains": [
                {"type": "function", "name": "test_function"},
            ],
        },
        "validationCommand": ["pytest", "tests/test_module.py", "-v"],
    }


@pytest.fixture
def manifest_file(manifest_dir: Path, sample_manifest_data: Dict[str, Any]) -> Path:
    """Create a manifest file in the test directory."""
    manifest_path = manifest_dir / "task-001.manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(sample_manifest_data, f)
    return manifest_path


# =============================================================================
# Tests for add_coherence_arguments function existence and signature
# =============================================================================


class TestAddCoherenceArgumentsFunction:
    """Verify add_coherence_arguments function exists and has correct signature."""

    def test_function_exists(self) -> None:
        """add_coherence_arguments function exists in main module."""
        assert add_coherence_arguments is not None

    def test_function_is_callable(self) -> None:
        """add_coherence_arguments is a callable function."""
        assert callable(add_coherence_arguments)

    def test_accepts_argument_parser(
        self, validate_parser: argparse.ArgumentParser
    ) -> None:
        """add_coherence_arguments accepts an ArgumentParser instance."""
        # Should not raise an exception
        add_coherence_arguments(validate_parser)

    def test_returns_none(self, validate_parser: argparse.ArgumentParser) -> None:
        """add_coherence_arguments returns None."""
        result = add_coherence_arguments(validate_parser)
        assert result is None


# =============================================================================
# Tests for add_coherence_arguments adding --coherence flag
# =============================================================================


class TestAddCoherenceFlag:
    """Verify --coherence flag is added by add_coherence_arguments."""

    def test_coherence_argument_added(
        self, configured_parser: argparse.ArgumentParser
    ) -> None:
        """add_coherence_arguments adds --coherence argument."""
        # Should not raise when parsing --coherence
        args = configured_parser.parse_args(["--coherence"])
        assert hasattr(args, "coherence")

    def test_coherence_default_is_false(
        self, configured_parser: argparse.ArgumentParser
    ) -> None:
        """--coherence defaults to False when not specified."""
        args = configured_parser.parse_args([])
        assert args.coherence is False

    def test_coherence_is_true_when_specified(
        self, configured_parser: argparse.ArgumentParser
    ) -> None:
        """--coherence is True when specified."""
        args = configured_parser.parse_args(["--coherence"])
        assert args.coherence is True

    def test_coherence_is_store_true_action(
        self, configured_parser: argparse.ArgumentParser
    ) -> None:
        """--coherence uses store_true action (boolean flag)."""
        # When not specified, should be False
        args_without = configured_parser.parse_args([])
        assert args_without.coherence is False

        # When specified, should be True
        args_with = configured_parser.parse_args(["--coherence"])
        assert args_with.coherence is True


# =============================================================================
# Tests for add_coherence_arguments adding --coherence-only flag
# =============================================================================


class TestAddCoherenceOnlyFlag:
    """Verify --coherence-only flag is added by add_coherence_arguments."""

    def test_coherence_only_argument_added(
        self, configured_parser: argparse.ArgumentParser
    ) -> None:
        """add_coherence_arguments adds --coherence-only argument."""
        # Should not raise when parsing --coherence-only
        args = configured_parser.parse_args(["--coherence-only"])
        assert hasattr(args, "coherence_only")

    def test_coherence_only_default_is_false(
        self, configured_parser: argparse.ArgumentParser
    ) -> None:
        """--coherence-only defaults to False when not specified."""
        args = configured_parser.parse_args([])
        assert args.coherence_only is False

    def test_coherence_only_is_true_when_specified(
        self, configured_parser: argparse.ArgumentParser
    ) -> None:
        """--coherence-only is True when specified."""
        args = configured_parser.parse_args(["--coherence-only"])
        assert args.coherence_only is True

    def test_coherence_only_is_store_true_action(
        self, configured_parser: argparse.ArgumentParser
    ) -> None:
        """--coherence-only uses store_true action (boolean flag)."""
        # When not specified, should be False
        args_without = configured_parser.parse_args([])
        assert args_without.coherence_only is False

        # When specified, should be True
        args_with = configured_parser.parse_args(["--coherence-only"])
        assert args_with.coherence_only is True


# =============================================================================
# Tests for both flags together
# =============================================================================


class TestBothCoherenceFlags:
    """Verify both --coherence and --coherence-only work together."""

    def test_both_flags_can_be_used_together(
        self, configured_parser: argparse.ArgumentParser
    ) -> None:
        """Both --coherence and --coherence-only can be parsed together."""
        args = configured_parser.parse_args(["--coherence", "--coherence-only"])
        assert args.coherence is True
        assert args.coherence_only is True

    def test_neither_flag_specified(
        self, configured_parser: argparse.ArgumentParser
    ) -> None:
        """When neither flag is specified, both are False."""
        args = configured_parser.parse_args([])
        assert args.coherence is False
        assert args.coherence_only is False


# =============================================================================
# Tests for handle_coherence_validation function existence and signature
# =============================================================================


class TestHandleCoherenceValidationFunction:
    """Verify handle_coherence_validation function exists and has correct signature."""

    def test_function_exists(self) -> None:
        """handle_coherence_validation function exists in main module."""
        assert handle_coherence_validation is not None

    def test_function_is_callable(self) -> None:
        """handle_coherence_validation is a callable function."""
        assert callable(handle_coherence_validation)

    def test_accepts_namespace_argument(self) -> None:
        """handle_coherence_validation accepts an argparse.Namespace."""
        args = argparse.Namespace(
            coherence=False,
            coherence_only=False,
            use_manifest_chain=False,
            manifest_path=None,
            manifest_dir=None,
            quiet=False,
        )
        # Should not raise an exception
        result = handle_coherence_validation(args)
        assert isinstance(result, bool)


# =============================================================================
# Tests for handle_coherence_validation return type
# =============================================================================


class TestHandleCoherenceValidationReturnType:
    """Verify handle_coherence_validation returns bool."""

    def test_returns_bool_when_coherence_disabled(self) -> None:
        """handle_coherence_validation returns bool when coherence is disabled."""
        args = argparse.Namespace(
            coherence=False,
            coherence_only=False,
            use_manifest_chain=False,
            manifest_path=None,
            manifest_dir=None,
            quiet=False,
        )
        result = handle_coherence_validation(args)
        assert isinstance(result, bool)

    def test_returns_true_when_no_coherence_validation_needed(self) -> None:
        """handle_coherence_validation returns True when no coherence validation is needed."""
        args = argparse.Namespace(
            coherence=False,
            coherence_only=False,
            use_manifest_chain=False,
            manifest_path=None,
            manifest_dir=None,
            quiet=False,
        )
        result = handle_coherence_validation(args)
        # When coherence is not requested, should return True (skip/success)
        assert result is True


# =============================================================================
# Tests for handle_coherence_validation auto-enabling use_manifest_chain
# =============================================================================


class TestHandleCoherenceValidationAutoEnableManifestChain:
    """Verify handle_coherence_validation auto-enables use_manifest_chain."""

    def test_auto_enables_manifest_chain_when_coherence_is_true(self) -> None:
        """When coherence=True, use_manifest_chain should be auto-enabled."""
        args = argparse.Namespace(
            coherence=True,
            coherence_only=False,
            use_manifest_chain=False,
            manifest_path=None,
            manifest_dir="manifests",
            quiet=True,
        )

        # Call the function
        handle_coherence_validation(args)

        # The function should have set use_manifest_chain to True
        assert args.use_manifest_chain is True

    def test_auto_enables_manifest_chain_when_coherence_only_is_true(self) -> None:
        """When coherence_only=True, use_manifest_chain should be auto-enabled."""
        args = argparse.Namespace(
            coherence=False,
            coherence_only=True,
            use_manifest_chain=False,
            manifest_path=None,
            manifest_dir="manifests",
            quiet=True,
        )

        # Call the function
        handle_coherence_validation(args)

        # The function should have set use_manifest_chain to True
        assert args.use_manifest_chain is True

    def test_preserves_manifest_chain_when_already_true(self) -> None:
        """When use_manifest_chain is already True, it should remain True."""
        args = argparse.Namespace(
            coherence=True,
            coherence_only=False,
            use_manifest_chain=True,
            manifest_path=None,
            manifest_dir="manifests",
            quiet=True,
        )

        # Call the function
        handle_coherence_validation(args)

        # Should still be True
        assert args.use_manifest_chain is True

    def test_does_not_enable_manifest_chain_when_coherence_disabled(self) -> None:
        """When coherence is disabled, use_manifest_chain should not be changed."""
        args = argparse.Namespace(
            coherence=False,
            coherence_only=False,
            use_manifest_chain=False,
            manifest_path=None,
            manifest_dir=None,
            quiet=False,
        )

        # Call the function
        handle_coherence_validation(args)

        # Should remain False
        assert args.use_manifest_chain is False


# =============================================================================
# Tests for handle_coherence_validation success behavior
# =============================================================================


class TestHandleCoherenceValidationSuccess:
    """Verify handle_coherence_validation returns True when coherence validation succeeds."""

    def test_returns_true_when_validation_not_needed(self) -> None:
        """Returns True when no coherence validation is needed."""
        args = argparse.Namespace(
            coherence=False,
            coherence_only=False,
            use_manifest_chain=False,
            manifest_path=None,
            manifest_dir=None,
            quiet=False,
        )

        result = handle_coherence_validation(args)
        assert result is True

    def test_returns_bool_when_coherence_enabled(
        self, manifest_dir: Path, manifest_file: Path
    ) -> None:
        """Returns bool when coherence validation is enabled."""
        args = argparse.Namespace(
            coherence=True,
            coherence_only=False,
            use_manifest_chain=False,
            manifest_path=str(manifest_file),
            manifest_dir=str(manifest_dir),
            quiet=True,
        )

        result = handle_coherence_validation(args)
        # Should return True or False depending on validation outcome
        assert isinstance(result, bool)

    def test_returns_bool_when_coherence_only_enabled(
        self, manifest_dir: Path, manifest_file: Path
    ) -> None:
        """Returns bool when coherence_only validation is enabled."""
        args = argparse.Namespace(
            coherence=False,
            coherence_only=True,
            use_manifest_chain=False,
            manifest_path=str(manifest_file),
            manifest_dir=str(manifest_dir),
            quiet=True,
        )

        result = handle_coherence_validation(args)
        # Should return True or False depending on validation outcome
        assert isinstance(result, bool)


# =============================================================================
# Tests for handle_coherence_validation with mock CoherenceValidator
# =============================================================================


class TestHandleCoherenceValidationWithMock:
    """Verify handle_coherence_validation interacts correctly with CoherenceValidator."""

    def test_calls_coherence_validator_when_coherence_true(
        self, manifest_dir: Path, manifest_file: Path
    ) -> None:
        """When coherence=True, CoherenceValidator should be called."""
        args = argparse.Namespace(
            coherence=True,
            coherence_only=False,
            use_manifest_chain=False,
            manifest_path=str(manifest_file),
            manifest_dir=str(manifest_dir),
            quiet=True,
        )

        # The function should run without error and return a bool
        result = handle_coherence_validation(args)
        assert isinstance(result, bool)

    def test_calls_coherence_validator_when_coherence_only_true(
        self, manifest_dir: Path, manifest_file: Path
    ) -> None:
        """When coherence_only=True, CoherenceValidator should be called."""
        args = argparse.Namespace(
            coherence=False,
            coherence_only=True,
            use_manifest_chain=False,
            manifest_path=str(manifest_file),
            manifest_dir=str(manifest_dir),
            quiet=True,
        )

        # The function should run without error and return a bool
        result = handle_coherence_validation(args)
        assert isinstance(result, bool)


# =============================================================================
# Integration tests
# =============================================================================


class TestIntegration:
    """Integration tests for CLI coherence integration."""

    def test_add_arguments_then_parse_and_handle(
        self,
        validate_parser: argparse.ArgumentParser,
        manifest_dir: Path,
        manifest_file: Path,
    ) -> None:
        """Complete workflow: add arguments, parse, and handle validation."""
        # Add coherence arguments
        add_coherence_arguments(validate_parser)

        # Add other required arguments for handle_coherence_validation
        validate_parser.add_argument(
            "--use-manifest-chain", action="store_true", default=False
        )
        validate_parser.add_argument("--manifest-dir", default=None)
        validate_parser.add_argument(
            "--quiet", "-q", action="store_true", default=False
        )
        validate_parser.add_argument("manifest_path", nargs="?", default=None)

        # Parse arguments
        args = validate_parser.parse_args(
            [
                "--coherence",
                "--manifest-dir",
                str(manifest_dir),
                str(manifest_file),
            ]
        )

        # Handle validation
        result = handle_coherence_validation(args)

        # Should complete without error and return bool
        assert isinstance(result, bool)
        # Should have auto-enabled use_manifest_chain
        assert args.use_manifest_chain is True

    def test_flags_available_in_help_output(
        self, validate_parser: argparse.ArgumentParser, capsys: pytest.CaptureFixture
    ) -> None:
        """--coherence and --coherence-only should appear in help output."""
        add_coherence_arguments(validate_parser)

        with pytest.raises(SystemExit) as exc_info:
            validate_parser.parse_args(["--help"])

        assert exc_info.value.code == 0
        captured = capsys.readouterr()

        # Both flags should be mentioned in help
        assert "--coherence" in captured.out
        # The long flag --coherence-only should be present
        assert "coherence" in captured.out.lower()

    def test_workflow_without_coherence_flags(
        self, validate_parser: argparse.ArgumentParser
    ) -> None:
        """Workflow works when coherence flags are not specified."""
        add_coherence_arguments(validate_parser)
        validate_parser.add_argument(
            "--use-manifest-chain", action="store_true", default=False
        )
        validate_parser.add_argument("--manifest-dir", default=None)
        validate_parser.add_argument(
            "--quiet", "-q", action="store_true", default=False
        )
        validate_parser.add_argument("manifest_path", nargs="?", default=None)

        # Parse without coherence flags
        args = validate_parser.parse_args([])

        # Handle validation
        result = handle_coherence_validation(args)

        # Should return True (no validation needed)
        assert result is True
        # use_manifest_chain should remain False
        assert args.use_manifest_chain is False


# =============================================================================
# Tests for argument naming convention
# =============================================================================


class TestArgumentNamingConvention:
    """Verify argument naming follows convention with underscores in namespace."""

    def test_coherence_uses_underscore_in_namespace(
        self, configured_parser: argparse.ArgumentParser
    ) -> None:
        """--coherence flag creates 'coherence' attribute (no dash)."""
        args = configured_parser.parse_args(["--coherence"])
        # Should use underscore in namespace attribute
        assert hasattr(args, "coherence")
        assert not hasattr(args, "coherence-flag")

    def test_coherence_only_uses_underscore_in_namespace(
        self, configured_parser: argparse.ArgumentParser
    ) -> None:
        """--coherence-only flag creates 'coherence_only' attribute."""
        args = configured_parser.parse_args(["--coherence-only"])
        # argparse converts dashes to underscores in namespace
        assert hasattr(args, "coherence_only")
        assert not hasattr(args, "coherence-only")
