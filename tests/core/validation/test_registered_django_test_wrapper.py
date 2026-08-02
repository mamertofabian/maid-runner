"""Behavioral contract for reviewed repository-owned Django test wrappers."""

from __future__ import annotations

from pathlib import Path

import pytest

from maid_runner.core import config as config_module
from maid_runner.core._validation_test_artifacts import (
    validate_manifest_test_commands,
)
from maid_runner.core.config import MaidConfig, load_config
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode
from maid_runner.core.test_runner import run_manifest_tests


def _write_test_project(root: Path, *, register_wrapper: bool = True) -> Path:
    test_file = root / "src" / "audio" / "tests" / "test_segments.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_segment():\n    pass\n")

    wrapper = root / "scripts" / "test"
    wrapper.parent.mkdir()
    wrapper.write_text("#!/bin/sh\nprintf ran > wrapper-ran.txt\n")
    wrapper.chmod(0o755)

    if register_wrapper:
        (root / ".maidrc.yaml").write_text(
            "test_runner_wrappers:\n"
            "  - command: ./scripts/test\n"
            "    runner: django\n"
        )

    manifest_dir = root / "manifests"
    manifest_dir.mkdir()
    manifest_path = manifest_dir / "wrapper.manifest.yaml"
    manifest_path.write_text(
        'schema: "2"\n'
        'goal: "Exercise the safe Django wrapper"\n'
        "type: fix\n"
        'created: "2026-08-02T00:00:00Z"\n'
        "files:\n"
        "  create:\n"
        "    - path: src/audio/tests/test_segments.py\n"
        "      artifacts:\n"
        "        - kind: test_function\n"
        "          name: test_segment\n"
        "validate:\n"
        "  - ./scripts/test audio.tests.test_segments\n"
    )
    return manifest_path


def test_load_config_accepts_existing_project_relative_django_wrapper(tmp_path):
    _write_test_project(tmp_path)

    assert MaidConfig.test_runner_wrappers == ()
    config: MaidConfig = load_config(tmp_path)

    assert config.test_runner_wrappers == (
        config_module.TestRunnerWrapperConfig(
            command="scripts/test",
            runner="django",
        ),
    )


def test_load_config_rejects_unsafe_or_unsupported_test_wrapper_declarations(
    tmp_path,
):
    cases = (
        "  - command: /tmp/test\n    runner: django\n",
        "  - command: ../scripts/test\n    runner: django\n",
        "  - command: ./scripts/missing\n    runner: django\n",
        "  - command: ./scripts/test\n    runner: custom\n",
        (
            "  - command: ./scripts/test\n    runner: django\n"
            "  - command: scripts/test\n    runner: django\n"
        ),
    )
    wrapper = tmp_path / "scripts" / "test"
    wrapper.parent.mkdir()
    wrapper.write_text("#!/bin/sh\n")

    for entries in cases:
        (tmp_path / ".maidrc.yaml").write_text(f"test_runner_wrappers:\n{entries}")
        with pytest.raises(ValueError):
            load_config(tmp_path)


def test_command_integrity_accepts_registered_django_wrapper_dotted_label(tmp_path):
    manifest_path = _write_test_project(tmp_path)

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert errors == []


def test_command_integrity_keeps_unregistered_wrapper_fail_closed(tmp_path):
    manifest_path = _write_test_project(tmp_path, register_wrapper=False)

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_registered_django_wrapper_does_not_authorize_another_command(tmp_path):
    manifest_path = _write_test_project(tmp_path)
    other_wrapper = tmp_path / "scripts" / "other-test"
    other_wrapper.write_text("#!/bin/sh\nexit 0\n")
    other_wrapper.chmod(0o755)
    manifest_path.write_text(
        manifest_path.read_text().replace("./scripts/test", "./scripts/other-test")
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_registered_django_wrapper_rejects_package_runner_cwd_change(tmp_path):
    manifest_path = _write_test_project(tmp_path)
    nested_wrapper = tmp_path / "frontend" / "scripts" / "test"
    nested_wrapper.parent.mkdir(parents=True)
    nested_wrapper.write_text("#!/bin/sh\nexit 0\n")
    nested_wrapper.chmod(0o755)
    manifest_path.write_text(
        manifest_path.read_text().replace(
            "./scripts/test audio.tests.test_segments",
            "pnpm --dir frontend exec ./scripts/test audio.tests.test_segments",
        )
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_registered_django_wrapper_rejects_docker_exec_namespace(tmp_path):
    manifest_path = _write_test_project(tmp_path)
    manifest_path.write_text(
        manifest_path.read_text().replace(
            "./scripts/test audio.tests.test_segments",
            (
                "docker exec --workdir frontend app "
                "./scripts/test audio.tests.test_segments"
            ),
        )
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_registered_django_wrapper_rejects_narrow_selector(tmp_path):
    manifest_path = _write_test_project(tmp_path)
    manifest_path.write_text(
        manifest_path.read_text().replace(
            "audio.tests.test_segments\n",
            "audio.tests.test_segments.TestSegments\n",
        )
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_registered_django_wrapper_rejects_pythonpath_mutation(tmp_path):
    manifest_path = _write_test_project(tmp_path)
    manifest_path.write_text(
        manifest_path.read_text().replace(
            "audio.tests.test_segments\n",
            "audio.tests.test_segments --pythonpath ../outside\n",
        )
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_run_manifest_tests_executes_registered_django_wrapper(tmp_path):
    manifest_path = _write_test_project(tmp_path)

    result = run_manifest_tests(manifest_path, project_root=tmp_path)

    assert (result.total, result.passed, result.failed) == (1, 1, 0)
    assert (tmp_path / "wrapper-ran.txt").read_text() == "ran"
