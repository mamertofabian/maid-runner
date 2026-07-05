"""Behavioral tests for pytest project-config addopts integrity checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from maid_runner.core import _pytest_config_addopts as pytest_config
from maid_runner.core._validation_test_artifacts import validate_manifest_test_commands
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode
from maid_runner.core.test_runner import run_manifest_tests


PYTEST_COMMAND = ("python", "-m", "pytest", "tests", "-q")


def _pytest_config_addopts_args(
    project_root: Path,
    command: tuple[str, ...],
) -> tuple[str, ...]:
    try:
        helper = pytest_config.pytest_config_addopts_args
    except AttributeError:
        helper = pytest_config.pyproject_pytest_addopts_args
    return helper(project_root, command)


def _pytest_config_addopts_errors(
    project_root: Path,
    command: tuple[str, ...],
) -> tuple[str, ...]:
    try:
        helper = pytest_config.pytest_config_addopts_errors
    except AttributeError:
        helper = pytest_config.pyproject_pytest_addopts_errors
    return helper(project_root, command)


def _write_behavioral_project(
    project_root: Path,
    slug: str,
    *,
    validate_command: str = "python -m pytest tests -q",
) -> Path:
    manifests_dir = project_root / "manifests"
    manifests_dir.mkdir()
    src_dir = project_root / "src"
    src_dir.mkdir()
    tests_dir = project_root / "tests"
    tests_dir.mkdir()

    (src_dir / "gate.py").write_text("def gate() -> str:\n    return 'ok'\n")
    (tests_dir / "test_gate.py").write_text(
        "from src.gate import gate\n\n"
        "def test_declared_behavior():\n"
        "    assert gate() == 'not ok'\n\n"
        "def test_other():\n"
        "    assert gate() == 'ok'\n"
    )
    manifest_path = manifests_dir / f"{slug}.manifest.yaml"
    manifest_path.write_text(
        f"""schema: "2"
goal: "Reject pytest config addopts bypass"
type: fix
files:
  edit:
    - path: src/gate.py
      artifacts:
        - kind: function
          name: gate
  read:
    - tests/test_gate.py
validate:
  - {validate_command}
"""
    )
    return manifest_path


def _write_pyproject(project_root: Path, addopts_literal: str) -> None:
    (project_root / "pyproject.toml").write_text(
        f"[tool.pytest.ini_options]\naddopts = {addopts_literal}\n"
    )


def _write_pytest_ini(project_root: Path, addopts: str) -> None:
    (project_root / "pytest.ini").write_text(f"[pytest]\naddopts = {addopts}\n")


def _write_tox_ini(project_root: Path, addopts: str) -> None:
    (project_root / "tox.ini").write_text(f"[pytest]\naddopts = {addopts}\n")


def _write_setup_cfg(project_root: Path, addopts: str) -> None:
    (project_root / "setup.cfg").write_text(f"[tool:pytest]\naddopts = {addopts}\n")


def _assert_rejected_by_config(
    project_root: Path,
    manifest_path: Path,
    *,
    config_name: str,
    addopts: str,
) -> None:
    result = run_manifest_tests(manifest_path, project_root=project_root)

    assert result.success is False
    assert result.total == 0
    assert [error.code for error in result.chain_errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]
    assert config_name in result.chain_errors[0].message
    assert addopts in result.chain_errors[0].message
    return result


def test_run_manifest_tests_rejects_pytest_ini_selector_addopts(tmp_path):
    manifest_path = _write_behavioral_project(tmp_path, "pytest-ini-selector")
    _write_pytest_ini(tmp_path, "-k test_other")

    result = _assert_rejected_by_config(
        tmp_path,
        manifest_path,
        config_name="pytest.ini",
        addopts="-k test_other",
    )
    assert result.chain_errors


def test_run_manifest_tests_rejects_tox_ini_collect_only_addopts(tmp_path):
    manifest_path = _write_behavioral_project(tmp_path, "tox-ini-collect-only")
    _write_tox_ini(tmp_path, "--collect-only")

    result = _assert_rejected_by_config(
        tmp_path,
        manifest_path,
        config_name="tox.ini",
        addopts="--collect-only",
    )
    assert result.chain_errors


def test_run_manifest_tests_rejects_setup_cfg_selector_addopts(tmp_path):
    manifest_path = _write_behavioral_project(tmp_path, "setup-cfg-selector")
    _write_setup_cfg(tmp_path, "-k test_other")

    result = _assert_rejected_by_config(
        tmp_path,
        manifest_path,
        config_name="setup.cfg",
        addopts="-k test_other",
    )
    assert result.chain_errors


@pytest.mark.parametrize(
    ("case_name", "write_configs", "expected"),
    [
        (
            "pytest_ini_over_pyproject",
            lambda root: (
                _write_pytest_ini(root, "-q"),
                _write_pyproject(root, '"-k test_other"'),
            ),
            ("-q",),
        ),
        (
            "pyproject_over_tox_ini",
            lambda root: (
                _write_pyproject(root, '"-q"'),
                _write_tox_ini(root, "-k test_other"),
            ),
            ("-q",),
        ),
        (
            "tox_ini_over_setup_cfg",
            lambda root: (
                _write_tox_ini(root, "-q"),
                _write_setup_cfg(root, "-k test_other"),
            ),
            ("-q",),
        ),
    ],
)
def test_pytest_config_addopts_uses_pytest_precedence(
    tmp_path,
    case_name,
    write_configs,
    expected,
):
    project_root = tmp_path / case_name
    project_root.mkdir()
    write_configs(project_root)

    assert _pytest_config_addopts_errors(project_root, PYTEST_COMMAND) == ()
    assert _pytest_config_addopts_args(project_root, PYTEST_COMMAND) == expected


def test_pytest_config_addopts_skips_ini_files_without_pytest_sections(tmp_path):
    falls_through_to_setup = tmp_path / "falls-through-to-setup"
    falls_through_to_setup.mkdir()
    (falls_through_to_setup / "tox.ini").write_text("[tox]\nenvlist = py\n")
    _write_setup_cfg(falls_through_to_setup, "--collect-only")

    no_effective_config = tmp_path / "no-effective-config"
    no_effective_config.mkdir()
    (no_effective_config / "setup.cfg").write_text("[metadata]\nname = demo\n")

    assert _pytest_config_addopts_args(
        falls_through_to_setup,
        PYTEST_COMMAND,
    ) == ("--collect-only",)
    assert _pytest_config_addopts_args(no_effective_config, PYTEST_COMMAND) == ()


@pytest.mark.parametrize(
    ("case_name", "write_config"),
    [
        ("pytest_ini", _write_pytest_ini),
        ("pyproject", lambda root, addopts: _write_pyproject(root, f'"{addopts}"')),
        ("tox_ini", _write_tox_ini),
        ("setup_cfg", _write_setup_cfg),
    ],
)
def test_run_manifest_tests_allows_benign_addopts_in_each_config_format(
    tmp_path,
    case_name,
    write_config,
):
    project_root = tmp_path / case_name
    project_root.mkdir()
    manifest_path = _write_behavioral_project(project_root, f"benign-{case_name}")
    write_config(project_root, "-q --disable-warnings")
    (project_root / "tests" / "test_gate.py").write_text(
        "from src.gate import gate\n\n"
        "def test_declared_behavior():\n"
        "    assert gate() == 'ok'\n"
    )

    result = run_manifest_tests(manifest_path, project_root=project_root)

    assert result.success is True
    assert result.chain_errors == []


@pytest.mark.parametrize(
    ("case_name", "filename", "contents", "expected_name"),
    [
        ("bad_pytest_ini", "pytest.ini", "[pytest\naddopts = -q\n", "pytest.ini"),
        (
            "bad_pyproject_addopts",
            "pyproject.toml",
            "[tool.pytest.ini_options]\naddopts = ['-q', 42]\n",
            "pyproject.toml",
        ),
        ("bad_tox_ini", "tox.ini", "[pytest\naddopts = -q\n", "tox.ini"),
        ("bad_setup_cfg", "setup.cfg", "[tool:pytest\naddopts = -q\n", "setup.cfg"),
    ],
)
def test_pytest_config_addopts_fails_closed_for_malformed_effective_config(
    tmp_path,
    case_name,
    filename,
    contents,
    expected_name,
):
    project_root = tmp_path / case_name
    project_root.mkdir()
    (project_root / filename).write_text(contents)

    errors = _pytest_config_addopts_errors(project_root, PYTEST_COMMAND)

    assert len(errors) == 1
    assert expected_name in errors[0]


def test_pytest_config_addopts_ignores_malformed_shadowed_config(tmp_path):
    _write_pytest_ini(tmp_path, "-q")
    (tmp_path / "tox.ini").write_text("[pytest\naddopts = -k test_other\n")

    assert _pytest_config_addopts_errors(tmp_path, PYTEST_COMMAND) == ()
    assert _pytest_config_addopts_args(tmp_path, PYTEST_COMMAND) == ("-q",)


def test_pytest_config_addopts_respects_explicit_config_file(tmp_path):
    _write_pyproject(tmp_path, '"-k test_other"')
    _write_pytest_ini(tmp_path, "-q")

    assert (
        _pytest_config_addopts_errors(
            tmp_path,
            ("python", "-m", "pytest", "-c", "pytest.ini", "tests", "-q"),
        )
        == ()
    )
    assert _pytest_config_addopts_args(
        tmp_path,
        ("python", "-m", "pytest", "-c", "pytest.ini", "tests", "-q"),
    ) == ("-q",)


def test_run_manifest_tests_rejects_explicit_custom_ini_selector_addopts(tmp_path):
    manifest_path = _write_behavioral_project(
        tmp_path,
        "explicit-custom-ini-selector",
        validate_command="python -m pytest -c custom.ini tests -q",
    )
    (tmp_path / "custom.ini").write_text("[pytest]\naddopts = -k test_other\n")

    result = _assert_rejected_by_config(
        tmp_path,
        manifest_path,
        config_name="custom.ini",
        addopts="-k test_other",
    )
    assert result.chain_errors


def test_run_manifest_tests_rejects_explicit_custom_toml_selector_addopts(tmp_path):
    manifest_path = _write_behavioral_project(
        tmp_path,
        "explicit-custom-toml-selector",
        validate_command="python -m pytest -c custom.toml tests -q",
    )
    (tmp_path / "custom.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "-k test_other"\n'
    )

    result = _assert_rejected_by_config(
        tmp_path,
        manifest_path,
        config_name="custom.toml",
        addopts="-k test_other",
    )
    assert result.chain_errors


def test_pytest_config_addopts_fails_closed_for_malformed_explicit_toml(tmp_path):
    (tmp_path / "custom.toml").write_text("[tool.pytest.ini_options\naddopts = '-q'\n")
    command = ("python", "-m", "pytest", "-c", "custom.toml", "tests", "-q")

    errors = _pytest_config_addopts_errors(tmp_path, command)

    assert len(errors) == 1
    assert "custom.toml" in errors[0]


def test_pytest_config_addopts_allows_literal_percent_in_ini_addopts(tmp_path):
    _write_pytest_ini(tmp_path, "-q --junit-xml=report-%p.xml")

    assert _pytest_config_addopts_errors(tmp_path, PYTEST_COMMAND) == ()
    assert _pytest_config_addopts_args(tmp_path, PYTEST_COMMAND) == (
        "-q",
        "--junit-xml=report-%p.xml",
    )


def test_pytest_config_addopts_respects_override_ini_addopts(tmp_path):
    _write_pytest_ini(tmp_path, "-k test_other")
    command = ("python", "-m", "pytest", "-o", "addopts=", "tests", "-q")

    assert _pytest_config_addopts_errors(tmp_path, command) == ()
    assert _pytest_config_addopts_args(tmp_path, command) == ()


def test_validate_manifest_test_commands_rejects_effective_pytest_config_addopts(
    tmp_path,
):
    manifest_path = _write_behavioral_project(
        tmp_path,
        "validate-command-effective-config",
    )
    _write_setup_cfg(tmp_path, "-k test_other")

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]
    assert "setup.cfg" in errors[0].message
    assert "-k test_other" in errors[0].message
