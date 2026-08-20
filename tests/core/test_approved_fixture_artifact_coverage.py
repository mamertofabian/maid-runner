"""Behavioral contract for approved fixture execution in derived coverage."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from maid_runner.core import artifact_coverage
from maid_runner.core.manifest import load_manifest
from maid_runner.core.runtime_evidence import collect_runtime_evidence


def test_derived_coverage_credits_digest_approved_session_fixture(
    tmp_path: Path,
) -> None:
    manifests = _write_project(tmp_path, approval="valid")

    run = collect_runtime_evidence(manifests, tmp_path, pytest_workers=2)
    result = artifact_coverage.evaluate_artifact_coverage_from_evidence(
        manifests,
        tmp_path,
        run.evidence,
        evidence_mode="derived",
    )

    owner = manifests[1]
    report = result.reports[owner.source_path]
    assert report.success is True
    assert [finding.to_dict() for finding in report.findings] == [
        {
            "artifact_name": "approved_session_fixture",
            "artifact_kind": "function",
            "parent_class": None,
            "file_path": "tests/conftest.py",
            "executed": True,
        }
    ]
    assert result.fallback_identities == ()


@pytest.mark.parametrize("approval", ["absent", "stale"])
def test_derived_coverage_rejects_unapproved_session_fixture(
    tmp_path: Path,
    approval: str,
) -> None:
    manifests = _write_project(tmp_path, approval=approval)

    run = collect_runtime_evidence(manifests, tmp_path, pytest_workers=2)
    result = artifact_coverage.evaluate_artifact_coverage_from_evidence(
        manifests,
        tmp_path,
        run.evidence,
        evidence_mode="derived",
    )

    owner = manifests[1]
    report = result.reports[owner.source_path]
    assert report.success is False
    assert [finding.executed for finding in report.findings] == [False]
    assert [error.code.value for error in report.errors] == ["E710"]
    assert result.fallback_identities == ()


def _write_project(root: Path, *, approval: str):
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "manifests").mkdir()
    (root / "src" / "other.py").write_text(
        "def other(value: str) -> str:\n    return value.upper()\n",
        encoding="utf-8",
    )
    conftest = root / "tests" / "conftest.py"
    conftest.write_text(
        "import pytest\n\n"
        "@pytest.fixture(scope='session')\n"
        "def approved_session_fixture() -> str:\n"
        "    return 'approved'\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_owner.py").write_text(
        "def test_owner(approved_session_fixture):\n"
        "    assert approved_session_fixture == 'approved'\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_other.py").write_text(
        "from src.other import other\n\n"
        "def test_other():\n"
        "    assert other('broad') == 'BROAD'\n",
        encoding="utf-8",
    )
    if approval != "absent":
        digest = hashlib.sha256(conftest.read_bytes()).hexdigest()
        if approval == "stale":
            digest = "0" * 64
        (root / ".maidrc.yaml").write_text(
            "artifact_coverage:\n"
            "  evidence_mode: derived\n"
            "  fixture_lifecycle_approvals:\n"
            "    - context_id: fixture:tests:approved_session_fixture:session\n"
            "      conftest_path: tests/conftest.py\n"
            f"      sha256: '{digest}'\n",
            encoding="utf-8",
        )

    broad_path = _write_manifest(
        root,
        slug="broad",
        created="2026-08-17T12:00:00Z",
        source_path="src/other.py",
        artifact={
            "kind": "function",
            "name": "other",
            "args": [{"name": "value", "type": "str"}],
            "returns": "str",
        },
        test_path="tests/",
    )
    owner_path = _write_manifest(
        root,
        slug="owner",
        created="2026-08-17T12:00:01Z",
        source_path="tests/conftest.py",
        artifact={
            "kind": "function",
            "name": "approved_session_fixture",
            "args": [],
            "returns": "str",
        },
        test_path="tests/test_owner.py",
    )
    return (load_manifest(broad_path), load_manifest(owner_path))


def _write_manifest(
    root: Path,
    *,
    slug: str,
    created: str,
    source_path: str,
    artifact: dict[str, object],
    test_path: str,
) -> Path:
    path = root / "manifests" / f"{slug}.manifest.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": f"Exercise {slug}",
                "type": "fix",
                "created": created,
                "files": {
                    "edit": [{"path": source_path, "artifacts": [artifact]}],
                    "read": ["tests/test_owner.py", "tests/test_other.py"],
                },
                "validate": [f"python -m pytest -q {test_path}"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path
