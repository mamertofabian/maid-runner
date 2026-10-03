"""Configured pytest filters must preserve the complete selected test contract."""

import json
import os
from pathlib import Path
import sys

import pytest
import yaml

from maid_runner.core._validation_test_artifacts import validate_manifest_test_commands
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode
from maid_runner.core.test_runner import run_manifest_tests


_REPORTED_ADDOPTS = (
    "-ra --strict-markers -m 'not integration' --ignore=tests/strategies"
)


def _project(
    root: Path,
    addopts: str,
    *,
    config: str = "pyproject.toml",
    prefix: tuple[str, ...] | None = None,
    body_fails: bool = False,
) -> Path:
    (root / "tests/unit").mkdir(parents=True)
    (root / "tests/strategies").mkdir()
    (root / "tests/strategies/test_unrelated.py").write_text(
        "raise RuntimeError('unrelated tests must not be imported')\n"
    )
    (root / "tests/unit/test_policy.py").write_text(
        "from pathlib import Path\nimport pytest\n"
        "@pytest.fixture(autouse=True)\ndef runtime_fixture():\n"
        "    Path('fixture-ran.txt').write_text('fixture')\n"
        "def test_alpha():\n    Path('alpha-ran.txt').write_text('alpha')\n"
        f"    assert {not body_fails!r}\n"
        "def test_beta():\n    Path('beta-ran.txt').write_text('beta')\n"
        "    assert 2 + 2 == 4\n"
    )
    _config(root, config, addopts)
    command = [*(prefix or ("python", "-m", "pytest"))]
    if config == "custom.ini":
        command.extend(["-c", config])
    command.extend(["tests/unit/test_policy.py", "-q"])
    manifest = root / "policy.manifest.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "type": "fix",
                "created": "2026-09-28",
                "goal": "Verify policy behavior without excluding declared cases",
                "files": {
                    "scope": [{"path": "policy.py", "reason": "Policy wiring"}],
                    "read": ["tests/unit/test_policy.py"],
                },
                "validate": [command],
            }
        )
    )
    (root / "policy.py").write_text("value = 4\n")
    return manifest


def _config(root: Path, name: str, addopts: str) -> None:
    if name == "pyproject.toml":
        text = (
            "[tool.pytest.ini_options]\naddopts = "
            + json.dumps(addopts)
            + '\nmarkers = ["integration: external integration"]\n'
        )
    else:
        section = "tool:pytest" if name == "setup.cfg" else "pytest"
        text = f"[{section}]\naddopts = {addopts}\nmarkers = integration: external integration\n"
    (root / name).write_text(text)


def _errors(manifest: Path, root: Path):
    return validate_manifest_test_commands(load_manifest(manifest), root)


@pytest.mark.parametrize(
    "config", ["pyproject.toml", "pytest.ini", "tox.ini", "setup.cfg", "custom.ini"]
)
def test_harmless_reported_addopts_preserve_all_tests_and_config(
    tmp_path: Path, config: str
) -> None:
    manifest = _project(tmp_path, _REPORTED_ADDOPTS, config=config)
    original_config = (tmp_path / config).read_bytes()

    errors = _errors(manifest, tmp_path)

    assert errors == []
    assert not (tmp_path / "fixture-ran.txt").exists()
    assert not (tmp_path / "alpha-ran.txt").exists()
    assert not (tmp_path / "beta-ran.txt").exists()
    result = run_manifest_tests(manifest, project_root=tmp_path)
    assert (result.total, result.passed, result.failed) == (1, 1, 0)
    assert (tmp_path / "alpha-ran.txt").read_text() == "alpha"
    assert (tmp_path / "beta-ran.txt").read_text() == "beta"
    assert (tmp_path / config).read_bytes() == original_config


def test_public_collection_proof_uses_original_uv_command(tmp_path: Path) -> None:
    from maid_runner.core._pytest_addopts_selection import (
        pytest_addopts_collection_error,
    )

    manifest = _project(tmp_path, _REPORTED_ADDOPTS, prefix=("uv", "run", "pytest"))
    command = load_manifest(manifest).validate_commands[0]

    assert pytest_addopts_collection_error(tmp_path, command) is None
    assert _errors(manifest, tmp_path) == []
    assert not (tmp_path / "fixture-ran.txt").exists()


@pytest.mark.parametrize(
    "addopts",
    [
        "-m 'not integration'",
        "-k alpha",
        "--deselect=tests/unit/test_policy.py::test_beta",
    ],
)
def test_selectors_that_omit_a_declared_case_are_rejected(
    tmp_path: Path, addopts: str
) -> None:
    manifest = _project(tmp_path, addopts)
    test = tmp_path / "tests/unit/test_policy.py"
    test.write_text(
        test.read_text().replace(
            "def test_beta():", "@pytest.mark.integration\ndef test_beta():"
        )
    )

    errors = _errors(manifest, tmp_path)

    assert [e.code for e in errors] == [ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS]
    assert "pyproject.toml" in errors[0].message
    assert "collection" in errors[0].message.lower()
    result = run_manifest_tests(manifest, project_root=tmp_path)
    assert result.total == 0
    assert not (tmp_path / "fixture-ran.txt").exists()


def test_parametrized_case_selection_is_checked_by_native_pytest(
    tmp_path: Path,
) -> None:
    manifest = _project(tmp_path, "-m 'not integration'")
    (tmp_path / "tests/unit/test_policy.py").write_text(
        "import pytest\n@pytest.mark.parametrize('value', [1, pytest.param(2, marks=pytest.mark.integration)])\n"
        "def test_policy(value):\n    assert value > 0\n"
    )

    errors = _errors(manifest, tmp_path)

    assert [e.code for e in errors] == [ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS]


def test_conftest_assigned_markers_cannot_hide_declared_cases(tmp_path: Path) -> None:
    manifest = _project(tmp_path, "-m 'not integration'")
    (tmp_path / "conftest.py").write_text(
        "import pytest\n@pytest.hookimpl(tryfirst=True)\ndef pytest_collection_modifyitems(items):\n"
        "    for item in items:\n        if item.name == 'test_beta':\n            item.add_marker(pytest.mark.integration)\n"
    )

    errors = _errors(manifest, tmp_path)

    assert [e.code for e in errors] == [ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS]


@pytest.mark.parametrize(
    "mode",
    [
        "--collect-only",
        "--collectonly",
        "--co",
        "--help",
        "--fixtures",
        "--setup-plan",
        "--unknown-plugin-option",
    ],
)
def test_nonexecuting_and_unsupported_syntax_does_not_trigger_collection(
    tmp_path: Path, mode: str
) -> None:
    manifest = _project(tmp_path, f"-m 'not integration' {mode}")
    test = tmp_path / "tests/unit/test_policy.py"
    test.write_text(
        "from pathlib import Path\nPath('imported.txt').touch()\n" + test.read_text()
    )

    errors = _errors(manifest, tmp_path)

    assert [e.code for e in errors] == [ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS]
    assert not (tmp_path / "imported.txt").exists()
    assert not (tmp_path / "fixture-ran.txt").exists()


def test_failing_test_is_executed_instead_of_blocked_as_nonexecuting(
    tmp_path: Path,
) -> None:
    manifest = _project(tmp_path, _REPORTED_ADDOPTS, body_fails=True)

    result = run_manifest_tests(manifest, project_root=tmp_path)

    assert result.chain_errors == []
    assert (result.total, result.passed, result.failed) == (1, 0, 1)
    assert (tmp_path / "alpha-ran.txt").exists()


def test_collection_failure_and_empty_collection_fail_closed(tmp_path: Path) -> None:
    from maid_runner.core._pytest_addopts_selection import (
        pytest_addopts_collection_error,
    )

    manifest = _project(tmp_path, _REPORTED_ADDOPTS)
    command = load_manifest(manifest).validate_commands[0]
    test = tmp_path / "tests/unit/test_policy.py"
    test.write_text(
        "raise RuntimeError('collection failed')\ndef test_policy():\n    assert True\n"
    )

    assert pytest_addopts_collection_error(tmp_path, command) is not None
    assert [e.code for e in _errors(manifest, tmp_path)] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]
    test.write_text("# no behavioral cases\n")
    assert pytest_addopts_collection_error(tmp_path, command) is not None


def test_selection_proof_is_not_reused_after_config_or_test_changes(
    tmp_path: Path,
) -> None:
    manifest = _project(tmp_path, _REPORTED_ADDOPTS)

    assert _errors(manifest, tmp_path) == []
    _config(tmp_path, "pyproject.toml", "-k alpha")
    assert [e.code for e in _errors(manifest, tmp_path)] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]
    _config(tmp_path, "pyproject.toml", _REPORTED_ADDOPTS)
    test = tmp_path / "tests/unit/test_policy.py"
    test.write_text(
        test.read_text().replace(
            "def test_beta():", "@pytest.mark.integration\ndef test_beta():"
        )
    )
    assert [e.code for e in _errors(manifest, tmp_path)] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_probes_use_the_same_clean_environment_as_test_execution(
    tmp_path: Path, monkeypatch
) -> None:
    manifest = _project(tmp_path, _REPORTED_ADDOPTS)
    monkeypatch.setenv("PYTEST_ADDOPTS", "--collect-only -k missing")
    monkeypatch.setenv("NODE_OPTIONS", "--test-name-pattern=missing")

    assert _errors(manifest, tmp_path) == []
    result = run_manifest_tests(manifest, project_root=tmp_path)
    assert (result.total, result.passed, result.failed) == (1, 1, 0)
    assert (tmp_path / "beta-ran.txt").exists()
    assert os.environ["PYTEST_ADDOPTS"] == "--collect-only -k missing"


def test_unsupported_command_options_do_not_gain_collection_proof(
    tmp_path: Path,
) -> None:
    manifest = _project(tmp_path, _REPORTED_ADDOPTS)
    data = yaml.safe_load(manifest.read_text())
    data["validate"][0].append("--collectonly")
    manifest.write_text(yaml.safe_dump(data))

    errors = _errors(manifest, tmp_path)

    assert [e.code for e in errors] == [ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS]
    assert not (tmp_path / "fixture-ran.txt").exists()


def test_missing_consumer_runner_cannot_fall_back_to_host_pytest(
    tmp_path: Path,
) -> None:
    from maid_runner.core._pytest_addopts_selection import (
        pytest_addopts_collection_error,
    )

    manifest = _project(
        tmp_path, _REPORTED_ADDOPTS, prefix=(str(tmp_path / "missing/pytest"),)
    )
    command = load_manifest(manifest).validate_commands[0]

    assert pytest_addopts_collection_error(tmp_path, command) is not None
    assert [e.code for e in _errors(manifest, tmp_path)] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]
    assert not (tmp_path / "fixture-ran.txt").exists()


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX executable fixture for the uv resolver boundary"
)
def test_proof_resolves_implicit_uv_runner_like_execution(
    tmp_path: Path, monkeypatch
) -> None:
    manifest = _project(tmp_path, _REPORTED_ADDOPTS)
    (tmp_path / "uv.lock").write_text("# uv-managed project marker\n")
    (tmp_path / "bin").mkdir()
    uv = tmp_path / "bin/uv"
    uv.write_text(
        f"#!{sys.executable}\n"
        + "import os, sys\n"
        + "assert sys.argv[1:3] == ['run', 'python']\n"
        + "os.environ['MAID_TEST_CONSUMER'] = 'resolved'\n"
        + "os.execv(sys.executable, [sys.executable, *sys.argv[3:]])\n"
    )
    uv.chmod(0o755)
    monkeypatch.setenv("PATH", str(uv.parent) + os.pathsep + os.environ["PATH"])
    (tmp_path / "conftest.py").write_text(
        "import os\nassert os.environ.get('MAID_TEST_CONSUMER') == 'resolved'\n"
    )

    assert _errors(manifest, tmp_path) == []
    result = run_manifest_tests(manifest, project_root=tmp_path, pytest_workers=1)
    assert (result.total, result.passed, result.failed) == (1, 1, 0)
    assert (tmp_path / "beta-ran.txt").exists()


@pytest.mark.parametrize(
    "case",
    ["nested-config", "argument-file", "duplicate-config", "config-argument-file"],
)
def test_ambiguous_native_configuration_cannot_disguise_collect_only(
    tmp_path: Path, case: str
) -> None:
    manifest = _project(tmp_path, _REPORTED_ADDOPTS)
    data = yaml.safe_load(manifest.read_text())
    if case == "nested-config":
        (tmp_path / "tests/unit/pytest.ini").write_text(
            "[pytest]\naddopts = --collect-only\n"
        )
    elif case == "argument-file":
        (tmp_path / "arguments.txt").write_text("--collect-only\n")
        data["validate"][0].append("@arguments.txt")
    elif case == "config-argument-file":
        (tmp_path / "arguments.txt").write_text("not integration\n--collect-only\n")
        _config(tmp_path, "pyproject.toml", "-m @arguments.txt")
    else:
        (tmp_path / "alternate.ini").write_text("[pytest]\naddopts = --collect-only\n")
        data["validate"][0].extend(["-c", "pyproject.toml", "-c", "alternate.ini"])
    manifest.write_text(yaml.safe_dump(data))

    errors = _errors(manifest, tmp_path)

    assert [e.code for e in errors] == [ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS]
    result = run_manifest_tests(manifest, project_root=tmp_path)
    assert result.total == 0
    assert not (tmp_path / "fixture-ran.txt").exists()


def test_explicit_config_choice_can_disambiguate_a_nested_configuration(
    tmp_path: Path,
) -> None:
    manifest = _project(tmp_path, _REPORTED_ADDOPTS)
    (tmp_path / "tests/unit/pytest.ini").write_text(
        "[pytest]\naddopts = --collect-only\n"
    )
    data = yaml.safe_load(manifest.read_text())
    data["validate"][0].extend(["-c", "pyproject.toml"])
    manifest.write_text(yaml.safe_dump(data))

    assert _errors(manifest, tmp_path) == []
    result = run_manifest_tests(manifest, project_root=tmp_path)
    assert (result.total, result.passed, result.failed) == (1, 1, 0)
    assert (tmp_path / "beta-ran.txt").exists()


def test_native_cfg_section_must_match_the_inspected_addopts(tmp_path: Path) -> None:
    manifest = _project(tmp_path, _REPORTED_ADDOPTS, body_fails=True)
    (tmp_path / "custom.cfg").write_text(
        '[pytest]\naddopts = -m "not integration"\n'
        "[tool:pytest]\naddopts = --collect-only\n"
    )
    data = yaml.safe_load(manifest.read_text())
    data["validate"][0].extend(["-c", "custom.cfg"])
    manifest.write_text(yaml.safe_dump(data))

    errors = _errors(manifest, tmp_path)

    assert [e.code for e in errors] == [ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS]
    assert run_manifest_tests(manifest, project_root=tmp_path).total == 0
    assert not (tmp_path / "fixture-ran.txt").exists()


def test_matching_native_cfg_sections_remain_eligible(tmp_path: Path) -> None:
    manifest = _project(tmp_path, _REPORTED_ADDOPTS)
    (tmp_path / "custom.cfg").write_text(
        '[pytest]\naddopts = -m "not integration"\n'
        '[tool:pytest]\naddopts = -m "not integration"\n'
    )
    data = yaml.safe_load(manifest.read_text())
    data["validate"][0].extend(["-c", "custom.cfg"])
    manifest.write_text(yaml.safe_dump(data))

    assert _errors(manifest, tmp_path) == []
    result = run_manifest_tests(manifest, project_root=tmp_path)
    assert (result.total, result.passed, result.failed) == (1, 1, 0)
    assert (tmp_path / "beta-ran.txt").exists()


@pytest.mark.skipif(
    int(pytest.__version__.split(".")[0]) < 9,
    reason="Native pytest.toml discovery requires pytest 9",
)
@pytest.mark.parametrize("name", ["pytest.toml", ".pytest.toml"])
def test_native_pytest9_config_cannot_hide_collect_only(
    tmp_path: Path, name: str
) -> None:
    manifest = _project(tmp_path, _REPORTED_ADDOPTS, body_fails=True)
    (tmp_path / name).write_text('[pytest]\naddopts = ["--collect-only"]\n')

    errors = _errors(manifest, tmp_path)

    assert [e.code for e in errors] == [ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS]
    assert run_manifest_tests(manifest, project_root=tmp_path).total == 0
    assert not (tmp_path / "fixture-ran.txt").exists()


@pytest.mark.parametrize("mode", ["missing", "malformed", "mismatched"])
def test_native_config_receipt_is_required_and_validated(
    tmp_path: Path, mode: str
) -> None:
    manifest = _project(tmp_path, _REPORTED_ADDOPTS)
    (tmp_path / "conftest.py").write_text(
        "import os\nfrom pathlib import Path\nimport pytest\n"
        "receipt = None\n"
        "@pytest.hookimpl(tryfirst=True)\n"
        "def pytest_configure(config):\n"
        "    global receipt\n"
        "    receipt = os.environ.get('MAID_ADDOPTS_PROOF_CONFIG')\n"
        + (
            "    os.environ.pop('MAID_ADDOPTS_PROOF_CONFIG', None)\n"
            if mode == "missing"
            else ""
        )
        + "def pytest_sessionfinish(session, exitstatus):\n"
        + (
            "    if receipt: Path(receipt).write_text('invalid JSON')\n"
            if mode == "malformed"
            else (
                "    if receipt:\n"
                "        import json\n"
                "        data = json.loads(Path(receipt).read_text())\n"
                "        data['addopts'] = ['--collect-only']\n"
                "        Path(receipt).write_text(json.dumps(data))\n"
                if mode == "mismatched"
                else "    pass\n"
            )
        )
    )

    errors = _errors(manifest, tmp_path)

    assert [e.code for e in errors] == [ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS]
    assert not (tmp_path / "fixture-ran.txt").exists()


def test_collect_only_specific_hooks_cannot_hide_runtime_deselection(
    tmp_path: Path,
) -> None:
    manifest = _project(tmp_path, "-m 'not integration'")
    test = tmp_path / "tests/unit/test_policy.py"
    test.write_text(
        test.read_text().replace(
            "def test_beta():", "@pytest.mark.integration\ndef test_beta():"
        )
    )
    (tmp_path / "conftest.py").write_text(
        "import pytest\n@pytest.hookimpl(tryfirst=True)\n"
        "def pytest_collection_modifyitems(config, items):\n"
        "    if config.option.collectonly: config.option.markexpr = ''\n"
    )

    errors = _errors(manifest, tmp_path)

    assert [e.code for e in errors] == [ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS]
    assert not (tmp_path / "fixture-ran.txt").exists()


def test_probe_stops_consumer_test_dispatch_before_fixtures(tmp_path: Path) -> None:
    manifest = _project(tmp_path, _REPORTED_ADDOPTS)
    (tmp_path / "conftest.py").write_text(
        "import pytest\nclass CustomLoop:\n"
        "    @pytest.hookimpl(tryfirst=True)\n"
        "    def pytest_runtestloop(self, session):\n"
        "        for item in session.items:\n"
        "            session.config.hook.pytest_runtest_protocol(item=item, nextitem=None)\n"
        "        return True\n"
        "def pytest_sessionstart(session):\n"
        "    session.config.pluginmanager.register(CustomLoop(), 'consumer-custom-loop')\n"
    )

    errors = _errors(manifest, tmp_path)

    assert [e.code for e in errors] == [ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS]
    assert not (tmp_path / "fixture-ran.txt").exists()
    assert not (tmp_path / "alpha-ran.txt").exists()
    assert not (tmp_path / "beta-ran.txt").exists()


def test_partial_collection_error_cannot_be_hidden_by_exit_status_override(
    tmp_path: Path,
) -> None:
    manifest = _project(tmp_path, _REPORTED_ADDOPTS)
    (tmp_path / "tests/unit/test_broken.py").write_text(
        "raise RuntimeError('partial collection failed')\ndef test_broken():\n    assert True\n"
    )
    (tmp_path / "conftest.py").write_text(
        "def pytest_sessionfinish(session):\n    session.exitstatus = 0\n"
    )
    data = yaml.safe_load(manifest.read_text())
    data["validate"][0] = ["python", "-m", "pytest", "tests/unit", "-q"]
    manifest.write_text(yaml.safe_dump(data))

    errors = _errors(manifest, tmp_path)

    assert [e.code for e in errors] == [ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS]
    assert "collection" in errors[0].message.lower()
    assert not (tmp_path / "fixture-ran.txt").exists()
    assert not (tmp_path / "alpha-ran.txt").exists()
