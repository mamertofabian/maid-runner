from __future__ import annotations

from pathlib import Path

from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode, TestRunResult
from maid_runner.core.types import TestStream


def test_rewrite_artifact_body_replaces_supported_python_artifacts() -> None:
    from maid_runner.core.knockout import rewrite_artifact_body

    source = '''
def plain(value: str) -> str:
    return value.upper()


class Service:
    def method(self) -> str:
        return "method"

    async def async_method(self) -> str:
        return "async"


@decorator("value")
def decorated() -> str:
    """keep signature and decorator only"""
    return "decorated"
'''.lstrip()

    rewritten_plain = rewrite_artifact_body(source, "plain", "function")
    rewritten_method = rewrite_artifact_body(
        source, "method", "method", parent_class="Service"
    )
    rewritten_async = rewrite_artifact_body(
        source, "async_method", "method", parent_class="Service"
    )
    rewritten_decorated = rewrite_artifact_body(source, "decorated", "function")

    assert (
        'def plain(value: str) -> str:\n    raise NotImplementedError("maid-knockout")'
        in rewritten_plain
    )
    assert (
        'def method(self) -> str:\n        raise NotImplementedError("maid-knockout")'
        in rewritten_method
    )
    assert (
        'async def async_method(self) -> str:\n        raise NotImplementedError("maid-knockout")'
        in rewritten_async
    )
    assert (
        '@decorator("value")\ndef decorated() -> str:\n    raise NotImplementedError("maid-knockout")'
        in rewritten_decorated
    )
    assert "return value.upper()" not in rewritten_plain
    assert 'return "method"' not in rewritten_method
    assert 'return "async"' not in rewritten_async
    assert 'return "decorated"' not in rewritten_decorated


def test_knockout_reports_e711_when_validate_commands_still_pass(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from maid_runner.core import knockout
    from maid_runner.core.knockout import KnockoutReport, KnockoutResult, run_knockout

    manifest_path = _write_project(
        tmp_path,
        source="""
def target() -> str:
    return "stub"
""",
        artifacts=[{"kind": "function", "name": "target"}],
    )
    monkeypatch.setattr(knockout, "changed_files", lambda root: ())
    monkeypatch.setattr(
        knockout,
        "_run_test_command",
        lambda *args, **kwargs: _test_result(args[0], exit_code=0),
    )

    report = run_knockout(load_manifest(manifest_path), tmp_path)

    explicit_result = KnockoutResult(
        artifact_name="target",
        artifact_kind="function",
        parent_class=None,
        file_path="src/target.py",
        detected=False,
        duration_ms=1.0,
    )
    explicit_report = KnockoutReport(results=(explicit_result,), errors=())
    assert report.success is False
    assert report.results[0].artifact_name == "target"
    assert report.results[0].artifact_kind == "function"
    assert report.results[0].parent_class is None
    assert report.results[0].file_path == "src/target.py"
    assert report.results[0].detected is False
    assert report.results[0].duration_ms >= 0
    assert report.errors[0].code == ErrorCode.ARTIFACT_KNOCKOUT_NOT_DETECTED
    assert explicit_report.to_dict()["results"][0]["detected"] is False


def test_knockout_detects_failure_and_restores_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from maid_runner.core import knockout
    from maid_runner.core.knockout import run_knockout

    manifest_path = _write_project(
        tmp_path,
        source="""
def target() -> str:
    return "honest"
""",
        artifacts=[{"kind": "function", "name": "target"}],
    )
    source_path = tmp_path / "src" / "target.py"
    original = source_path.read_text()
    monkeypatch.setattr(knockout, "changed_files", lambda root: ())
    monkeypatch.setattr(
        knockout,
        "_run_test_command",
        lambda *args, **kwargs: _test_result(args[0], exit_code=1),
    )

    report = run_knockout(load_manifest(manifest_path), tmp_path)

    assert report.success is True
    assert report.errors == ()
    assert report.results[0].detected is True
    assert source_path.read_text() == original


def test_knockout_restores_source_when_validate_run_raises(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from maid_runner.core import knockout
    from maid_runner.core.knockout import run_knockout

    manifest_path = _write_project(
        tmp_path,
        source="""
def target() -> str:
    return "restore"
""",
        artifacts=[{"kind": "function", "name": "target"}],
    )
    source_path = tmp_path / "src" / "target.py"
    original = source_path.read_text()
    monkeypatch.setattr(knockout, "changed_files", lambda root: ())

    def raise_during_validate(*args, **kwargs):
        raise RuntimeError("spawn failed")

    monkeypatch.setattr(knockout, "_run_test_command", raise_during_validate)

    report = run_knockout(load_manifest(manifest_path), tmp_path)

    assert source_path.read_text() == original
    assert report.success is False
    assert report.errors[0].code == ErrorCode.KNOCKOUT_HARNESS_FAILURE
    assert "spawn failed" in report.errors[0].message


def test_knockout_reports_restore_hash_mismatch_with_recovery_instruction(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from maid_runner.core import knockout
    from maid_runner.core.knockout import run_knockout

    manifest_path = _write_project(
        tmp_path,
        source="""
def target() -> str:
    return "restore"
""",
        artifacts=[{"kind": "function", "name": "target"}],
    )
    monkeypatch.setattr(knockout, "changed_files", lambda root: ())
    monkeypatch.setattr(
        knockout,
        "_run_test_command",
        lambda *args, **kwargs: _test_result(args[0], exit_code=1),
    )
    monkeypatch.setattr(
        knockout,
        "_restore_file",
        lambda path, content: path.write_text("corrupted\n"),
    )

    report = run_knockout(load_manifest(manifest_path), tmp_path)

    assert report.success is False
    assert report.errors[0].code == ErrorCode.KNOCKOUT_HARNESS_FAILURE
    assert "git checkout -- src/target.py" in report.errors[0].suggestion


def test_knockout_refuses_dirty_source_file_by_default(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from maid_runner.core import knockout
    from maid_runner.core.knockout import run_knockout

    manifest_path = _write_project(
        tmp_path,
        source="""
def target() -> str:
    return "dirty"
""",
        artifacts=[{"kind": "function", "name": "target"}],
    )
    monkeypatch.setattr(knockout, "changed_files", lambda root: ("src/target.py",))

    report = run_knockout(load_manifest(manifest_path), tmp_path)

    assert report.success is False
    assert report.results == ()
    assert report.errors[0].code == ErrorCode.KNOCKOUT_HARNESS_FAILURE
    assert "dirty" in report.errors[0].message


def test_knockout_refuses_normalized_equivalent_dirty_source_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from maid_runner.core import knockout
    from maid_runner.core.knockout import run_knockout

    manifest_path = _write_project(
        tmp_path,
        source="""
def target() -> str:
    return "dirty"
""",
        artifacts=[{"kind": "function", "name": "target"}],
        manifest_file_path="./src/target.py",
    )
    source_path = tmp_path / "src" / "target.py"
    original = source_path.read_text()
    monkeypatch.setattr(knockout, "changed_files", lambda root: ("src/target.py",))

    def fail_if_called(*args, **kwargs):
        raise AssertionError("dirty target should not be rewritten or validated")

    monkeypatch.setattr(knockout, "_run_test_command", fail_if_called)

    report = run_knockout(load_manifest(manifest_path), tmp_path)

    assert report.success is False
    assert report.results == ()
    assert report.errors[0].code == ErrorCode.KNOCKOUT_HARNESS_FAILURE
    assert source_path.read_text() == original


def test_knockout_allow_dirty_override_runs_validate_commands(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from maid_runner.core import knockout
    from maid_runner.core.knockout import run_knockout

    manifest_path = _write_project(
        tmp_path,
        source="""
def target() -> str:
    return "dirty override"
""",
        artifacts=[{"kind": "function", "name": "target"}],
    )
    calls = []
    monkeypatch.setattr(knockout, "changed_files", lambda root: ("src/target.py",))

    def record_validate(command, **kwargs):
        calls.append(command)
        return _test_result(command, exit_code=1)

    monkeypatch.setattr(knockout, "_run_test_command", record_validate)

    report = run_knockout(load_manifest(manifest_path), tmp_path, allow_dirty=True)

    assert report.success is True
    assert len(calls) == 1


def test_knockout_refuses_parent_relative_target_outside_project(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from maid_runner.core import knockout
    from maid_runner.core.knockout import run_knockout

    outside_path = tmp_path.parent / f"{tmp_path.name}-outside.py"
    outside_path.write_text(
        """
def target() -> str:
    return "outside"
""".lstrip()
    )
    try:
        manifest_path = _write_project(
            tmp_path,
            source="""
def target() -> str:
    return "inside"
""",
            artifacts=[{"kind": "function", "name": "target"}],
            manifest_file_path=f"../{outside_path.name}",
        )
        original = outside_path.read_text()
        monkeypatch.setattr(knockout, "changed_files", lambda root: ())

        def fail_if_called(*args, **kwargs):
            raise AssertionError("escaping target should not be validated")

        monkeypatch.setattr(knockout, "_run_test_command", fail_if_called)

        report = run_knockout(
            load_manifest(manifest_path),
            tmp_path,
            allow_dirty=True,
        )

        assert report.success is False
        assert report.results == ()
        assert report.errors[0].code == ErrorCode.KNOCKOUT_HARNESS_FAILURE
        assert "escapes the project root" in report.errors[0].message
        assert outside_path.read_text() == original
    finally:
        outside_path.unlink(missing_ok=True)


def test_knockout_refuses_symlink_target_resolving_outside_project(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from maid_runner.core import knockout
    from maid_runner.core.knockout import run_knockout

    outside_path = tmp_path.parent / f"{tmp_path.name}-symlink-outside.py"
    outside_path.write_text(
        """
def target() -> str:
    return "outside"
""".lstrip()
    )
    try:
        manifest_path = _write_project(
            tmp_path,
            source="""
def target() -> str:
    return "inside"
""",
            artifacts=[{"kind": "function", "name": "target"}],
        )
        target_path = tmp_path / "src" / "target.py"
        target_path.unlink()
        target_path.symlink_to(outside_path)
        original = outside_path.read_text()
        monkeypatch.setattr(knockout, "changed_files", lambda root: ())

        report = run_knockout(
            load_manifest(manifest_path),
            tmp_path,
            allow_dirty=True,
        )

        assert report.success is False
        assert report.results == ()
        assert report.errors[0].code == ErrorCode.KNOCKOUT_HARNESS_FAILURE
        assert "escapes the project root" in report.errors[0].message
        assert outside_path.read_text() == original
    finally:
        outside_path.unlink(missing_ok=True)


def test_knockout_runs_in_manifest_order_and_respects_limit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from maid_runner.core import knockout
    from maid_runner.core.knockout import run_knockout

    manifest_path = _write_project(
        tmp_path,
        source="""
def alpha() -> str:
    return "alpha"


def beta() -> str:
    return "beta"
""",
        artifacts=[
            {"kind": "function", "name": "alpha"},
            {"kind": "function", "name": "beta"},
        ],
    )
    source_path = tmp_path / "src" / "target.py"
    observed = []
    monkeypatch.setattr(knockout, "changed_files", lambda root: ())

    def record_knockout(command, **kwargs):
        source = source_path.read_text()
        if (
            'def alpha() -> str:\n    raise NotImplementedError("maid-knockout")'
            in source
        ):
            observed.append("alpha")
        if (
            'def beta() -> str:\n    raise NotImplementedError("maid-knockout")'
            in source
        ):
            observed.append("beta")
        return _test_result(command, exit_code=1)

    monkeypatch.setattr(knockout, "_run_test_command", record_knockout)

    report = run_knockout(load_manifest(manifest_path), tmp_path, limit=1)

    assert observed == ["alpha"]
    assert [result.artifact_name for result in report.results] == ["alpha"]


def test_knockout_rechecks_dirty_state_before_each_artifact_rewrite(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from maid_runner.core import knockout
    from maid_runner.core.knockout import run_knockout

    manifest_path = _write_two_file_project(tmp_path)
    second_path = tmp_path / "src" / "second.py"
    original_second = second_path.read_text()
    dirty_paths: list[str] = []
    monkeypatch.setattr(knockout, "changed_files", lambda root: tuple(dirty_paths))

    def dirty_second_after_first(command, **kwargs):
        dirty_paths.append("src/second.py")
        second_path.write_text(original_second + "\n# validate dirtied this file\n")
        return _test_result(command, exit_code=1)

    monkeypatch.setattr(knockout, "_run_test_command", dirty_second_after_first)

    report = run_knockout(load_manifest(manifest_path), tmp_path)

    assert [result.artifact_name for result in report.results] == ["first"]
    assert report.success is False
    assert report.errors[0].code == ErrorCode.KNOCKOUT_HARNESS_FAILURE
    assert "src/second.py" in report.errors[0].message
    assert 'raise NotImplementedError("maid-knockout")' not in second_path.read_text()


def test_knockout_targets_methods_in_manifest_order(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from maid_runner.core import knockout
    from maid_runner.core.knockout import run_knockout

    manifest_path = _write_project(
        tmp_path,
        source="""
class Service:
    def first(self) -> str:
        return "first"

    def second(self) -> str:
        return "second"
""",
        artifacts=[
            {"kind": "method", "name": "first", "of": "Service"},
            {"kind": "method", "name": "second", "of": "Service"},
        ],
    )
    source_path = tmp_path / "src" / "target.py"
    observed = []
    monkeypatch.setattr(knockout, "changed_files", lambda root: ())

    def record_knockout(command, **kwargs):
        source = source_path.read_text()
        if (
            'def first(self) -> str:\n        raise NotImplementedError("maid-knockout")'
            in source
        ):
            observed.append("Service.first")
        if (
            'def second(self) -> str:\n        raise NotImplementedError("maid-knockout")'
            in source
        ):
            observed.append("Service.second")
        return _test_result(command, exit_code=1)

    monkeypatch.setattr(knockout, "_run_test_command", record_knockout)

    report = run_knockout(load_manifest(manifest_path), tmp_path)

    assert observed == ["Service.first", "Service.second"]
    assert [result.parent_class for result in report.results] == ["Service", "Service"]


def _write_project(
    root: Path,
    *,
    source: str,
    artifacts: list[dict],
    manifest_file_path: str = "src/target.py",
) -> Path:
    src_dir = root / "src"
    tests_dir = root / "tests"
    manifests_dir = root / "manifests"
    src_dir.mkdir()
    tests_dir.mkdir()
    manifests_dir.mkdir()
    (src_dir / "__init__.py").write_text("")
    (src_dir / "target.py").write_text(source.lstrip())
    (tests_dir / "test_target.py").write_text(
        """
from src.target import target


def test_target():
    assert target is not None
""".lstrip()
    )
    manifest_path = manifests_dir / "target.manifest.yaml"
    manifest_path.write_text(_manifest_text(artifacts, file_path=manifest_file_path))
    return manifest_path


def _write_two_file_project(root: Path) -> Path:
    src_dir = root / "src"
    tests_dir = root / "tests"
    manifests_dir = root / "manifests"
    src_dir.mkdir()
    tests_dir.mkdir()
    manifests_dir.mkdir()
    (src_dir / "__init__.py").write_text("")
    (src_dir / "first.py").write_text(
        """
def first() -> str:
    return "first"
""".lstrip()
    )
    (src_dir / "second.py").write_text(
        """
def second() -> str:
    return "second"
""".lstrip()
    )
    (tests_dir / "test_target.py").write_text(
        "def test_placeholder():\n    assert True\n"
    )
    manifest_path = manifests_dir / "target.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Knock out two targets"
type: feature
created: "2026-06-10T00:00:00Z"
files:
  edit:
    - path: src/first.py
      artifacts:
        - kind: function
          name: first
    - path: src/second.py
      artifacts:
        - kind: function
          name: second
  read:
    - tests/test_target.py
validate:
  - python -m pytest -q tests/test_target.py
"""
    )
    return manifest_path


def _manifest_text(artifacts: list[dict], *, file_path: str = "src/target.py") -> str:
    artifact_lines = []
    for artifact in artifacts:
        artifact_lines.append(f"        - kind: {artifact['kind']}")
        artifact_lines.append(f"          name: {artifact['name']}")
        if "of" in artifact:
            artifact_lines.append(f"          of: {artifact['of']}")
    rendered_artifacts = "\n".join(artifact_lines)
    return f"""schema: "2"
goal: "Knock out target"
type: feature
created: "2026-06-10T00:00:00Z"
files:
  edit:
    - path: {file_path}
      artifacts:
{rendered_artifacts}
  read:
    - tests/test_target.py
validate:
  - python -m pytest -q tests/test_target.py
"""


def _test_result(command: tuple[str, ...], *, exit_code: int) -> TestRunResult:
    return TestRunResult(
        manifest_slug="target",
        command=command,
        exit_code=exit_code,
        stdout="",
        stderr="",
        duration_ms=1.0,
        stream=TestStream.IMPLEMENTATION,
    )
