"""Behavioral tests for `maid chain merge --all` (chain-merge child 6)."""

from __future__ import annotations

import json


_FRAG_A = """schema: "2"
goal: "frag a"
type: feature
files:
  create:
    - path: src/frag.py
      artifacts:
        - kind: function
          name: alpha
        - kind: function
          name: beta
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
"""

_FRAG_B = """schema: "2"
goal: "frag b"
type: feature
files:
  edit:
    - path: src/frag.py
      artifacts:
        - kind: function
          name: beta
        - kind: function
          name: gamma
validate:
  - pytest
created: "2026-02-01T00:00:00Z"
"""


def _project(tmp_path):
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    (manifests / "frag_a.manifest.yaml").write_text(_FRAG_A)
    (manifests / "frag_b.manifest.yaml").write_text(_FRAG_B)
    return manifests


def test_chain_merge_all_json_emits_summary(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    manifests = _project(tmp_path)

    rc = main(["chain", "merge", "--all", "--json", "--manifest-dir", str(manifests)])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["defrag_count"] == 1
    assert payload["swept_file_count"] == 1
    assert "worst_offenders" in payload


def test_chain_merge_all_is_read_only(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    manifests = _project(tmp_path)
    before = {p.name: p.read_bytes() for p in manifests.iterdir()}

    rc = main(["chain", "merge", "--all", "--manifest-dir", str(manifests)])
    assert rc == 0

    after = {p.name: p.read_bytes() for p in manifests.iterdir()}
    assert after == before
