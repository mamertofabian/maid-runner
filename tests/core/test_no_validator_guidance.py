from __future__ import annotations

from pathlib import Path


def _validate_declared_file(project_root: Path, relative_path: str):
    from maid_runner.core.manifest import load_manifest
    from maid_runner.core.types import ValidationMode
    from maid_runner.core.validate import ValidationEngine

    source_path = project_root / relative_path
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("content\n", encoding="utf-8")
    manifest_dir = project_root / "manifests"
    manifest_dir.mkdir(exist_ok=True)
    manifest_path = manifest_dir / "unsupported.manifest.yaml"
    manifest_path.write_text(
        f"""schema: "2"
goal: "Validate unsupported file guidance"
type: feature
files:
  edit:
    - path: {relative_path}
      artifacts:
        - kind: function
          name: placeholder
validate:
  - uv run python -m pytest tests/core/test_no_validator_guidance.py -q
""",
        encoding="utf-8",
    )
    return ValidationEngine(project_root=project_root).validate(
        load_manifest(manifest_path),
        mode=ValidationMode.IMPLEMENTATION,
        include_chain_diagnostics=False,
        include_plugin_diagnostics=False,
    )


def test_no_validator_guidance_names_runtime_audit_and_plugin_docs() -> None:
    from maid_runner.core.diagnostic_policy import no_validator_guidance

    guidance = no_validator_guidance()

    assert "maid validators" in guidance
    assert "validator-plugin-authoring" in guidance


def test_source_like_e307_suggests_validator_plugin_discovery(
    tmp_path: Path,
) -> None:
    from maid_runner.core.diagnostic_policy import no_validator_severity
    from maid_runner.core.result import ErrorCode, Severity

    result = _validate_declared_file(tmp_path, "src/Program.cs")

    assert no_validator_severity("src/Program.cs") == Severity.WARNING
    assert len(result.warnings) == 1
    warning = result.warnings[0]
    assert warning.code == ErrorCode.VALIDATOR_NOT_AVAILABLE
    assert warning.severity == Severity.WARNING
    assert "maid validators" in (warning.suggestion or "")
    assert "validator-plugin-authoring" in (warning.suggestion or "")


def test_unsupported_language_error_suggests_validator_plugin_discovery() -> None:
    from maid_runner.validators.registry import UnsupportedLanguageError

    message = str(UnsupportedLanguageError(".cs"))

    assert "maid validators" in message
    assert "validator-plugin-authoring" in message


def test_recognized_non_code_e307_has_no_plugin_suggestion(tmp_path: Path) -> None:
    from maid_runner.core.diagnostic_policy import no_validator_severity
    from maid_runner.core.result import ErrorCode, Severity

    result = _validate_declared_file(tmp_path, "README.md")

    assert no_validator_severity("README.md") == Severity.INFO
    assert len(result.warnings) == 1
    warning = result.warnings[0]
    assert warning.code == ErrorCode.VALIDATOR_NOT_AVAILABLE
    assert warning.severity == Severity.INFO
    assert warning.suggestion is None
