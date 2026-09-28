"""Native pytest configuration must not masquerade as executed tests."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from maid_runner.core._validation_test_artifacts import validate_manifest_test_commands
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode
from maid_runner.core.test_runner import run_manifest_tests


_TEST = "tests/unit/test_contract.py"
_NATIVE = int(pytest.__version__.split(".")[0]) >= 9


def _project(
    root: Path,
    config: str = "pytest.toml",
    *,
    addopts=None,
    fails=True,
    location="root",
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "tests/unit").mkdir(parents=True)
    (root / _TEST).write_text(
        "from pathlib import Path\nimport pytest\n"
        "def test_alpha():\n    Path('alpha-ran.txt').touch()\n"
        f"    assert {not fails!r}\n"
        "@pytest.mark.integration\ndef test_beta():\n"
        "    Path('beta-ran.txt').touch()\n    assert 2 + 2 == 4\n"
    )
    target = root / config
    if location == "nested":
        target = root / "tests/unit" / config
    elif location == "parent":
        target = root.parent / config
    table = "pytest" if config in {"pytest.toml", ".pytest.toml"} else "tool.pytest"
    target.write_text(
        f"[{table}]\naddopts = {json.dumps(addopts if addopts is not None else ['--collect-only'])}\nmarkers = ['integration: integration tests']\n"
    )
    command = ["python", "-m", "pytest", _TEST, "-q"]
    if config == "custom.toml":
        command.extend(["-c", config])
    manifest = root / "native.manifest.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "type": "fix",
                "created": "2026-09-28",
                "goal": "Require native pytest to execute the declared cases",
                "files": {
                    "scope": [{"path": "policy.py", "reason": "Policy wiring"}],
                    "read": [_TEST],
                },
                "validate": [command],
            }
        )
    )
    (root / "policy.py").write_text("value = 4\n")
    return manifest


def _errors(root: Path, manifest: Path):
    return validate_manifest_test_commands(load_manifest(manifest), root)


@pytest.mark.parametrize(
    "config", ["pytest.toml", ".pytest.toml", "pyproject.toml", "custom.toml"]
)
def test_native_nonexecuting_config_is_checked_in_consumer_version(
    tmp_path: Path, config: str
) -> None:
    manifest = _project(tmp_path, config)

    errors = _errors(tmp_path, manifest)

    if _NATIVE:
        assert [e.code for e in errors] == [
            ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
        ]
        assert run_manifest_tests(manifest, project_root=tmp_path).total == 0
        assert not (tmp_path / "alpha-ran.txt").exists()
    else:
        assert errors == []
        result = run_manifest_tests(manifest, project_root=tmp_path)
        assert (result.total, result.passed, result.failed) == (1, 0, 1)
        assert (tmp_path / "alpha-ran.txt").exists()


@pytest.mark.parametrize(
    "config", ["pytest.toml", ".pytest.toml", "pyproject.toml", "custom.toml"]
)
def test_benign_native_config_runs_all_tests_without_rewriting_files(
    tmp_path: Path, config: str
) -> None:
    manifest = _project(tmp_path, config, addopts=["-q"], fails=False)
    original = (tmp_path / config).read_bytes()

    assert _errors(tmp_path, manifest) == []
    assert not (tmp_path / "alpha-ran.txt").exists()
    result = run_manifest_tests(manifest, project_root=tmp_path)

    assert (result.total, result.passed, result.failed) == (1, 1, 0)
    assert (tmp_path / "alpha-ran.txt").exists()
    assert (tmp_path / "beta-ran.txt").exists()
    assert (tmp_path / config).read_bytes() == original


@pytest.mark.parametrize("location", ["nested", "parent"])
@pytest.mark.parametrize("config", ["pytest.toml", ".pytest.toml", "pyproject.toml"])
def test_native_config_candidates_include_test_and_project_ancestors(
    tmp_path: Path, location: str, config: str
) -> None:
    from maid_runner.core._pytest_config_addopts import (
        requires_native_pytest_config_check,
    )

    root = tmp_path / "project"
    manifest = _project(root, config, location=location)
    command = load_manifest(manifest).validate_commands[0]

    assert requires_native_pytest_config_check(root, command, [_TEST]) is True
    errors = _errors(root, manifest)
    if _NATIVE:
        assert [e.code for e in errors] == [
            ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
        ]
    else:
        assert errors == []


def test_native_config_does_not_affect_non_pytest_commands(tmp_path: Path) -> None:
    from maid_runner.core._pytest_config_addopts import (
        requires_native_pytest_config_check,
    )

    _project(tmp_path)

    assert (
        requires_native_pytest_config_check(
            tmp_path, ["node", "--test", "test.js"], [_TEST]
        )
        is False
    )
    assert (
        requires_native_pytest_config_check(
            tmp_path, ["deno", "test", "test.ts"], [_TEST]
        )
        is False
    )


def test_legacy_only_pyproject_keeps_the_existing_inspection_path(
    tmp_path: Path,
) -> None:
    from maid_runner.core._pytest_config_addopts import (
        requires_native_pytest_config_check,
    )

    manifest = _project(tmp_path, "pyproject.toml")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "-q"\n'
    )
    command = load_manifest(manifest).validate_commands[0]

    assert requires_native_pytest_config_check(tmp_path, command, [_TEST]) is False
    assert _errors(tmp_path, manifest) == []


def test_explicit_legacy_config_takes_precedence_over_native_candidates(
    tmp_path: Path,
) -> None:
    manifest = _project(tmp_path, fails=False)
    (tmp_path / "legacy.ini").write_text("[pytest]\naddopts = -q --tb=short\n")
    data = yaml.safe_load(manifest.read_text())
    data["validate"][0].extend(["-c", "legacy.ini"])
    manifest.write_text(yaml.safe_dump(data))

    assert _errors(tmp_path, manifest) == []
    result = run_manifest_tests(manifest, project_root=tmp_path)
    assert (result.total, result.passed, result.failed) == (1, 1, 0)
    assert (tmp_path / "alpha-ran.txt").exists()


@pytest.mark.parametrize("override", ["", "--collect-only", "--collectonly"])
def test_explicit_addopts_override_retains_execution_checks(
    tmp_path: Path, override: str
) -> None:
    manifest = _project(tmp_path)
    data = yaml.safe_load(manifest.read_text())
    data["validate"][0].extend(["-o", "addopts=" + override])
    manifest.write_text(yaml.safe_dump(data))

    errors = _errors(tmp_path, manifest)

    if override:
        assert [e.code for e in errors] == [
            ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
        ]
        assert run_manifest_tests(manifest, project_root=tmp_path).total == 0
        assert not (tmp_path / "alpha-ran.txt").exists()
    else:
        assert errors == []
        result = run_manifest_tests(manifest, project_root=tmp_path)
        assert (result.total, result.passed, result.failed) == (1, 0, 1)
        assert (tmp_path / "alpha-ran.txt").exists()


@pytest.mark.parametrize("config", ["pytest.toml", "pyproject.toml"])
def test_native_selectors_cannot_omit_declared_cases(
    tmp_path: Path, config: str
) -> None:
    manifest = _project(
        tmp_path, config, addopts=["-m", "not integration"], fails=False
    )

    errors = _errors(tmp_path, manifest)

    if _NATIVE:
        assert [e.code for e in errors] == [
            ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
        ]
        assert not (tmp_path / "alpha-ran.txt").exists()
    else:
        assert errors == []


def test_native_formats_use_real_precedence_over_legacy_ini(tmp_path: Path) -> None:
    manifest = _project(tmp_path, addopts=["-q"], fails=False)
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = --collect-only\n")

    errors = _errors(tmp_path, manifest)

    if _NATIVE:
        assert errors == []
        result = run_manifest_tests(manifest, project_root=tmp_path)
        assert (result.total, result.passed, result.failed) == (1, 1, 0)
        assert (tmp_path / "alpha-ran.txt").exists()
    else:
        assert [e.code for e in errors] == [
            ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
        ]
        assert not (tmp_path / "alpha-ran.txt").exists()


def test_malformed_native_file_is_judged_by_the_consumer_parser(tmp_path: Path) -> None:
    manifest = _project(tmp_path, fails=False)
    (tmp_path / "pytest.toml").write_text("[pytest\naddopts = broken\n")

    errors = _errors(tmp_path, manifest)

    if _NATIVE:
        assert [e.code for e in errors] == [
            ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
        ]
    else:
        assert errors == []
        result = run_manifest_tests(manifest, project_root=tmp_path)
        assert (result.total, result.passed, result.failed) == (1, 1, 0)


def test_native_proof_rejects_empty_collection_and_unsupported_commands(
    tmp_path: Path,
) -> None:
    from maid_runner.core._pytest_addopts_selection import (
        pytest_native_config_collection_error,
    )

    manifest = _project(tmp_path, addopts=[])
    (tmp_path / _TEST).write_text("# no test cases\n")

    assert (
        pytest_native_config_collection_error(
            tmp_path, load_manifest(manifest).validate_commands[0]
        )
        is not None
    )
    assert (
        pytest_native_config_collection_error(tmp_path, ["python", "-c", "pass"])
        is not None
    )


def test_native_candidate_forces_wrapped_pytest_to_fail_closed(tmp_path: Path) -> None:
    manifest = _project(tmp_path)
    data = yaml.safe_load(manifest.read_text())
    data["validate"][0] = ["sh", "-c", f"python -m pytest {_TEST} -q"]
    manifest.write_text(yaml.safe_dump(data))

    assert [e.code for e in _errors(tmp_path, manifest)] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]
    assert not (tmp_path / "alpha-ran.txt").exists()


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX alternate-interpreter launcher fixture"
)
@pytest.mark.parametrize("version", ["8.4.2", "9.0.2"])
def test_consumer_interpreter_version_is_independent_of_host(
    tmp_path: Path, version: str
) -> None:
    manifest = _project(tmp_path)
    (tmp_path / "bin").mkdir()
    launcher = tmp_path / "bin/pytest"
    launcher.write_text(
        f"#!{sys.executable}\nimport os, sys\n"
        f"os.execvp('uv', ['uv', 'run', '--with', 'pytest=={version}', 'python', '-m', 'pytest', *sys.argv[1:]])\n"
    )
    launcher.chmod(0o755)
    version_probe = subprocess.run(
        [str(launcher), "--version"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert version_probe.returncode == 0
    assert f"pytest {version}" in version_probe.stdout
    data = yaml.safe_load(manifest.read_text())
    data["validate"][0] = ["./bin/pytest", _TEST, "-q"]
    manifest.write_text(yaml.safe_dump(data))

    errors = _errors(tmp_path, manifest)

    if version.startswith("9."):
        assert [e.code for e in errors] == [
            ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
        ]
        assert not (tmp_path / "alpha-ran.txt").exists()
    else:
        assert errors == []
        result = run_manifest_tests(manifest, project_root=tmp_path)
        assert (result.total, result.passed, result.failed) == (1, 0, 1)
        assert (tmp_path / "alpha-ran.txt").exists()


@pytest.mark.parametrize(
    "config", ["pytest.toml", ".pytest.toml", "pyproject.toml", "custom.toml"]
)
def test_cwd_changing_shell_cannot_hide_relative_native_config(
    tmp_path: Path, config: str
) -> None:
    from maid_runner.core._pytest_config_addopts import (
        requires_native_pytest_config_check,
    )

    nested = tmp_path / "sub"
    nested_manifest = _project(nested, config)
    data = yaml.safe_load(nested_manifest.read_text())
    data["files"]["scope"][0]["path"] = "sub/policy.py"
    data["files"]["read"] = ["sub/" + _TEST]
    command = ["sh", "-c", f"cd sub && python -m pytest -c {config} {_TEST} -q"]
    data["validate"] = [command]
    manifest = tmp_path / "wrapped.manifest.yaml"
    manifest.write_text(yaml.safe_dump(data))

    assert requires_native_pytest_config_check(tmp_path, command, ["sub/" + _TEST])
    assert [error.code for error in _errors(tmp_path, manifest)] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]
    assert run_manifest_tests(manifest, project_root=tmp_path).total == 0
    assert not (nested / "alpha-ran.txt").exists()
