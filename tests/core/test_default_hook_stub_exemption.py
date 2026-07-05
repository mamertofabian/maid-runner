"""Behavioral tests for manifest-acknowledged default hook stubs."""

from __future__ import annotations

from pathlib import Path

import pytest

from maid_runner.core.manifest import ManifestSchemaError, load_manifest
from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import validate
from maid_runner.validators.base import BaseValidator, CollectionResult


class _ConcreteValidator(BaseValidator):
    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".txt",)

    def collect_implementation_artifacts(
        self,
        source: str,
        file_path: str | Path,
    ) -> CollectionResult:
        return CollectionResult(artifacts=[], language="text", file_path=str(file_path))

    def collect_behavioral_artifacts(
        self,
        source: str,
        file_path: str | Path,
    ) -> CollectionResult:
        return CollectionResult(artifacts=[], language="text", file_path=str(file_path))


def _write(project: Path, relative_path: str, content: str) -> Path:
    path = project / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _write_manifest(project: Path, name: str, content: str) -> Path:
    return _write(project, f"manifests/{name}", content)


def _warning_messages(result) -> list[str]:
    return [
        warning.message
        for warning in result.warnings
        if warning.code == ErrorCode.STUB_FUNCTION_DETECTED
    ]


def _source_with_default_hook() -> str:
    return '''class HookBase:
    def default_value(self):
        """Documented neutral default hook."""
        return None
'''


def _source_with_default_hook_and_real_stub() -> str:
    return (
        _source_with_default_hook()
        + """


def unfinished():
    pass
"""
    )


def _write_behavioral_test(project: Path, import_line: str, body: str) -> None:
    _write(
        project,
        "tests/test_hooks.py",
        f"{import_line}\n\n" "def test_hooks_are_exercised():\n" f"{body}",
    )


def test_default_hook_true_suppresses_e310_for_trivial_default(
    tmp_path: Path,
) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        "default-hook.manifest.yaml",
        """schema: "2"
goal: "Acknowledge intentional default hook"
type: fix
created: "2026-07-03T08:00:00Z"
files:
  create:
    - path: src/hooks.py
      artifacts:
        - kind: class
          name: HookBase
        - kind: method
          name: default_value
          of: HookBase
          default_hook: true
  read:
    - tests/test_hooks.py
validate:
  - pytest tests/test_hooks.py -v
""",
    )
    _write(tmp_path, "src/hooks.py", _source_with_default_hook())
    _write_behavioral_test(
        tmp_path,
        "from src.hooks import HookBase",
        "    assert HookBase().default_value() is None\n",
    )

    result = validate(
        manifest_path,
        mode=ValidationMode.IMPLEMENTATION,
        project_root=tmp_path,
        check_stubs=True,
    )

    assert result.success is True
    assert "HookBase.default_value" not in "\n".join(_warning_messages(result))

    validator = _ConcreteValidator()
    assert validator.module_path(Path("src/hooks.py"), tmp_path) is None
    assert validator.resolve_reexport("src.hooks", "HookBase", tmp_path) is None
    assert validator.get_test_function_bodies("", Path("tests/test_hooks.py")) == {}
    assert validator.generate_test_stub([], Path("tests/test_hooks.py")) == ""


def test_real_stub_without_default_hook_still_reports_e310(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        "mixed-stubs.manifest.yaml",
        """schema: "2"
goal: "Only acknowledged hook is exempt"
type: fix
created: "2026-07-03T08:00:00Z"
files:
  create:
    - path: src/hooks.py
      artifacts:
        - kind: class
          name: HookBase
        - kind: method
          name: default_value
          of: HookBase
          default_hook: true
        - kind: function
          name: unfinished
  read:
    - tests/test_hooks.py
validate:
  - pytest tests/test_hooks.py -v
""",
    )
    _write(tmp_path, "src/hooks.py", _source_with_default_hook_and_real_stub())
    _write_behavioral_test(
        tmp_path,
        "from src.hooks import HookBase, unfinished",
        "    assert HookBase().default_value() is None\n"
        "    assert unfinished is not None\n",
    )

    result = validate(
        manifest_path,
        mode=ValidationMode.IMPLEMENTATION,
        project_root=tmp_path,
        check_stubs=True,
    )

    messages = "\n".join(_warning_messages(result))
    assert "Function 'unfinished' appears to be a stub" in messages
    assert "HookBase.default_value" not in messages


def test_default_hook_parses_from_manifest_yaml(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        "parse-default-hook.manifest.yaml",
        """schema: "2"
goal: "Parse default_hook"
type: fix
created: "2026-07-03T08:00:00Z"
files:
  create:
    - path: src/hooks.py
      artifacts:
        - kind: function
          name: explicit_true
          default_hook: true
        - kind: function
          name: explicit_false
          default_hook: false
        - kind: function
          name: omitted
validate:
  - pytest tests/test_hooks.py -v
""",
    )

    manifest = load_manifest(manifest_path)
    artifacts = manifest.file_spec_for("src/hooks.py").artifacts

    assert [artifact.default_hook for artifact in artifacts] == [True, False, False]


def test_schema_rejects_non_boolean_default_hook(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        "invalid-default-hook.manifest.yaml",
        """schema: "2"
goal: "Reject invalid default_hook"
type: fix
created: "2026-07-03T08:00:00Z"
files:
  create:
    - path: src/hooks.py
      artifacts:
        - kind: function
          name: hook
          default_hook: "yes"
validate:
  - pytest tests/test_hooks.py -v
""",
    )

    with pytest.raises(ManifestSchemaError) as excinfo:
        load_manifest(manifest_path)

    assert "default_hook" in str(excinfo.value)
    assert "boolean" in str(excinfo.value)


def test_schema_rejects_default_hook_on_non_callable_artifact(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        "invalid-default-hook-kind.manifest.yaml",
        """schema: "2"
goal: "Reject default_hook on non-callable artifact"
type: fix
created: "2026-07-03T08:00:00Z"
files:
  create:
    - path: src/hooks.py
      artifacts:
        - kind: class
          name: HookBase
          default_hook: true
validate:
  - pytest tests/test_hooks.py -v
""",
    )

    with pytest.raises(ManifestSchemaError) as excinfo:
        load_manifest(manifest_path)

    message = str(excinfo.value)
    assert "kind" in message
    assert "function" in message
    assert "method" in message


def test_chain_level_acknowledgment_covers_other_declaring_manifests(
    tmp_path: Path,
) -> None:
    older_manifest = _write_manifest(
        tmp_path,
        "001-original.manifest.yaml",
        """schema: "2"
goal: "Original default hook declaration"
type: fix
created: "2026-07-03T08:00:00Z"
files:
  create:
    - path: src/hooks.py
      artifacts:
        - kind: class
          name: HookBase
        - kind: method
          name: default_value
          of: HookBase
  read:
    - tests/test_hooks.py
validate:
  - pytest tests/test_hooks.py -v
""",
    )
    _write_manifest(
        tmp_path,
        "002-acknowledge.manifest.yaml",
        """schema: "2"
goal: "Acknowledge the default hook declaration"
type: fix
created: "2026-07-03T08:01:00Z"
files:
  edit:
    - path: src/hooks.py
      artifacts:
        - kind: class
          name: HookBase
        - kind: method
          name: default_value
          of: HookBase
          default_hook: true
  read:
    - tests/test_hooks.py
validate:
  - pytest tests/test_hooks.py -v
""",
    )
    _write(tmp_path, "src/hooks.py", _source_with_default_hook())
    _write_behavioral_test(
        tmp_path,
        "from src.hooks import HookBase",
        "    assert HookBase().default_value() is None\n",
    )

    result = validate(
        older_manifest,
        mode=ValidationMode.IMPLEMENTATION,
        project_root=tmp_path,
        use_chain=True,
        check_stubs=True,
    )

    assert result.success is True
    assert "HookBase.default_value" not in "\n".join(_warning_messages(result))
