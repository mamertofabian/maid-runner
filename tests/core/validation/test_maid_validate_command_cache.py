from maid_runner.core._maid_validate_command_cache import (
    _parse_maid_validate_command,
    _run_cached_maid_validate_command,
)
from maid_runner.core.types import TestStream, ValidationMode


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
        "use_chain": False,
        "manifest_path": "contracts/target.manifest.yaml",
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


def test_run_cached_maid_validate_command_reuses_engine_and_chain_cache(tmp_path):
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

    first = _run_cached_maid_validate_command(
        ("uv", "run", "maid", "validate", "manifests/target.manifest.yaml"),
        cwd=tmp_path,
        manifest_slug="first",
        stream=TestStream.IMPLEMENTATION,
        cache=cache,
    )
    engine = cache.get("engine")
    chain = cache.get("chain:manifests/")
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
    assert cache.get("chain:manifests/") is chain
