"""Behavioral contract for canonical snapshot creation timestamps."""

from __future__ import annotations

import re
from datetime import datetime, timezone


_UTC_Z_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def test_snapshot_generators_emit_canonical_utc_z_created_timestamps(tmp_path):
    from maid_runner.core.snapshot import generate_snapshot, generate_system_snapshot

    source = tmp_path / "src" / "target.py"
    source.parent.mkdir()
    source.write_text("def target() -> str:\n    return 'ok'\n")

    before = datetime.now(timezone.utc).replace(microsecond=0)
    single = generate_snapshot(source, project_root=tmp_path)

    manifests = tmp_path / "manifests"
    manifests.mkdir()
    (manifests / "target.manifest.yaml").write_text(
        """schema: "2"
goal: "Track target"
type: feature
files:
  edit:
    - path: src/target.py
      artifacts:
        - kind: function
          name: target
          args: []
          returns: str
validate:
  - pytest tests/test_target.py
created: "2026-01-01T00:00:00Z"
"""
    )
    populated_system = generate_system_snapshot(manifests, project_root=tmp_path)
    empty_system = generate_system_snapshot(
        tmp_path / "missing-manifests", project_root=tmp_path
    )
    after = datetime.now(timezone.utc).replace(microsecond=0)

    assert single.created is not None
    assert populated_system.created is not None
    assert empty_system.created is not None
    assert _UTC_Z_TIMESTAMP.fullmatch(single.created)
    assert _UTC_Z_TIMESTAMP.fullmatch(populated_system.created)
    assert _UTC_Z_TIMESTAMP.fullmatch(empty_system.created)
    emitted = [
        datetime.fromisoformat(created.replace("Z", "+00:00"))
        for created in (single.created, populated_system.created, empty_system.created)
    ]
    assert all(before <= created <= after for created in emitted)
