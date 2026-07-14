"""Behavioral regressions for path-backed E200 module identities."""

from pathlib import Path

import pytest

from maid_runner.core.result import ErrorCode
from maid_runner.core.ts_module_paths import (
    clear_ts_resolution_cache,
    resolve_relative_ts_import,
    resolve_ts_import,
    resolve_ts_reexport,
    ts_file_to_module_path,
)
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine
from maid_runner.validators.python import PythonValidator


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _e200_errors(result) -> list:
    return [
        error
        for error in result.errors
        if error.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
    ]


def test_svelte_state_module_file_and_runtime_import_share_identity() -> None:
    importer = "src/lib/services/auto-sync.test"
    runtime_identity = resolve_relative_ts_import("./auto-sync.svelte", importer)

    assert runtime_identity == "src/lib/services/auto-sync"
    assert (
        ts_file_to_module_path("src/lib/services/auto-sync.svelte.ts", Path("."))
        == runtime_identity
    )
    assert (
        ts_file_to_module_path("src/lib/services/auto-sync.svelte.js", Path("."))
        == runtime_identity
    )


def test_svelte_state_module_runtime_import_satisfies_e200(tmp_path: Path) -> None:
    manifest_path = _write(
        tmp_path / "manifests" / "svelte-state.manifest.yaml",
        """schema: "2"
goal: "Cover a Svelte state module through its runtime import"
files:
  edit:
    - path: src/lib/services/auto-sync.svelte.ts
      artifacts:
        - kind: function
          name: getAutoSyncStatus
          args: []
          returns: string
  read:
    - tests/auto-sync.test.ts
validate:
  - vitest run tests/auto-sync.test.ts
""",
    )
    _write(
        tmp_path / "src" / "lib" / "services" / "auto-sync.svelte.ts",
        "export function getAutoSyncStatus(): string { return 'idle'; }\n",
    )
    _write(
        tmp_path / "tests" / "auto-sync.test.ts",
        "import { getAutoSyncStatus } from "
        "'../src/lib/services/auto-sync.svelte';\n\n"
        "it('reads status', () => {\n"
        "  expect(getAutoSyncStatus()).toBe('idle');\n"
        "});\n",
    )

    result = ValidationEngine(project_root=tmp_path).validate(
        manifest_path, mode=ValidationMode.BEHAVIORAL
    )

    assert _e200_errors(result) == []
    assert result.success is True


def test_hyphenated_python_loader_records_literal_script_identity() -> None:
    source = """
def load_module(module_name, relative_path):
    raise NotImplementedError

speak_summary = load_module("speak_summary", "hooks/session/speak-summary.py")

def test_tts_disabled():
    assert speak_summary.is_tts_disabled() is False
"""

    result = PythonValidator().collect_behavioral_artifacts(
        source, "tests/test_capture_response.py"
    )

    assert any(
        artifact.name == "is_tts_disabled"
        and artifact.import_source == "hooks.session.speak-summary"
        and artifact.reference_context == "call"
        for artifact in result.artifacts
    )


def test_hyphenated_python_loader_rejects_mismatched_runtime_name() -> None:
    source = """
def load_module(module_name, relative_path):
    raise NotImplementedError

speak_summary = load_module("different_hook", "hooks/session/speak-summary.py")

def test_tts_disabled():
    assert speak_summary.is_tts_disabled() is False
"""

    result = PythonValidator().collect_behavioral_artifacts(
        source, "tests/test_capture_response.py"
    )

    assert not any(
        artifact.name == "is_tts_disabled"
        and artifact.import_source == "hooks.session.speak-summary"
        for artifact in result.artifacts
    )


def test_hyphenated_python_loader_call_satisfies_e200(tmp_path: Path) -> None:
    manifest_path = _write(
        tmp_path / "manifests" / "hook-script.manifest.yaml",
        """schema: "2"
goal: "Cover a dynamically loaded hook script"
files:
  edit:
    - path: hooks/session/speak-summary.py
      artifacts:
        - kind: function
          name: is_tts_disabled
          args: []
          returns: bool
  read:
    - tests/test_capture_response.py
validate:
  - pytest tests/test_capture_response.py -v
""",
    )
    _write(
        tmp_path / "hooks" / "session" / "speak-summary.py",
        "def is_tts_disabled() -> bool:\n    return False\n",
    )
    _write(
        tmp_path / "tests" / "test_capture_response.py",
        "def load_module(module_name, relative_path):\n"
        "    raise NotImplementedError\n\n"
        "speak_summary = load_module(\n"
        "    'speak_summary', 'hooks/session/speak-summary.py'\n"
        ")\n\n"
        "def test_tts_disabled():\n"
        "    assert speak_summary.is_tts_disabled() is False\n",
    )

    result = ValidationEngine(project_root=tmp_path).validate(
        manifest_path, mode=ValidationMode.BEHAVIORAL
    )

    assert _e200_errors(result) == []
    assert result.success is True


def test_svelte_state_module_alias_and_barrel_resolve_canonical_identity(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "tsconfig.json",
        '{"compilerOptions": {"baseUrl": ".", "paths": {"$lib/*": ["src/lib/*"]}}}',
    )
    _write(
        tmp_path / "src" / "lib" / "state.svelte.ts",
        "export function aliasOnly(): string { return 'alias'; }\n"
        "export function barrelOnly(): string { return 'barrel'; }\n",
    )
    _write(
        tmp_path / "src" / "lib" / "index.ts",
        "export { barrelOnly } from './state.svelte';\n",
    )
    clear_ts_resolution_cache()

    assert (
        resolve_ts_import("$lib/state.svelte", "tests/state.test", tmp_path)
        == "src/lib/state"
    )
    assert resolve_ts_reexport("src/lib", "barrelOnly", tmp_path) == (
        "src/lib/state",
        "barrelOnly",
    )


def test_svelte_state_module_alias_and_barrel_imports_satisfy_e200(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = _write(
        tmp_path / "manifests" / "svelte-imports.manifest.yaml",
        """schema: "2"
goal: "Cover a Svelte state module through alias and barrel imports"
files:
  edit:
    - path: src/lib/state.svelte.ts
      artifacts:
        - kind: function
          name: aliasOnly
          args: []
          returns: string
        - kind: function
          name: barrelOnly
          args: []
          returns: string
  read:
    - tests/state.test.ts
validate:
  - vitest run tests/state.test.ts
""",
    )
    _write(
        tmp_path / "tsconfig.json",
        '{"compilerOptions": {"baseUrl": ".", "paths": {"$lib": ["src/lib/index.ts"], "$lib/*": ["src/lib/*"]}}}',
    )
    _write(
        tmp_path / "src" / "lib" / "state.svelte.ts",
        "export function aliasOnly(): string { return 'alias'; }\n"
        "export function barrelOnly(): string { return 'barrel'; }\n",
    )
    _write(
        tmp_path / "src" / "lib" / "index.ts",
        "export { barrelOnly } from './state.svelte';\n",
    )
    _write(
        tmp_path / "tests" / "state.test.ts",
        "import { aliasOnly } from '$lib/state.svelte';\n"
        "import { barrelOnly } from '$lib';\n\n"
        "it('uses state exports', () => {\n"
        "  expect(aliasOnly()).toBe('alias');\n"
        "  expect(barrelOnly()).toBe('barrel');\n"
        "});\n",
    )
    clear_ts_resolution_cache()
    monkeypatch.chdir(tmp_path)

    result = ValidationEngine(project_root=tmp_path).validate(
        manifest_path, mode=ValidationMode.BEHAVIORAL
    )

    assert _e200_errors(result) == []
    assert result.success is True


def test_svelte_state_module_does_not_override_plain_typescript_entry(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src" / "ordinary.ts",
        "export function ordinary(): string { return 'ordinary'; }\n",
    )
    _write(
        tmp_path / "src" / "state-only.ts",
        "export function stateOnly(): string { return 'state'; }\n",
    )
    _write(
        tmp_path / "src" / "state.ts",
        "export { ordinary } from './ordinary';\n",
    )
    _write(
        tmp_path / "src" / "state.svelte.ts",
        "export { stateOnly } from './state-only';\n",
    )
    clear_ts_resolution_cache()

    assert resolve_ts_reexport("src/state", "ordinary", tmp_path) == (
        "src/ordinary",
        "ordinary",
    )
    assert resolve_ts_reexport("src/state", "stateOnly", tmp_path) is None


def test_hyphenated_python_loader_rejects_non_assignment_shapes() -> None:
    sources = (
        """
def load_module(module_name, relative_path):
    raise NotImplementedError

def test_inline_loader():
    assert load_module("speak_summary", "hooks/session/speak-summary.py").is_tts_disabled() is False
""",
        """
def load_module(module_name, relative_path):
    raise NotImplementedError

def test_walrus_loader():
    assert (module := load_module("speak_summary", "hooks/session/speak-summary.py")).is_tts_disabled() is False
""",
        """
def load_module(module_name, relative_path, mode):
    raise NotImplementedError

speak_summary = load_module("speak_summary", "hooks/session/speak-summary.py", "strict")

def test_extra_argument_loader():
    assert speak_summary.is_tts_disabled() is False
""",
    )

    for source in sources:
        result = PythonValidator().collect_behavioral_artifacts(
            source, "tests/test_capture_response.py"
        )
        assert not any(
            artifact.name == "is_tts_disabled"
            and artifact.import_source == "hooks.session.speak-summary"
            for artifact in result.artifacts
        )
