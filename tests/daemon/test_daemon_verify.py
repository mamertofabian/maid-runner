"""Behavioral tests for daemon verify requests."""

from __future__ import annotations

import json
import socket as socket_module
import threading
from pathlib import Path

import pytest

from maid_runner.daemon.handlers import configure_context
from maid_runner.daemon.protocol import DaemonRequestError
from maid_runner.daemon.server import Server


def _write_verify_project(project: Path, *, source: str | None = None) -> None:
    source_dir = project / "src"
    tests_dir = project / "tests"
    source_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)
    (project / "manifests").mkdir()
    if source is None:
        source = "def demo() -> str:\n    value = 'ok'\n    return value\n"
    (source_dir / "demo.py").write_text(source)
    (tests_dir / "test_demo.py").write_text(
        "from src.demo import demo\n\n\n"
        "def test_demo_returns_ok():\n"
        "    assert demo() == 'ok'\n"
    )
    (project / "manifests" / "demo.manifest.yaml").write_text(
        """schema: "2"
goal: verify demo
type: feature
files:
  create:
    - path: src/demo.py
      artifacts:
        - kind: function
          name: demo
          returns: str
    - path: tests/test_demo.py
      artifacts:
        - kind: test_function
          name: test_demo_returns_ok
validate:
  - python -c 'pass'
"""
    )


def _strip_duration_fields(value):
    if isinstance(value, dict):
        return {
            key: _strip_duration_fields(item)
            for key, item in value.items()
            if "duration" not in key
        }
    if isinstance(value, list):
        return [_strip_duration_fields(item) for item in value]
    return value


def _included_stages(payload: dict) -> dict:
    return {
        stage["name"]: _strip_duration_fields(stage)
        for stage in payload["stages"]
        if stage["name"]
        in {"schema", "behavioral", "implementation", "coherence", "file_tracking"}
    }


def _direct_verify_payload(
    project: Path,
    *,
    manifest_dir: str = "manifests/",
    allow_empty: bool = False,
) -> dict:
    from maid_runner.cli.commands._format import format_verify_result
    from maid_runner.cli.commands.verify import _run_verify

    result = _run_verify(
        manifest_dir=manifest_dir,
        project_root=project,
        allow_empty=allow_empty,
        check_assertions=True,
        check_stubs=True,
        require_changed_scope=False,
    )
    return json.loads(format_verify_result(result, json_mode=True))


def _read_one_response(conn: socket_module.socket, timeout: float = 5.0) -> dict:
    conn.settimeout(timeout)
    chunks: list[bytes] = []
    while True:
        chunk = conn.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        if b"\n" in chunk:
            break
    data = b"".join(chunks)
    return json.loads(data.split(b"\n", 1)[0].decode("utf-8"))


def test_handle_verify_reports_validation_coherence_file_tracking_and_skipped_tests(
    tmp_path,
):
    from maid_runner.daemon.handlers import handle_verify

    _write_verify_project(tmp_path)
    configure_context(tmp_path)

    payload = handle_verify({"manifest_dir": "manifests/"})

    stages = {stage["name"]: stage for stage in payload["stages"]}
    assert set(stages) == {
        "schema",
        "behavioral",
        "implementation",
        "coherence",
        "file_tracking",
        "tests",
    }
    assert stages["tests"]["success"] is True
    assert "skipped" in stages["tests"]["details"]["errors"][0].lower()


def test_handle_verify_matches_direct_verify_subset_json_excluding_durations(
    tmp_path,
):
    from maid_runner.daemon.handlers import handle_verify

    missing_artifact_project = tmp_path / "missing-artifact"
    missing_artifact_project.mkdir()
    _write_verify_project(
        missing_artifact_project, source="# missing declared artifact\n"
    )
    configure_context(missing_artifact_project)

    daemon_payload = handle_verify({"manifest_dir": "manifests/"})
    direct_payload = _direct_verify_payload(missing_artifact_project)

    assert _included_stages(daemon_payload) == _included_stages(direct_payload)
    assert [stage["name"] for stage in daemon_payload["stages"]] == [
        stage["name"] for stage in direct_payload["stages"]
    ]

    warning_project = tmp_path / "warning"
    warning_project.mkdir()
    _write_verify_project(
        warning_project,
        source="def demo() -> str:\n    pass\n",
    )
    configure_context(warning_project)

    daemon_payload = handle_verify({"manifest_dir": "manifests/"})
    direct_payload = _direct_verify_payload(warning_project)

    assert _included_stages(daemon_payload) == _included_stages(direct_payload)
    assert [stage["name"] for stage in daemon_payload["stages"]] == [
        stage["name"] for stage in direct_payload["stages"]
    ]
    assert daemon_payload["success"] is False

    empty_project = tmp_path / "empty"
    empty_project.mkdir()
    configure_context(empty_project)

    daemon_payload = handle_verify({"manifest_dir": "manifests/", "allow_empty": True})
    direct_payload = _direct_verify_payload(empty_project, allow_empty=True)

    assert _included_stages(daemon_payload) == _included_stages(direct_payload)
    assert [stage["name"] for stage in daemon_payload["stages"]] == [
        stage["name"] for stage in direct_payload["stages"]
    ]
    assert daemon_payload["success"] is True


def test_handle_verify_rejects_manifest_dir_path_escape(tmp_path):
    from maid_runner.daemon.handlers import handle_verify

    _write_verify_project(tmp_path)
    configure_context(tmp_path)

    with pytest.raises(DaemonRequestError) as exc:
        handle_verify({"manifest_dir": "../outside"})

    assert exc.value.code == "PATH_ESCAPE"


def test_handle_verify_ignores_client_supplied_project_root(tmp_path):
    from maid_runner.daemon.handlers import handle_verify

    good_project = tmp_path / "good"
    bad_project = tmp_path / "bad"
    good_project.mkdir()
    bad_project.mkdir()
    _write_verify_project(good_project)
    (bad_project / "manifests").mkdir()
    (bad_project / "manifests" / "bad.manifest.yaml").write_text("schema: '2'\n")
    configure_context(good_project)

    payload = handle_verify(
        {"manifest_dir": "manifests/", "project_root": str(bad_project)}
    )

    assert payload["success"] is True


def test_verify_request_round_trips_over_daemon_socket(tmp_path):
    _write_verify_project(tmp_path)
    configure_context(tmp_path)
    server = Server(tmp_path / "serve.sock", tmp_path / "serve.pid", client_timeout_s=1)

    server_side, client_side = socket_module.socketpair()
    server_side.settimeout(1.0)
    client_side.settimeout(1.0)

    worker = threading.Thread(target=server.handle_client, args=(server_side,))
    worker.start()
    try:
        client_side.sendall(
            b'{"id":"v1","method":"verify","params":{"manifest_dir":"manifests/"}}\n'
        )
        response = _read_one_response(client_side)
    finally:
        client_side.close()
        worker.join(timeout=2.0)
        server_side.close()

    assert response["id"] == "v1"
    assert response["ok"] is True
    stages = {stage["name"] for stage in response["result"]["stages"]}
    assert {
        "schema",
        "behavioral",
        "implementation",
        "coherence",
        "file_tracking",
        "tests",
    } <= stages
