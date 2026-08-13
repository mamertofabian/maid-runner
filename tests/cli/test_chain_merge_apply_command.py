"""Behavioral test for `maid chain merge <file> --apply` (chain-merge child 4)."""

from __future__ import annotations

import json

CODE_FULL = "def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n\n\ndef gamma():\n    return 3\n"

FRAG_A = """schema: "2"
goal: "frag a"
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

FRAG_B = """schema: "2"
goal: "frag b"
type: feature
files:
  edit:
    - path: src/foo.py
      artifacts:
        - kind: function
          name: beta
        - kind: function
          name: gamma
validate:
  - pytest
created: "2026-02-01T00:00:00Z"
"""


def test_chain_merge_apply_json_writes_snapshot(tmp_path, capsys, monkeypatch):
    from maid_runner.cli.commands._main import main

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text(CODE_FULL)
    md = tmp_path / "manifests"
    md.mkdir()
    (md / "frag-a.manifest.yaml").write_text(FRAG_A)
    (md / "frag-b.manifest.yaml").write_text(FRAG_B)
    monkeypatch.chdir(tmp_path)

    rc = main(
        [
            "chain",
            "merge",
            "src/foo.py",
            "--apply",
            "--json",
            "--manifest-dir",
            "manifests",
        ]
    )
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["applied"] is True
    assert "snapshot_path" in payload
