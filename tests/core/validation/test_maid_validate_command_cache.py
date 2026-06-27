import json

from maid_runner.core._maid_validate_command_cache import (
    _parse_maid_validate_command,
    _run_cached_maid_validate_command,
)
from maid_runner.core.result import TestRunResult
from maid_runner.core.test_runner import run_tests
from maid_runner.core.types import TestStream, ValidationMode


def _write_valid_snapshot_project(tmp_path):
    manifests_dir = tmp_path / "manifests"
    src_dir = tmp_path / "src"
    manifests_dir.mkdir()
    src_dir.mkdir()
    (src_dir / "target.py").write_text("def target():\n    return None\n")
    manifest_path = manifests_dir / "target.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Target"
type: snapshot
files:
  snapshot:
    - path: src/target.py
      artifacts:
        - kind: function
          name: target
          args: []
          returns: "None"
validate:
  - echo target
"""
    )
    return manifest_path


def _write_missing_path_project(tmp_path):
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    manifest_path = manifests_dir / "target.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Target"
type: snapshot
files:
  snapshot:
    - path: src/missing.py
      artifacts:
        - kind: function
          name: target
          args: []
          returns: "None"
validate:
  - echo target
"""
    )
    return manifest_path


def test_parse_maid_validate_command_accepts_supported_flags():
    parsed = _parse_maid_validate_command(
        (
            "uv",
            "run",
            "maid",
            "validate",
            "contracts/target.manifest.yaml",
            "--mode",
            "behavioral",
            "--manifest-dir=contracts",
            "--json",
            "--no-chain",
        )
    )

    assert parsed == {
        "mode": ValidationMode.BEHAVIORAL,
        "manifest_dir": "contracts",
        "json_mode": True,
        "quiet": False,
        "use_chain": False,
        "manifest_path": "contracts/target.manifest.yaml",
    }


def test_parse_maid_validate_command_accepts_quiet_flag():
    parsed = _parse_maid_validate_command(
        (
            "uv",
            "run",
            "maid",
            "validate",
            "manifests/target.manifest.yaml",
            "--mode",
            "behavioral",
            "--quiet",
        )
    )

    assert parsed == {
        "mode": ValidationMode.BEHAVIORAL,
        "manifest_dir": "manifests/",
        "json_mode": False,
        "quiet": True,
        "use_chain": True,
        "manifest_path": "manifests/target.manifest.yaml",
    }


def test_parse_maid_validate_command_rejects_unsupported_shapes():
    assert _parse_maid_validate_command(()) is None
    assert _parse_maid_validate_command(("maid", "test")) is None
    assert _parse_maid_validate_command(("maid", "validate", "--mode")) is None
    assert _parse_maid_validate_command(("maid", "validate", "--mode", "bad")) is None
    assert _parse_maid_validate_command(("maid", "validate", "--unknown")) is None
    assert (
        _parse_maid_validate_command(
            ("maid", "validate", "a.manifest.yaml", "b.manifest.yaml")
        )
        is None
    )


def test_run_cached_maid_validate_command_returns_none_for_non_validate_command(
    tmp_path,
):
    result = _run_cached_maid_validate_command(
        ("pytest", "tests/test_a.py"),
        cwd=tmp_path,
        manifest_slug="target",
        stream=TestStream.IMPLEMENTATION,
        cache={},
    )

    assert result is None


def test_run_cached_maid_validate_command_preserves_quiet_success_output(tmp_path):
    _write_valid_snapshot_project(tmp_path)

    result = _run_cached_maid_validate_command(
        (
            "uv",
            "run",
            "maid",
            "validate",
            "manifests/target.manifest.yaml",
            "--mode",
            "schema",
            "--quiet",
        ),
        cwd=tmp_path,
        manifest_slug="target",
        stream=TestStream.IMPLEMENTATION,
        cache={},
    )

    assert result is not None
    assert result.success is True
    assert result.exit_code == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_run_cached_maid_validate_command_preserves_quiet_failure_output(tmp_path):
    _write_missing_path_project(tmp_path)

    result = _run_cached_maid_validate_command(
        (
            "uv",
            "run",
            "maid",
            "validate",
            "manifests/target.manifest.yaml",
            "--mode",
            "implementation",
            "--quiet",
        ),
        cwd=tmp_path,
        manifest_slug="target",
        stream=TestStream.IMPLEMENTATION,
        cache={},
    )

    assert result is not None
    assert result.success is False
    assert result.exit_code == 1
    assert "E306 File 'src/missing.py' not found" in result.stdout
    assert "FAIL target" not in result.stdout
    assert "Mode:" not in result.stdout
    assert result.stderr == ""


def test_run_cached_maid_validate_command_json_takes_precedence_over_quiet(tmp_path):
    _write_valid_snapshot_project(tmp_path)

    result = _run_cached_maid_validate_command(
        (
            "uv",
            "run",
            "maid",
            "validate",
            "manifests/target.manifest.yaml",
            "--mode",
            "schema",
            "--json",
            "--quiet",
        ),
        cwd=tmp_path,
        manifest_slug="target",
        stream=TestStream.IMPLEMENTATION,
        cache={},
    )

    assert result is not None
    assert result.success is True
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["manifest"] == "target"


def test_run_cached_maid_validate_command_preserves_quiet_batch_success_output(
    tmp_path,
):
    _write_valid_snapshot_project(tmp_path)

    result = _run_cached_maid_validate_command(
        ("uv", "run", "maid", "validate", "--mode", "schema", "--quiet"),
        cwd=tmp_path,
        manifest_slug="batch",
        stream=TestStream.IMPLEMENTATION,
        cache={},
    )

    assert result is not None
    assert result.success is True
    assert result.exit_code == 0
    assert result.stdout == "\n"
    assert result.stderr == ""


def test_run_tests_executes_quiet_maid_validate_commands_in_process(
    tmp_path, monkeypatch
):
    _write_valid_snapshot_project(tmp_path)

    def fail_on_subprocess_fallback(command, **kwargs):
        raise AssertionError(f"unexpected subprocess fallback: {command}")

    monkeypatch.setattr(
        "maid_runner.core.test_runner.run_command",
        fail_on_subprocess_fallback,
    )

    manifest_path = tmp_path / "manifests" / "target.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Target"
type: snapshot
files:
  snapshot:
    - path: src/target.py
      artifacts:
        - kind: function
          name: target
          args: []
          returns: "None"
validate:
  - uv run maid validate manifests/target.manifest.yaml --mode schema --quiet
"""
    )

    result = run_tests(
        manifest_dir="manifests/",
        project_root=tmp_path,
        batch=False,
    )

    assert result.success is True
    assert result.total == 1
    assert result.results[0].command == (
        "uv",
        "run",
        "maid",
        "validate",
        "manifests/target.manifest.yaml",
        "--mode",
        "schema",
        "--quiet",
    )
    assert result.results[0].stdout == ""


def test_run_tests_keeps_unsupported_validate_flags_on_subprocess_path(
    tmp_path, monkeypatch
):
    _write_valid_snapshot_project(tmp_path)
    manifest_path = tmp_path / "manifests" / "target.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Target"
type: snapshot
files:
  snapshot:
    - path: src/target.py
      artifacts:
        - kind: function
          name: target
          args: []
          returns: "None"
validate:
  - uv run maid validate manifests/target.manifest.yaml --unknown
"""
    )
    observed: list[tuple[str, ...]] = []

    def fake_run_command(command, **kwargs):
        observed.append(command)
        return TestRunResult(
            manifest_slug=kwargs.get("manifest_slug", ""),
            command=command,
            exit_code=0,
            stdout="fallback",
            stderr="",
            duration_ms=1.0,
            stream=kwargs.get("stream", TestStream.IMPLEMENTATION),
        )

    monkeypatch.setattr("maid_runner.core.test_runner.run_command", fake_run_command)

    result = run_tests(
        manifest_dir="manifests/",
        project_root=tmp_path,
        batch=False,
    )

    assert result.success is True
    assert observed == [
        (
            "uv",
            "run",
            "maid",
            "validate",
            "manifests/target.manifest.yaml",
            "--unknown",
        )
    ]
    assert result.results[0].stdout == "fallback"


def test_run_cached_maid_validate_command_validates_without_existing_chain_dir(
    tmp_path,
):
    contracts_dir = tmp_path / "contracts"
    src_dir = tmp_path / "src"
    contracts_dir.mkdir()
    src_dir.mkdir()
    (src_dir / "target.py").write_text("def target():\n    return None\n")
    (contracts_dir / "target.manifest.yaml").write_text(
        """schema: "2"
goal: "Target"
type: snapshot
files:
  snapshot:
    - path: src/target.py
      artifacts:
        - kind: function
          name: target
          args: []
          returns: "None"
validate:
  - echo target
"""
    )

    cache: dict[str, object] = {}
    result = _run_cached_maid_validate_command(
        (
            "uv",
            "run",
            "maid",
            "validate",
            "contracts/target.manifest.yaml",
            "--manifest-dir",
            "missing-manifests",
        ),
        cwd=tmp_path,
        manifest_slug="driver",
        stream=TestStream.IMPLEMENTATION,
        cache=cache,
    )

    assert result is not None
    assert result.success is True
    assert result.command == (
        "uv",
        "run",
        "maid",
        "validate",
        "contracts/target.manifest.yaml",
        "--manifest-dir",
        "missing-manifests",
    )
    assert "engine" in cache
    assert "chain:missing-manifests" not in cache


def test_run_cached_maid_validate_command_reuses_engine_and_chain_cache(
    tmp_path, monkeypatch
):
    from maid_runner.core import chain as chain_module

    manifests_dir = tmp_path / "manifests"
    src_dir = tmp_path / "src"
    manifests_dir.mkdir()
    src_dir.mkdir()
    (src_dir / "target.py").write_text("def target():\n    return None\n")
    (manifests_dir / "target.manifest.yaml").write_text(
        """schema: "2"
goal: "Target"
type: snapshot
files:
  snapshot:
    - path: src/target.py
      artifacts:
        - kind: function
          name: target
          args: []
          returns: "None"
validate:
  - echo target
"""
    )

    cache: dict[str, object] = {}
    constructed = 0
    original_chain = chain_module.ManifestChain

    class CountingManifestChain(original_chain):
        def __init__(self, *args, **kwargs):
            nonlocal constructed
            constructed += 1
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(chain_module, "ManifestChain", CountingManifestChain)

    first = _run_cached_maid_validate_command(
        ("uv", "run", "maid", "validate", "manifests/target.manifest.yaml"),
        cwd=tmp_path,
        manifest_slug="first",
        stream=TestStream.IMPLEMENTATION,
        cache=cache,
    )
    engine = cache.get("engine")
    second = _run_cached_maid_validate_command(
        ("uv", "run", "maid", "validate", "manifests/target.manifest.yaml"),
        cwd=tmp_path,
        manifest_slug="second",
        stream=TestStream.IMPLEMENTATION,
        cache=cache,
    )

    assert first is not None
    assert second is not None
    assert first.success is True
    assert second.success is True
    assert cache.get("engine") is engine
    assert "chain:manifests/" not in cache
    assert constructed == 2


def test_run_cached_maid_validate_command_clears_manifest_chain_between_direct_calls(
    tmp_path, monkeypatch
):
    from maid_runner.core import chain as chain_module

    manifests_dir = tmp_path / "manifests"
    src_dir = tmp_path / "src"
    manifests_dir.mkdir()
    src_dir.mkdir()
    (src_dir / "target.py").write_text("def target():\n    return None\n")
    (manifests_dir / "target.manifest.yaml").write_text(
        """schema: "2"
goal: "Target"
type: snapshot
files:
  snapshot:
    - path: src/target.py
      artifacts:
        - kind: function
          name: target
          args: []
          returns: "None"
validate:
  - echo target
"""
    )

    cache: dict[str, object] = {}
    constructed = 0
    original_chain = chain_module.ManifestChain

    class CountingManifestChain(original_chain):
        def __init__(self, *args, **kwargs):
            nonlocal constructed
            constructed += 1
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(chain_module, "ManifestChain", CountingManifestChain)

    for slug in ("first", "second"):
        result = _run_cached_maid_validate_command(
            ("uv", "run", "maid", "validate", "manifests/target.manifest.yaml"),
            cwd=tmp_path,
            manifest_slug=slug,
            stream=TestStream.IMPLEMENTATION,
            cache=cache,
        )
        assert result is not None
        assert result.success is True

    assert "engine" in cache
    assert "chain:manifests/" not in cache
    assert constructed == 2
