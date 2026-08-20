"""Tests for maid_runner.core.config - MaidConfig loading."""

import pytest

from maid_runner.core.config import MaidConfig, load_config
from maid_runner.core.types import ValidationMode


class TestMaidConfig:
    def test_defaults(self):
        config = MaidConfig()
        assert config.manifest_dir == "manifests/"
        assert config.schema_version == "2"
        assert config.default_validation_mode == ValidationMode.IMPLEMENTATION
        assert config.languages == ("python", "typescript")
        assert config.coherence_enabled is False
        assert config.coherence_checks == ()
        assert config.coverage_recommendation.critical_paths == ()
        assert config.coverage_recommendation.entrypoints == ()
        assert config.coverage_recommendation.cache_enabled is True
        assert config.coverage_recommendation.deep_command is None

    def test_custom_values(self):
        config = MaidConfig(
            manifest_dir="custom/",
            default_validation_mode=ValidationMode.BEHAVIORAL,
            languages=("python",),
            coherence_enabled=True,
            coherence_checks=("duplicate", "naming"),
        )
        assert config.manifest_dir == "custom/"
        assert config.default_validation_mode == ValidationMode.BEHAVIORAL
        assert config.languages == ("python",)
        assert config.coherence_enabled is True
        assert config.coherence_checks == ("duplicate", "naming")


class TestLoadConfig:
    def test_load_from_yaml(self, tmp_path):
        config_file = tmp_path / ".maidrc.yaml"
        config_file.write_text(
            "manifest_dir: custom-manifests/\n"
            "schema_version: 2\n"
            "default_validation_mode: behavioral\n"
            "languages:\n"
            "  - python\n"
            "coherence:\n"
            "  enabled: true\n"
            "  checks:\n"
            "    - duplicate\n"
            "    - signature\n"
        )
        config = load_config(tmp_path)
        assert config.manifest_dir == "custom-manifests/"
        assert config.default_validation_mode == ValidationMode.BEHAVIORAL
        assert config.languages == ("python",)
        assert config.coherence_enabled is True
        assert config.coherence_checks == ("duplicate", "signature")

    def test_load_missing_returns_defaults(self, tmp_path):
        config = load_config(tmp_path)
        assert config.manifest_dir == "manifests/"
        assert config.default_validation_mode == ValidationMode.IMPLEMENTATION

    def test_load_partial_config(self, tmp_path):
        config_file = tmp_path / ".maidrc.yaml"
        config_file.write_text("manifest_dir: my-manifests/\n")
        config = load_config(tmp_path)
        assert config.manifest_dir == "my-manifests/"
        assert config.default_validation_mode == ValidationMode.IMPLEMENTATION
        assert config.coherence_enabled is False

    def test_load_empty_file(self, tmp_path):
        config_file = tmp_path / ".maidrc.yaml"
        config_file.write_text("")
        config = load_config(tmp_path)
        assert config.manifest_dir == "manifests/"


def test_test_execution_config_accepts_workers_threshold_jobs_and_process_budget(
    tmp_path,
):
    from maid_runner.core.config import TestExecutionConfig

    (tmp_path / ".maidrc.yaml").write_text(
        """test_execution:
  pytest_workers: 8
  pytest_dist_mode: loadscope
  accepted_pytest_worker_counts: [8]
  parallel_threshold_seconds: 30
  parallel_without_history: false
  command_jobs: 2
  max_processes: 16
"""
    )

    config = load_config(tmp_path).test_execution

    assert isinstance(config, TestExecutionConfig)
    assert config.pytest_workers == 8
    assert config.pytest_dist_mode == "loadscope"
    assert config.accepted_pytest_worker_counts == (8,)
    assert config.parallel_threshold_seconds == 30.0
    assert config.parallel_without_history is False
    assert config.command_jobs == 2
    assert config.max_processes == 16
    assert config.command_jobs * config.pytest_workers == config.max_processes


def test_test_execution_config_rejects_invalid_or_oversubscribed_values(tmp_path):
    invalid_values = (
        "pytest_workers: 0\naccepted_pytest_worker_counts: [8]",
        "pytest_workers: 8\naccepted_pytest_worker_counts: [8]\ncommand_jobs: 2\nmax_processes: 8",
        "pytest_workers: 8\naccepted_pytest_worker_counts: [4]",
        "pytest_workers: 8\naccepted_pytest_worker_counts: [8]\nparallel_threshold_seconds: .nan",
    )

    for body in invalid_values:
        (tmp_path / ".maidrc.yaml").write_text(
            "test_execution:\n  " + body.replace("\n", "\n  ") + "\n"
        )
        with pytest.raises(ValueError):
            load_config(tmp_path)


def test_test_execution_config_accepts_only_proven_loadscope_dist_mode(tmp_path):
    (tmp_path / ".maidrc.yaml").write_text(
        """test_execution:
  pytest_workers: 8
  pytest_dist_mode: load
  accepted_pytest_worker_counts: [8]
  max_processes: 8
"""
    )

    with pytest.raises(ValueError, match="loadscope"):
        load_config(tmp_path)

    defaults = MaidConfig().test_execution
    assert defaults.pytest_workers == 1
    assert defaults.pytest_dist_mode == "loadscope"
    assert defaults.accepted_pytest_worker_counts == ()
    assert defaults.parallel_threshold_seconds == 30.0
    assert defaults.parallel_without_history is False
    assert defaults.command_jobs == 1
    assert defaults.max_processes == 1


def test_repository_maidrc_opts_into_proven_eight_worker_loadscope_policy():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    execution = load_config(root).test_execution

    assert execution.pytest_workers == 8
    assert execution.pytest_dist_mode == "loadscope"
    assert execution.accepted_pytest_worker_counts == (8,)
    assert execution.command_jobs * execution.pytest_workers <= execution.max_processes
    assert execution.parallel_without_history is True


def test_fixture_lifecycle_approval_validation_fails_closed(tmp_path):
    import hashlib

    conftest = tmp_path / "tests/conftest.py"
    conftest.parent.mkdir()
    conftest.write_text("# reviewed fixture bytes\n")
    digest = hashlib.sha256(conftest.read_bytes()).hexdigest()

    def write_approval(body):
        (tmp_path / ".maidrc.yaml").write_text(
            "artifact_coverage:\n  fixture_lifecycle_approvals:\n" + body
        )

    valid = (
        "    - context_id: 'fixture:tests:reviewed:session'\n"
        "      conftest_path: tests/conftest.py\n"
        f"      sha256: '{digest}'\n"
    )
    write_approval(valid)
    approval = load_config(tmp_path).artifact_coverage.fixture_lifecycle_approvals[0]
    assert approval.context_id == "fixture:tests:reviewed:session"
    assert approval.conftest_path == "tests/conftest.py"
    assert approval.sha256 == digest

    outside = tmp_path.parent / "outside-conftest.py"
    outside.write_text("# outside\n")
    link = tmp_path / "nested/conftest.py"
    link.parent.mkdir()
    link.symlink_to(outside)
    other = tmp_path / "other/conftest.py"
    other.parent.mkdir()
    other.write_text("# unrelated fixture bytes\n")
    other_digest = hashlib.sha256(other.read_bytes()).hexdigest()
    conflicting = valid + valid.replace(digest, "0" * 64)
    invalid = (
        valid + valid,
        conflicting,
        valid.replace("tests/conftest.py", "../outside-conftest.py"),
        valid.replace("tests/conftest.py", str(conftest)),
        valid.replace("tests/conftest.py", "nested/conftest.py"),
        valid.replace("tests/conftest.py", "tests/not-a-fixture.py"),
        valid.replace("tests/conftest.py", "other/conftest.py").replace(
            digest, other_digest
        ),
        valid.replace("fixture:tests:reviewed:session", "fixture::reviewed:session"),
        valid.replace("fixture:tests:reviewed:session", ""),
        valid.replace(digest, "xyz"),
        valid.replace(digest, digest.upper()),
        "    - not: a-valid-approval\n",
        "    - scalar\n",
    )
    for body in invalid:
        write_approval(body)
        with pytest.raises(ValueError):
            load_config(tmp_path)


def test_fixture_lifecycle_approvals_bind_project_and_distribution_sources(
    tmp_path, monkeypatch
):
    import hashlib
    import importlib.metadata
    import inspect
    from pathlib import Path
    from types import SimpleNamespace

    import _pytest.tmpdir

    from maid_runner.core.config import DistributionFixtureLifecycleApproval

    test_source = tmp_path / "tests/test_local_fixture.py"
    test_source.parent.mkdir()
    test_source.write_text("# reviewed local fixture bytes\n")
    local_digest = hashlib.sha256(test_source.read_bytes()).hexdigest()
    distribution_source = Path(inspect.getsourcefile(_pytest.tmpdir)).resolve()
    distribution_digest = hashlib.sha256(distribution_source.read_bytes()).hexdigest()
    project_block = (
        "artifact_coverage:\n"
        "  fixture_lifecycle_approvals:\n"
        "    - context_id: 'fixture:tests/test_local_fixture.py:local:function'\n"
        "      conftest_path: tests/test_local_fixture.py\n"
        f"      sha256: '{local_digest}'\n"
    )
    distribution_block = (
        "  distribution_fixture_lifecycle_approvals:\n"
        "    - context_id: 'fixture::tmp_path_factory:session'\n"
        "      distribution: pytest\n"
        "      module_path: _pytest/tmpdir.py\n"
        f"      sha256: '{distribution_digest}'\n"
    )
    config = project_block + distribution_block
    duplicate_distribution_entry = (
        "    - context_id: 'fixture::tmp_path_factory:session'\n"
        "      distribution: pytest\n"
        "      module_path: _pytest/tmpdir.py\n"
        f"      sha256: '{distribution_digest}'\n"
    )
    (tmp_path / ".maidrc.yaml").write_text(config)

    coverage = load_config(tmp_path).artifact_coverage

    assert coverage.fixture_lifecycle_approvals[0].conftest_path == (
        "tests/test_local_fixture.py"
    )
    approval = coverage.distribution_fixture_lifecycle_approvals[0]
    assert isinstance(approval, DistributionFixtureLifecycleApproval)
    assert approval.context_id == "fixture::tmp_path_factory:session"
    assert approval.distribution == "pytest"
    assert approval.module_path == "_pytest/tmpdir.py"
    assert approval.sha256 == distribution_digest

    invalid = (
        config.replace("distribution: pytest", "distribution: missing-package"),
        config.replace("_pytest/tmpdir.py", "../_pytest/tmpdir.py"),
        config.replace("_pytest/tmpdir.py", str(distribution_source)),
        config.replace("_pytest/tmpdir.py", "_pytest"),
        config.replace("_pytest/tmpdir.py", "_pytest/missing.py"),
        config.replace(
            "fixture::tmp_path_factory:session", "fixture:tests:bad:session"
        ),
        config.replace(distribution_digest, distribution_digest.upper()),
        config.replace("      sha256:", "      extra: value\n      sha256:", 1),
        config + duplicate_distribution_entry,
        config + duplicate_distribution_entry.replace(distribution_digest, "0" * 64),
        project_block + "  distribution_fixture_lifecycle_approvals: scalar\n",
        project_block + "  distribution_fixture_lifecycle_approvals:\n    - scalar\n",
    )
    for value in invalid:
        (tmp_path / ".maidrc.yaml").write_text(value)
        with pytest.raises(ValueError):
            load_config(tmp_path)

    distribution_root = tmp_path / "fake-site-packages"
    distribution_root.mkdir()
    outside_module = tmp_path / "outside_distribution.py"
    outside_module.write_text("# outside fake distribution\n")
    escaped_module = distribution_root / "fake_package/fixture.py"
    escaped_module.parent.mkdir()
    escaped_module.symlink_to(outside_module)
    escaped_digest = hashlib.sha256(outside_module.read_bytes()).hexdigest()
    real_distribution = importlib.metadata.distribution

    def fake_distribution(name):
        if name == "fake-package":
            return SimpleNamespace(
                locate_file=lambda path: distribution_root / Path(path)
            )
        return real_distribution(name)

    monkeypatch.setattr(importlib.metadata, "distribution", fake_distribution)
    escaped_config = project_block + (
        "  distribution_fixture_lifecycle_approvals:\n"
        "    - context_id: 'fixture::escaped:session'\n"
        "      distribution: fake-package\n"
        "      module_path: fake_package/fixture.py\n"
        f"      sha256: '{escaped_digest}'\n"
    )
    (tmp_path / ".maidrc.yaml").write_text(escaped_config)
    with pytest.raises(ValueError):
        load_config(tmp_path)


def test_knockout_execution_jobs_requires_positive_bounded_integer(tmp_path):
    from maid_runner.core.config import KnockoutExecutionConfig

    (tmp_path / ".maidrc.yaml").write_text(
        "test_execution:\n  max_processes: 4\n" "knockout_execution:\n  jobs: 3\n"
    )
    config = load_config(tmp_path)
    assert isinstance(config.knockout_execution, KnockoutExecutionConfig)
    assert config.knockout_execution.jobs == 3

    for jobs in ("0", "-1", "true", "'2'", "5"):
        (tmp_path / ".maidrc.yaml").write_text(
            "test_execution:\n  max_processes: 4\n"
            f"knockout_execution:\n  jobs: {jobs}\n"
        )
        with pytest.raises(ValueError, match="knockout_execution.jobs"):
            load_config(tmp_path)


def test_artifact_coverage_fallback_jobs_requires_positive_bounded_integer(tmp_path):
    (tmp_path / ".maidrc.yaml").write_text(
        "test_execution:\n  max_processes: 4\n"
        "artifact_coverage:\n  fallback_jobs: 3\n"
    )
    config = load_config(tmp_path)
    assert config.artifact_coverage.fallback_jobs == 3

    for jobs in ("0", "-1", "true", "'2'", "5"):
        (tmp_path / ".maidrc.yaml").write_text(
            "test_execution:\n  max_processes: 4\n"
            f"artifact_coverage:\n  fallback_jobs: {jobs}\n"
        )
        with pytest.raises(ValueError, match="artifact_coverage.fallback_jobs"):
            load_config(tmp_path)
