"""Behavioral tests for per-file-scoped detection wiring (chain-merge child 3a).

SUT imported inside each test body.
"""

from __future__ import annotations

import json
from pathlib import Path


def _write_file_manifest(root: Path, rel_path: str, slug: str):
    from maid_runner.core.manifest import load_manifest

    (root / "src").mkdir(exist_ok=True)
    (root / "manifests").mkdir(exist_ok=True)
    (root / rel_path).write_text("def target() -> str:\n    return 'ok'\n")
    path = root / "manifests" / f"{slug}.manifest.yaml"
    path.write_text(
        'schema: "2"\n'
        f'goal: "{slug}"\n'
        "type: feature\n"
        'created: "2026-08-13T00:00:00Z"\n'
        "files:\n"
        "  edit:\n"
        f"    - path: {rel_path}\n"
        "      artifacts:\n"
        "        - kind: function\n"
        "          name: target\n"
        "          args: []\n"
        "          returns: str\n"
        "validate:\n"
        "  - python -m pytest -q\n"
    )
    return load_manifest(path)


def _warm_detection(root: Path, manifest, nodeids):
    from maid_runner.core._knockout_worker import KnockoutWorkerResult
    from maid_runner.core.knockout import (
        KnockoutDifferentialProof,
        KnockoutReport,
        KnockoutResult,
        _store_knockout_spec_cache,
        build_knockout_mutation_specs,
    )

    (spec,) = build_knockout_mutation_specs((manifest,), root)
    proof = KnockoutDifferentialProof(
        identity=spec.identity,
        command=("pytest",),
        baseline_exit_code=0,
        mutant_exit_code=1,
        restored_exit_code=0,
        detecting_nodeids=nodeids,
        used_exact_fallback=False,
        diagnostics=(),
    )
    result = KnockoutResult(
        artifact_name=spec.identity.artifact_name,
        artifact_kind=spec.identity.artifact_kind,
        parent_class=spec.identity.parent_class,
        file_path=spec.identity.file_path,
        detected=True,
        duration_ms=1.0,
        proof=proof,
    )
    worker = KnockoutWorkerResult(
        identity=spec.identity,
        reports={"cmd": KnockoutReport(results=(result,), errors=())},
        process_cost=1,
        errors=(),
    )
    _store_knockout_spec_cache(root, spec, worker)


def test_detection_source_for_file_scopes_to_that_file(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge_evidence import detection_source_for_file

    manifest_a = _write_file_manifest(tmp_path, "src/a.py", "a")
    _write_file_manifest(tmp_path, "src/b.py", "b")
    # Record detecting-nodeids for src/a.py's `target` only.
    a_nodeids = ("tests/test_a.py::test_a",)
    _warm_detection(tmp_path, manifest_a, a_nodeids)

    chain = ManifestChain(tmp_path / "manifests")

    source_a = detection_source_for_file(chain, "src/a.py", str(tmp_path))
    source_b = detection_source_for_file(chain, "src/b.py", str(tmp_path))

    # Both files declare `function:target`, but only src/a.py has evidence.
    assert source_a.detecting_nodeids_for("function:target") == a_nodeids
    assert source_b.detecting_nodeids_for("function:target") is None


def test_chain_merge_report_marks_detection_available(tmp_path, capsys, monkeypatch):
    from maid_runner.cli.commands._main import main

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text("def alpha():\n    return 1\n")
    md = tmp_path / "manifests"
    md.mkdir()
    (md / "foo.manifest.yaml").write_text(
        'schema: "2"\n'
        'goal: "foo"\n'
        "type: feature\n"
        'created: "2026-08-13T00:00:00Z"\n'
        "files:\n"
        "  edit:\n"
        "    - path: src/foo.py\n"
        "      artifacts:\n"
        "        - kind: function\n"
        "          name: alpha\n"
        "          args: []\n"
        "          returns: int\n"
        "validate:\n"
        "  - python -m pytest -q\n"
    )
    monkeypatch.chdir(tmp_path)

    rc = main(["chain", "merge", "src/foo.py", "--json", "--manifest-dir", "manifests"])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    # A real (per-file) source is now wired in, so detection is available even
    # though the cold cache leaves every artifact UNKNOWN.
    assert payload["acceptance"]["detection_available"] is True
