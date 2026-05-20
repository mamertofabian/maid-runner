from maid_runner.core._pytest_command_normalization import (
    _has_non_combinable_pytest_options,
    _is_python_command,
    _looks_like_pytest_invocation,
    _normalize_pytest_command,
    _pytest_behavior_options,
)


def test_normalize_pytest_command_accepts_direct_and_python_module_forms():
    assert _normalize_pytest_command(
        ("pytest", "tests/test_a.py", "-v", "--tb=short")
    ) == (
        ("pytest",),
        ("tests/test_a.py",),
        ("-v", "--tb=short"),
    )
    assert _normalize_pytest_command(
        ("uv", "run", "python", "-m", "pytest", "tests/test_a.py", "-q")
    ) == (
        ("uv", "run", "python", "-m", "pytest"),
        ("tests/test_a.py",),
        ("-q",),
    )


def test_normalize_pytest_command_preserves_maxfail_value_option_pair():
    assert _normalize_pytest_command(
        ("python3.12", "-m", "pytest", "tests/test_a.py", "--maxfail", "2")
    ) == (
        ("python3.12", "-m", "pytest"),
        ("tests/test_a.py",),
        ("--maxfail", "2"),
    )


def test_normalize_pytest_command_rejects_unbatchable_shapes():
    assert _normalize_pytest_command(()) is None
    assert _normalize_pytest_command(("pytest", "-q")) is None
    assert _normalize_pytest_command(("pytest", "tests/test_a.py", "--maxfail")) is None
    assert (
        _normalize_pytest_command(("pytest", "tests/test_a.py", "--last-failed"))
        is None
    )
    assert _normalize_pytest_command(("py.test", "tests/test_a.py")) is None
    assert _normalize_pytest_command(("python", "-m", "unittest", "tests")) is None


def test_pytest_behavior_options_drop_only_verbosity_flags():
    assert _pytest_behavior_options(("-q", "--tb=short", "-vv", "--maxfail", "1")) == (
        "--tb=short",
        "--maxfail",
        "1",
    )


def test_non_combinable_pytest_options_include_stateful_or_fail_fast_flags():
    assert _has_non_combinable_pytest_options(("-x",)) is True
    assert _has_non_combinable_pytest_options(("--lf",)) is True
    assert _has_non_combinable_pytest_options(("--maxfail=1",)) is True
    assert _has_non_combinable_pytest_options(("--tb=short", "-q")) is False


def test_looks_like_pytest_invocation_accepts_unbatchable_pytest_aliases():
    assert _looks_like_pytest_invocation(("uv", "run", "py.test", "tests")) is True
    assert (
        _looks_like_pytest_invocation(("python3.11", "-m", "pytest", "tests")) is True
    )
    assert _looks_like_pytest_invocation(("npm", "test")) is False


def test_python_command_detection_preserves_uv_resolution_boundary():
    assert _is_python_command("pytest") is True
    assert _is_python_command("python3.12") is True
    assert _is_python_command("py.test") is True
    assert _is_python_command("uv") is False
    assert _is_python_command("npm") is False
