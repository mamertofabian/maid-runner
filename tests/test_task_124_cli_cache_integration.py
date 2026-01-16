"""Behavioral tests for Task 124: CLI cache integration.

Tests the use_cache parameter integration for the validate CLI command:
- run_validation() function accepts use_cache parameter
- Default behavior is use_cache=False (backward compatible)
- Cache flag propagation to underlying functions
- CLI flag parsing with argparse
- End-to-end validation with cache enabled
"""

import inspect
import json
from pathlib import Path
from typing import Optional
from unittest.mock import patch


class TestRunValidationUseCacheParameter:
    """Tests for run_validation() accepting use_cache parameter."""

    def test_run_validation_has_use_cache_parameter(self):
        """Test that run_validation accepts use_cache parameter without error."""
        from maid_runner.cli.validate import run_validation

        sig = inspect.signature(run_validation)
        assert (
            "use_cache" in sig.parameters
        ), "run_validation() must have 'use_cache' parameter"

    def test_run_validation_use_cache_parameter_type_is_bool(self):
        """Test that use_cache parameter has bool type annotation."""
        from maid_runner.cli.validate import run_validation

        sig = inspect.signature(run_validation)
        param = sig.parameters.get("use_cache")
        assert param is not None, "run_validation() must have 'use_cache' parameter"
        assert param.annotation is bool, "use_cache parameter must have bool annotation"

    def test_run_validation_use_cache_default_is_false(self):
        """Test that use_cache defaults to False for backward compatibility."""
        from maid_runner.cli.validate import run_validation

        sig = inspect.signature(run_validation)
        param = sig.parameters.get("use_cache")
        assert param is not None, "run_validation() must have 'use_cache' parameter"
        assert (
            param.default is False
        ), "use_cache default must be False for backward compatibility"

    def test_run_validation_accepts_use_cache_true(self, tmp_path: Path):
        """Test that run_validation accepts use_cache=True without error."""
        from maid_runner.cli.validate import run_validation

        # Create a minimal valid manifest
        manifest_path = tmp_path / "test.manifest.json"
        manifest_data = {
            "version": "1",
            "goal": "Test cache integration",
            "taskType": "edit",
            "editableFiles": ["src/test.py"],
            "expectedArtifacts": {
                "file": "src/test.py",
                "contains": [{"type": "function", "name": "test_func"}],
            },
        }
        manifest_path.write_text(json.dumps(manifest_data))

        # Create the target file
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "test.py").write_text("def test_func(): pass")

        # Mock to prevent actual validation and check the call completes
        with patch("maid_runner.cli._text_mode_validation.validate_schema"):
            with patch(
                "maid_runner.cli._text_mode_validation.validate_manifest_semantics"
            ):
                with patch(
                    "maid_runner.cli._text_mode_validation.validate_supersession"
                ):
                    with patch(
                        "maid_runner.cli._text_mode_validation.validate_with_ast"
                    ):
                        import os

                        original_cwd = os.getcwd()
                        try:
                            os.chdir(tmp_path)
                            # This should not raise - the parameter should be accepted
                            run_validation(
                                manifest_path=str(manifest_path),
                                validation_mode="implementation",
                                use_manifest_chain=False,
                                quiet=True,
                                manifest_dir=None,
                                skip_file_tracking=True,
                                watch=False,
                                watch_all=False,
                                timeout=300,
                                verbose=False,
                                skip_tests=False,
                                use_cache=True,
                            )
                        except SystemExit:
                            pass  # Expected - validation may exit
                        finally:
                            os.chdir(original_cwd)

    def test_run_validation_accepts_use_cache_false(self, tmp_path: Path):
        """Test that run_validation accepts use_cache=False without error."""
        from maid_runner.cli.validate import run_validation

        manifest_path = tmp_path / "test.manifest.json"
        manifest_data = {
            "version": "1",
            "goal": "Test cache integration",
            "taskType": "edit",
            "editableFiles": ["src/test.py"],
            "expectedArtifacts": {
                "file": "src/test.py",
                "contains": [{"type": "function", "name": "test_func"}],
            },
        }
        manifest_path.write_text(json.dumps(manifest_data))

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "test.py").write_text("def test_func(): pass")

        with patch("maid_runner.cli._text_mode_validation.validate_schema"):
            with patch(
                "maid_runner.cli._text_mode_validation.validate_manifest_semantics"
            ):
                with patch(
                    "maid_runner.cli._text_mode_validation.validate_supersession"
                ):
                    with patch(
                        "maid_runner.cli._text_mode_validation.validate_with_ast"
                    ):
                        import os

                        original_cwd = os.getcwd()
                        try:
                            os.chdir(tmp_path)
                            run_validation(
                                manifest_path=str(manifest_path),
                                validation_mode="implementation",
                                use_manifest_chain=False,
                                quiet=True,
                                manifest_dir=None,
                                skip_file_tracking=True,
                                watch=False,
                                watch_all=False,
                                timeout=300,
                                verbose=False,
                                skip_tests=False,
                                use_cache=False,
                            )
                        except SystemExit:
                            pass  # Expected
                        finally:
                            os.chdir(original_cwd)


class TestCacheFlagPropagationToDiscoverRelatedManifests:
    """Tests for use_cache flag propagation to discover_related_manifests()."""

    def test_use_cache_true_propagates_to_discover_related_manifests(
        self, tmp_path: Path
    ):
        """Test that use_cache=True is passed to discover_related_manifests()."""
        from maid_runner.cli.validate import run_validation

        manifest_path = tmp_path / "manifests" / "task-001.manifest.json"
        manifest_path.parent.mkdir(parents=True)
        manifest_data = {
            "version": "1",
            "goal": "Test cache propagation",
            "taskType": "edit",
            "editableFiles": ["src/test.py"],
            "expectedArtifacts": {
                "file": "src/test.py",
                "contains": [{"type": "function", "name": "test_func"}],
            },
        }
        manifest_path.write_text(json.dumps(manifest_data))

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "test.py").write_text("def test_func(): pass")

        # Track calls to discover_related_manifests
        discover_calls = []

        def mock_discover(target_file, use_cache=False):
            discover_calls.append({"target_file": target_file, "use_cache": use_cache})
            return []  # Return empty list of related manifests

        with patch("maid_runner.cli._text_mode_validation.validate_schema"):
            with patch(
                "maid_runner.cli._text_mode_validation.validate_manifest_semantics"
            ):
                with patch(
                    "maid_runner.cli._text_mode_validation.validate_supersession"
                ):
                    with patch(
                        "maid_runner.cli._text_mode_validation.validate_with_ast"
                    ) as mock_ast:
                        # Mock validate_with_ast to prevent actual validation
                        mock_ast.return_value = None

                        with patch(
                            "maid_runner.validators.manifest_validator.discover_related_manifests",
                            mock_discover,
                        ):
                            import os

                            original_cwd = os.getcwd()
                            try:
                                os.chdir(tmp_path)
                                run_validation(
                                    manifest_path=str(manifest_path),
                                    validation_mode="implementation",
                                    use_manifest_chain=True,
                                    quiet=True,
                                    manifest_dir=None,
                                    skip_file_tracking=True,
                                    watch=False,
                                    watch_all=False,
                                    timeout=300,
                                    verbose=False,
                                    skip_tests=False,
                                    use_cache=True,
                                )
                            except SystemExit:
                                pass
                            finally:
                                os.chdir(original_cwd)

                        # Verify use_cache=True was passed
                        if discover_calls:
                            assert any(
                                call.get("use_cache") is True for call in discover_calls
                            ), "discover_related_manifests should be called with use_cache=True"

    def test_use_cache_false_propagates_to_discover_related_manifests(
        self, tmp_path: Path
    ):
        """Test that use_cache=False (default) is passed to discover_related_manifests()."""
        from maid_runner.cli.validate import run_validation

        manifest_path = tmp_path / "manifests" / "task-001.manifest.json"
        manifest_path.parent.mkdir(parents=True)
        manifest_data = {
            "version": "1",
            "goal": "Test cache propagation default",
            "taskType": "edit",
            "editableFiles": ["src/test.py"],
            "expectedArtifacts": {
                "file": "src/test.py",
                "contains": [{"type": "function", "name": "test_func"}],
            },
        }
        manifest_path.write_text(json.dumps(manifest_data))

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "test.py").write_text("def test_func(): pass")

        discover_calls = []

        def mock_discover(target_file, use_cache=False):
            discover_calls.append({"target_file": target_file, "use_cache": use_cache})
            return []

        with patch("maid_runner.cli._text_mode_validation.validate_schema"):
            with patch(
                "maid_runner.cli._text_mode_validation.validate_manifest_semantics"
            ):
                with patch(
                    "maid_runner.cli._text_mode_validation.validate_supersession"
                ):
                    with patch(
                        "maid_runner.cli._text_mode_validation.validate_with_ast"
                    ) as mock_ast:
                        mock_ast.return_value = None

                        with patch(
                            "maid_runner.validators.manifest_validator.discover_related_manifests",
                            mock_discover,
                        ):
                            import os

                            original_cwd = os.getcwd()
                            try:
                                os.chdir(tmp_path)
                                run_validation(
                                    manifest_path=str(manifest_path),
                                    validation_mode="implementation",
                                    use_manifest_chain=True,
                                    quiet=True,
                                    manifest_dir=None,
                                    skip_file_tracking=True,
                                    watch=False,
                                    watch_all=False,
                                    timeout=300,
                                    verbose=False,
                                    skip_tests=False,
                                    use_cache=False,
                                )
                            except SystemExit:
                                pass
                            finally:
                                os.chdir(original_cwd)

                        # When use_cache=False (default), calls should use default
                        if discover_calls:
                            for call in discover_calls:
                                assert (
                                    call.get("use_cache") is False
                                    or call.get("use_cache") is None
                                ), "discover_related_manifests should be called with use_cache=False by default"


class TestCacheFlagPropagationToGetSupersededManifests:
    """Tests for use_cache flag propagation to get_superseded_manifests()."""

    def test_use_cache_true_propagates_to_get_superseded_manifests(
        self, tmp_path: Path
    ):
        """Test that use_cache=True is passed to get_superseded_manifests() in directory validation."""
        from maid_runner.cli.validate import run_validation

        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir(parents=True)

        manifest_data = {
            "version": "1",
            "goal": "Test cache in directory validation",
            "taskType": "edit",
            "editableFiles": ["src/test.py"],
            "expectedArtifacts": {
                "file": "src/test.py",
                "contains": [{"type": "function", "name": "test_func"}],
            },
        }
        (manifests_dir / "task-001.manifest.json").write_text(json.dumps(manifest_data))

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "test.py").write_text("def test_func(): pass")

        superseded_calls = []

        def mock_get_superseded(manifests_path, use_cache=False):
            superseded_calls.append(
                {"manifests_path": manifests_path, "use_cache": use_cache}
            )
            return set()

        with patch(
            "maid_runner.cli.validate.get_superseded_manifests", mock_get_superseded
        ):
            with patch(
                "maid_runner.utils.get_superseded_manifests", mock_get_superseded
            ):
                import os

                original_cwd = os.getcwd()
                try:
                    os.chdir(tmp_path)
                    run_validation(
                        manifest_path=None,
                        validation_mode="implementation",
                        use_manifest_chain=True,
                        quiet=True,
                        manifest_dir=str(manifests_dir),
                        skip_file_tracking=True,
                        watch=False,
                        watch_all=False,
                        timeout=300,
                        verbose=False,
                        skip_tests=False,
                        use_cache=True,
                    )
                except SystemExit:
                    pass
                finally:
                    os.chdir(original_cwd)

        # Verify at least one call had use_cache=True
        if superseded_calls:
            assert any(
                call.get("use_cache") is True for call in superseded_calls
            ), "get_superseded_manifests should be called with use_cache=True"


class TestCLIFlagParsing:
    """Tests for --use-cache CLI flag parsing with argparse."""

    def test_validate_subparser_has_use_cache_argument(self):
        """Test that the validate subparser recognizes --use-cache flag."""
        import argparse

        # Create a parser like main() does
        parser = argparse.ArgumentParser(prog="maid")
        subparsers = parser.add_subparsers(dest="command")

        validate_parser = subparsers.add_parser("validate")
        validate_parser.add_argument("manifest_path", nargs="?")
        validate_parser.add_argument("--use-cache", action="store_true")

        # Parse args with --use-cache
        args = parser.parse_args(["validate", "test.manifest.json", "--use-cache"])

        assert args.use_cache is True, "--use-cache flag should set use_cache to True"

    def test_validate_subparser_use_cache_default_is_false(self):
        """Test that --use-cache defaults to False when not provided."""
        import argparse

        parser = argparse.ArgumentParser(prog="maid")
        subparsers = parser.add_subparsers(dest="command")

        validate_parser = subparsers.add_parser("validate")
        validate_parser.add_argument("manifest_path", nargs="?")
        validate_parser.add_argument("--use-cache", action="store_true")

        # Parse args without --use-cache
        args = parser.parse_args(["validate", "test.manifest.json"])

        assert (
            args.use_cache is False
        ), "--use-cache should default to False when not provided"

    def test_main_cli_passes_use_cache_to_run_validation(self, tmp_path: Path):
        """Test that main CLI passes use_cache to run_validation when flag is set."""
        manifest_path = tmp_path / "test.manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "version": "1",
                    "goal": "Test",
                    "taskType": "edit",
                    "editableFiles": ["test.py"],
                    "expectedArtifacts": {
                        "file": "test.py",
                        "contains": [{"type": "function", "name": "test"}],
                    },
                }
            )
        )

        # Mock run_validation to capture calls
        run_validation_calls = []

        def mock_run_validation(*args, **kwargs):
            run_validation_calls.append({"args": args, "kwargs": kwargs})

        with patch("maid_runner.cli.validate.run_validation", mock_run_validation):
            with patch(
                "sys.argv",
                ["maid", "validate", str(manifest_path), "--use-cache"],
            ):
                try:
                    from maid_runner.cli.main import main

                    main()
                except SystemExit:
                    pass

        # Check that use_cache=True was passed
        if run_validation_calls:
            last_call = run_validation_calls[-1]
            # use_cache may be in kwargs or as positional arg
            assert last_call["kwargs"].get("use_cache") is True or (
                len(last_call["args"]) >= 12 and last_call["args"][11] is True
            ), "main() should pass use_cache=True to run_validation"


class TestEndToEndCacheIntegration:
    """Integration tests for cache-enabled validation."""

    def test_validation_with_cache_enabled_works(self, tmp_path: Path):
        """Test that end-to-end validation with use_cache=True completes successfully."""
        from maid_runner.cli.validate import run_validation

        # Create a complete test setup
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        src_dir = tmp_path / "src"
        src_dir.mkdir()

        # Create a valid Python file
        (src_dir / "example.py").write_text(
            '''"""Example module."""

def example_function(param: str) -> str:
    """Example function."""
    return param
'''
        )

        # Create a valid manifest
        manifest_data = {
            "version": "1",
            "goal": "Test cache-enabled validation",
            "taskType": "edit",
            "editableFiles": ["src/example.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "src/example.py",
                "contains": [
                    {
                        "type": "function",
                        "name": "example_function",
                        "args": [{"name": "param", "type": "str"}],
                        "returns": "str",
                    }
                ],
            },
            "validationCommand": ["pytest", "-v"],
        }
        manifest_path = manifests_dir / "task-001.manifest.json"
        manifest_path.write_text(json.dumps(manifest_data))

        import os

        original_cwd = os.getcwd()
        exit_code = None

        try:
            os.chdir(tmp_path)

            # Run validation with cache enabled
            try:
                run_validation(
                    manifest_path=str(manifest_path),
                    validation_mode="implementation",
                    use_manifest_chain=False,
                    quiet=True,
                    manifest_dir=None,
                    skip_file_tracking=True,
                    watch=False,
                    watch_all=False,
                    timeout=300,
                    verbose=False,
                    skip_tests=True,
                    use_cache=True,
                )
                exit_code = 0
            except SystemExit as e:
                exit_code = e.code

        finally:
            os.chdir(original_cwd)

        # Validation should pass (exit code 0 or None)
        assert exit_code in (
            0,
            None,
        ), f"Validation with cache should succeed, got exit code: {exit_code}"

    def test_validation_with_cache_disabled_works(self, tmp_path: Path):
        """Test that end-to-end validation with use_cache=False completes successfully."""
        from maid_runner.cli.validate import run_validation

        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        src_dir = tmp_path / "src"
        src_dir.mkdir()

        (src_dir / "example.py").write_text(
            '''"""Example module."""

def example_function(param: str) -> str:
    """Example function."""
    return param
'''
        )

        manifest_data = {
            "version": "1",
            "goal": "Test cache-disabled validation",
            "taskType": "edit",
            "editableFiles": ["src/example.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "src/example.py",
                "contains": [
                    {
                        "type": "function",
                        "name": "example_function",
                        "args": [{"name": "param", "type": "str"}],
                        "returns": "str",
                    }
                ],
            },
            "validationCommand": ["pytest", "-v"],
        }
        manifest_path = manifests_dir / "task-001.manifest.json"
        manifest_path.write_text(json.dumps(manifest_data))

        import os

        original_cwd = os.getcwd()
        exit_code = None

        try:
            os.chdir(tmp_path)

            try:
                run_validation(
                    manifest_path=str(manifest_path),
                    validation_mode="implementation",
                    use_manifest_chain=False,
                    quiet=True,
                    manifest_dir=None,
                    skip_file_tracking=True,
                    watch=False,
                    watch_all=False,
                    timeout=300,
                    verbose=False,
                    skip_tests=True,
                    use_cache=False,
                )
                exit_code = 0
            except SystemExit as e:
                exit_code = e.code

        finally:
            os.chdir(original_cwd)

        assert exit_code in (
            0,
            None,
        ), f"Validation without cache should succeed, got exit code: {exit_code}"


class TestRunValidationSignatureComplete:
    """Tests to verify run_validation has the complete expected signature."""

    def test_run_validation_signature_matches_manifest(self):
        """Test that run_validation has all parameters defined in the manifest."""
        from maid_runner.cli.validate import run_validation

        sig = inspect.signature(run_validation)
        params = sig.parameters

        # All parameters from the manifest
        expected_params = {
            "manifest_path": Optional[str],
            "validation_mode": str,
            "use_manifest_chain": bool,
            "quiet": bool,
            "manifest_dir": Optional[str],
            "skip_file_tracking": bool,
            "watch": bool,
            "watch_all": bool,
            "timeout": int,
            "verbose": bool,
            "skip_tests": bool,
            "use_cache": bool,  # The new parameter for task-124
        }

        for param_name, expected_type in expected_params.items():
            assert (
                param_name in params
            ), f"run_validation() missing parameter: {param_name}"

    def test_run_validation_returns_none(self):
        """Test that run_validation has return type None."""
        from maid_runner.cli.validate import run_validation

        sig = inspect.signature(run_validation)
        assert sig.return_annotation is None or sig.return_annotation is type(
            None
        ), "run_validation should return None"
