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
    assert execution.parallel_without_history is False
