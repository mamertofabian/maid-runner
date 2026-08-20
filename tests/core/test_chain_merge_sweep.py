"""Behavioral tests for maid_runner.core.chain_merge_sweep (chain-merge child 6).

The SUT is imported inside each test body so a missing module fails the test
(exit 1) rather than the collection (exit 2).
"""

from __future__ import annotations


def _manifests_dir(tmp_path):
    d = tmp_path / "manifests"
    d.mkdir()
    return d


def _manifest(goal, mode, path, names, created):
    arts = "\n".join(f"        - kind: function\n          name: {n}" for n in names)
    return (
        f'schema: "2"\n'
        f'goal: "{goal}"\n'
        f"type: feature\n"
        f"files:\n"
        f"  {mode}:\n"
        f"    - path: {path}\n"
        f"      artifacts:\n"
        f"{arts}\n"
        f"validate:\n"
        f"  - pytest\n"
        f'created: "{created}"\n'
    )


def _mixed_repo(tmp_path):
    """A repo with one LEAN file and two DEFRAG files of differing redundancy."""
    d = _manifests_dir(tmp_path)
    # LEAN: single manifest, no re-declaration.
    (d / "lean.manifest.yaml").write_text(
        _manifest(
            "lean", "create", "src/lean.py", ["alpha", "beta"], "2026-01-01T00:00:00Z"
        )
    )
    # DEFRAG src/frag.py: redundant = 1 (beta re-declared).
    (d / "frag_a.manifest.yaml").write_text(
        _manifest(
            "frag a", "create", "src/frag.py", ["alpha", "beta"], "2026-01-01T00:00:00Z"
        )
    )
    (d / "frag_b.manifest.yaml").write_text(
        _manifest(
            "frag b", "edit", "src/frag.py", ["beta", "gamma"], "2026-02-01T00:00:00Z"
        )
    )
    # DEFRAG src/frag2.py: redundant = 2 (a, b re-declared).
    (d / "frag2_a.manifest.yaml").write_text(
        _manifest(
            "frag2 a", "create", "src/frag2.py", ["a", "b", "c"], "2026-01-01T00:00:00Z"
        )
    )
    (d / "frag2_b.manifest.yaml").write_text(
        _manifest(
            "frag2 b", "edit", "src/frag2.py", ["a", "b", "d"], "2026-02-01T00:00:00Z"
        )
    )
    return d


def test_sweep_counts_defrag_and_lean_verdicts(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge_sweep import (
        ChainMergeSweepSummary,
        build_repo_merge_summary,
    )

    chain = ManifestChain(_mixed_repo(tmp_path))

    summary = build_repo_merge_summary(chain)

    assert isinstance(summary, ChainMergeSweepSummary)
    assert summary.defrag_count == 2
    assert summary.lean_count == 1
    assert summary.blocked_count == 0


def test_sweep_worst_offenders_ranked_by_redundancy(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge_sweep import build_repo_merge_summary

    chain = ManifestChain(_mixed_repo(tmp_path))

    summary = build_repo_merge_summary(chain)

    # frag2 (redundant=2) ranks ahead of frag (redundant=1); lean is excluded.
    assert summary.worst_offenders == ("src/frag2.py", "src/frag.py")


def test_sweep_swept_file_count_matches_writable_files(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge_sweep import build_repo_merge_summary

    chain = ManifestChain(_mixed_repo(tmp_path))

    summary = build_repo_merge_summary(chain)

    assert summary.swept_file_count == 3


def test_sweep_is_deterministic(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge_sweep import build_repo_merge_summary

    chain = ManifestChain(_mixed_repo(tmp_path))

    assert build_repo_merge_summary(chain) == build_repo_merge_summary(chain)
