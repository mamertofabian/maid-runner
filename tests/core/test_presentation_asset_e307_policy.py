from __future__ import annotations

from pathlib import Path

from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode, Severity
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine


def test_presentation_asset_extensions_are_presence_only_info() -> None:
    from maid_runner.core.diagnostic_policy import no_validator_severity

    paths = [
        "templates/index.htm",
        "templates/app.HTML",
        "styles/base.css",
        "styles/theme.less",
        "styles/mobile.sass",
        "styles/components.scss",
    ]

    assert [no_validator_severity(path) for path in paths] == [
        Severity.INFO for _path in paths
    ]


def test_implementation_validation_keeps_presentation_asset_e307_visible_as_info(
    tmp_path: Path,
) -> None:
    template = tmp_path / "src" / "app.component.html"
    stylesheet = tmp_path / "src" / "app.component.sass"
    template.parent.mkdir()
    template.write_text("<main>StudyFinder</main>\n")
    stylesheet.write_text("main\n  display: block\n")
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    manifest_path = manifest_dir / "presentation-assets.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Track presentation assets"
type: snapshot
files:
  edit:
    - path: src/app.component.html
      artifacts:
        - kind: function
          name: template_placeholder
    - path: src/app.component.sass
      artifacts:
        - kind: function
          name: stylesheet_placeholder
validate:
  - uv run python -m pytest tests/core/test_presentation_asset_e307_policy.py -v
"""
    )

    result = ValidationEngine(project_root=tmp_path).validate(
        load_manifest(manifest_path),
        mode=ValidationMode.IMPLEMENTATION,
        include_chain_diagnostics=False,
        include_plugin_diagnostics=False,
    )

    assert result.success is True
    assert [
        (
            finding.code,
            finding.severity,
            finding.location.file if finding.location else "",
        )
        for finding in result.warnings
    ] == [
        (ErrorCode.VALIDATOR_NOT_AVAILABLE, Severity.INFO, "src/app.component.html"),
        (ErrorCode.VALIDATOR_NOT_AVAILABLE, Severity.INFO, "src/app.component.sass"),
    ]


def test_unrecognized_source_extension_remains_warning() -> None:
    from maid_runner.core.diagnostic_policy import no_validator_severity

    assert no_validator_severity("lib/task.rb") == Severity.WARNING
