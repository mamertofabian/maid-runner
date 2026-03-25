"""Tests for maid_runner.core.config - MaidConfig loading."""

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
