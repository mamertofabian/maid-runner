"""Behavioral tests for the `maid chain merge` CLI (chain-merge child 1).

The SUT entry point (``main``) is imported inside each test body.
"""

from __future__ import annotations

import json


_MANIFEST = """schema: "2"
goal: "A creates foo"
type: feature
files:
  create:
    - path: src/foo.py
      artifacts:
        - kind: function
          name: alpha
        - kind: function
          name: beta
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
"""


def _project(tmp_path):
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    (manifests / "a.manifest.yaml").write_text(_MANIFEST)
    return manifests


def test_chain_merge_dry_run_json_emits_report(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    manifests = _project(tmp_path)

    rc = main(
        [
            "chain",
            "merge",
            "src/foo.py",
            "--dry-run",
            "--json",
            "--manifest-dir",
            str(manifests),
        ]
    )
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["file_path"] == "src/foo.py"
    assert payload["verdict"] in {"defrag", "lean", "blocked"}
    assert "active_manifest_count" in payload
    assert "acceptance" in payload


def test_chain_merge_dry_run_is_read_only(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    manifests = _project(tmp_path)
    before = {p.name: p.read_bytes() for p in manifests.iterdir()}

    rc = main(
        [
            "chain",
            "merge",
            "src/foo.py",
            "--dry-run",
            "--manifest-dir",
            str(manifests),
        ]
    )
    assert rc == 0

    after = {p.name: p.read_bytes() for p in manifests.iterdir()}
    assert after == before
