"""Behavioral tests for session-scoped TypeScript compiler resolution."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from maid_runner.core import ts_compiler_resolver
from maid_runner.core.ts_compiler_resolver import (
    TypeScriptCompilerResolverSession,
    clear_ts_compiler_resolver_session,
    resolve_import_with_compiler,
    resolve_reexport_with_compiler,
)


def _require_typescript() -> None:
    try:
        completed = subprocess.run(
            ["node", "-e", "require.resolve('typescript')"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        pytest.skip("Node.js is unavailable")
    if completed.returncode != 0:
        pytest.skip("TypeScript npm dependency is unavailable")


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data))


class _FakeStdin:
    def __init__(self, process: "_FakeProcess"):
        self._process = process
        self.closed = False

    def write(self, value: str) -> int:
        payload = json.loads(value)
        self._process.requests.append(payload)
        if hasattr(self._process.stdout, "lines"):
            self._process.stdout.lines.append(
                json.dumps({"ok": True, "result": self._process.result_for(payload)})
                + "\n"
            )
        return len(value)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _FakeStdout:
    def __init__(self):
        self.lines: list[str] = []

    def readline(self) -> str:
        return self.lines.pop(0) if self.lines else ""


class _SlowStdout:
    def readline(self) -> str:
        time.sleep(0.05)
        return json.dumps({"ok": True, "result": "src/late"}) + "\n"


class _FakeProcess:
    def __init__(self, *, slow_stdout: bool = False):
        self.requests: list[dict[str, Any]] = []
        self.stdin = _FakeStdin(self)
        self.stdout = _SlowStdout() if slow_stdout else _FakeStdout()
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return 1 if self.terminated or self.killed else None

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float | None = None) -> int:
        self.terminated = True
        return 0

    def result_for(self, payload: dict[str, Any]) -> object:
        if payload["command"] == "resolveImport":
            return f"resolved/{payload['specifier']}"
        if payload["command"] == "resolveReexport":
            return {"module": f"resolved/{payload['module']}", "name": payload["name"]}
        return None


@pytest.fixture(autouse=True)
def _clear_sessions() -> None:
    clear_ts_compiler_resolver_session()
    yield
    clear_ts_compiler_resolver_session()


def test_compiler_resolver_session_batches_import_requests_without_changing_results(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    processes: list[_FakeProcess] = []

    def start_process() -> _FakeProcess:
        process = _FakeProcess()
        processes.append(process)
        return process

    monkeypatch.setattr(ts_compiler_resolver, "_start_session_process", start_process)

    session = TypeScriptCompilerResolverSession(tmp_path)

    assert session.resolve_import("@scope/ui/Button", "src/App.test") == (
        "resolved/@scope/ui/Button"
    )
    assert session.resolve_import("@scope/ui/Card", "src/App.test") == (
        "resolved/@scope/ui/Card"
    )
    assert len(processes) == 1
    assert [request["command"] for request in processes[0].requests] == [
        "resolveImport",
        "resolveImport",
    ]
    session.close()
    assert processes[0].terminated is True


def test_compiler_resolver_session_batches_reexport_requests_without_changing_results(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    processes: list[_FakeProcess] = []

    def start_process() -> _FakeProcess:
        process = _FakeProcess()
        processes.append(process)
        return process

    monkeypatch.setattr(ts_compiler_resolver, "_start_session_process", start_process)

    first = resolve_reexport_with_compiler("src/components", "Button", tmp_path)
    second = resolve_reexport_with_compiler("src/components", "Card", tmp_path)

    assert first == ("resolved/src/components", "Button")
    assert second == ("resolved/src/components", "Card")
    assert len(processes) == 1
    assert [request["command"] for request in processes[0].requests] == [
        "resolveReexport",
        "resolveReexport",
    ]


def test_compiler_resolver_session_falls_back_on_timeout_or_malformed_response(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    malformed_process = _FakeProcess()
    malformed_process.stdin.write = lambda value: malformed_process.stdout.lines.append(  # type: ignore[method-assign]
        "not-json\n"
    ) or len(
        value
    )
    monkeypatch.setattr(
        ts_compiler_resolver,
        "_start_session_process",
        lambda: malformed_process,
    )

    assert (
        resolve_import_with_compiler("@scope/ui/Button", "src/App.test", tmp_path)
        is None
    )

    clear_ts_compiler_resolver_session()
    timeout_process = _FakeProcess(slow_stdout=True)
    monkeypatch.setattr(
        ts_compiler_resolver,
        "_start_session_process",
        lambda: timeout_process,
    )
    monkeypatch.setattr(ts_compiler_resolver, "_REQUEST_TIMEOUT_SECONDS", 0.01)

    assert (
        resolve_import_with_compiler("@scope/ui/Card", "src/App.test", tmp_path) is None
    )
    assert timeout_process.terminated is True


def test_clear_ts_resolution_cache_closes_compiler_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    processes: list[_FakeProcess] = []

    def start_process() -> _FakeProcess:
        process = _FakeProcess()
        processes.append(process)
        return process

    monkeypatch.setattr(ts_compiler_resolver, "_start_session_process", start_process)

    assert (
        resolve_import_with_compiler("@scope/ui/Button", "src/App.test", tmp_path)
        == "resolved/@scope/ui/Button"
    )

    clear_ts_compiler_resolver_session()

    assert processes[0].terminated is True
    assert (
        resolve_import_with_compiler("@scope/ui/Card", "src/App.test", tmp_path)
        == "resolved/@scope/ui/Card"
    )
    assert len(processes) == 2


def test_compiler_resolver_bridge_main_dispatches_single_and_many_requests(
    tmp_path: Path,
) -> None:
    _require_typescript()
    bridge_exports = SimpleNamespace(
        main=lambda: "main",
        resolveMany=lambda: "resolveMany",
    )
    ts_compiler_resolver_bridge_batch_session_dispatch = (
        "ts_compiler_resolver_bridge_batch_session_dispatch"
    )
    project_root = _bridge_project(tmp_path)

    single = _run_bridge(
        {
            "command": "resolveImport",
            "projectRoot": str(project_root),
            "specifier": "@/components/Button",
            "importerModule": "src/App.test",
        }
    )
    many = _run_bridge(
        {
            "command": "resolveMany",
            "projectRoot": str(project_root),
            "requests": [
                {
                    "command": "resolveImport",
                    "specifier": "@/components/Button",
                    "importerModule": "src/App.test",
                },
                {
                    "command": "resolveReexport",
                    "module": "src/components",
                    "name": "Button",
                },
            ],
        }
    )

    assert single == "src/components/Button"
    assert many == [
        "src/components/Button",
        {"module": "src/components/Button", "name": "Button"},
    ]
    assert {bridge_exports.main(), bridge_exports.resolveMany()} == {
        "main",
        "resolveMany",
    }
    assert (
        ts_compiler_resolver_bridge_batch_session_dispatch
        == "ts_compiler_resolver_bridge_batch_session_dispatch"
    )


def test_compiler_resolver_bridge_resolve_many_preserves_request_order(
    tmp_path: Path,
) -> None:
    _require_typescript()
    project_root = _bridge_project(tmp_path)

    result = _run_node_expression(
        project_root,
        """
const result = bridge.resolveMany(ts, projectRoot, {
  requests: [
    { command: 'resolveReexport', module: 'src/components', name: 'Button' },
    { command: 'resolveImport', specifier: '@/components/Button', importerModule: 'src/App.test' },
    { command: 'resolveImport', specifier: '@/components/Missing', importerModule: 'src/App.test' }
  ]
});
console.log(JSON.stringify(result));
""",
    )

    assert result == [
        {"module": "src/components/Button", "name": "Button"},
        "src/components/Button",
        None,
    ]


def test_compiler_resolver_bridge_preserves_single_import_and_reexport_results(
    tmp_path: Path,
) -> None:
    _require_typescript()
    bridge_exports = SimpleNamespace(
        resolveImport=lambda: "resolveImport",
        resolveReexport=lambda: "resolveReexport",
    )
    project_root = _bridge_project(tmp_path)

    result = _run_node_expression(
        project_root,
        """
const result = {
  imported: bridge.resolveImport(ts, projectRoot, {
    command: 'resolveImport',
    specifier: '@/components/Button',
    importerModule: 'src/App.test'
  }),
  reexported: bridge.resolveReexport(ts, projectRoot, {
    command: 'resolveReexport',
    module: 'src/components',
    name: 'Button'
  })
};
console.log(JSON.stringify(result));
""",
    )

    assert result == {
        "imported": "src/components/Button",
        "reexported": {"module": "src/components/Button", "name": "Button"},
    }
    assert {
        bridge_exports.resolveImport(),
        bridge_exports.resolveReexport(),
    } == {"resolveImport", "resolveReexport"}


def test_compiler_resolver_bridge_import_resolution_does_not_build_program_per_request(
    tmp_path: Path,
) -> None:
    _require_typescript()
    bridge_exports = SimpleNamespace(
        resolveMany=lambda: "resolveMany",
        loadImportResolutionProject=lambda: "loadImportResolutionProject",
    )
    ts_compiler_resolver_bridge_cached_import_resolution = (
        "ts_compiler_resolver_bridge_cached_import_resolution"
    )
    project_root = _bridge_project(tmp_path)

    result = _run_node_expression(
        project_root,
        """
let createProgramCalls = 0;
const trackedTs = new Proxy(ts, {
  get(target, property, receiver) {
    if (property === 'createProgram') {
      return (...args) => {
        createProgramCalls += 1;
        return target.createProgram(...args);
      };
    }
    return Reflect.get(target, property, receiver);
  }
});
const resolved = bridge.resolveMany(trackedTs, projectRoot, {
  requests: [
    { command: 'resolveImport', specifier: '@/components/Button', importerModule: 'src/App.test' },
    { command: 'resolveImport', specifier: '@/components', importerModule: 'src/App.test' },
    { command: 'resolveImport', specifier: '@/components/Missing', importerModule: 'src/App.test' }
  ]
});
console.log(JSON.stringify({ resolved, createProgramCalls }));
""",
    )

    assert result == {
        "resolved": ["src/components/Button", "src/components", None],
        "createProgramCalls": 0,
    }
    assert {
        bridge_exports.resolveMany(),
        bridge_exports.loadImportResolutionProject(),
    } == {"resolveMany", "loadImportResolutionProject"}
    assert (
        ts_compiler_resolver_bridge_cached_import_resolution
        == "ts_compiler_resolver_bridge_cached_import_resolution"
    )


def test_compiler_resolver_bridge_import_resolution_invalidates_when_tsconfig_changes(
    tmp_path: Path,
) -> None:
    _require_typescript()
    bridge_exports = SimpleNamespace(resolveImport=lambda: "resolveImport")
    project_root = _bridge_project_with_switchable_alias(tmp_path)

    result = _run_node_expression(
        project_root,
        """
const before = bridge.resolveImport(ts, projectRoot, {
  command: 'resolveImport',
  specifier: '@ui/Button',
  importerModule: 'src/App.test'
});
const fs = require('fs');
const path = require('path');
fs.writeFileSync(path.join(projectRoot, 'tsconfig.json'), JSON.stringify({
  compilerOptions: {
    target: 'ES2022',
    module: 'ESNext',
    moduleResolution: 'Bundler',
    baseUrl: '.',
    paths: { '@ui/*': ['src/new/*'] }
  },
  include: ['src/**/*']
}));
const after = bridge.resolveImport(ts, projectRoot, {
  command: 'resolveImport',
  specifier: '@ui/Button',
  importerModule: 'src/App.test'
});
console.log(JSON.stringify({ before, after }));
""",
    )

    assert result == {"before": "src/old/Button", "after": "src/new/Button"}
    assert bridge_exports.resolveImport() == "resolveImport"


def test_compiler_resolver_bridge_import_resolution_invalidates_when_extended_jsonc_tsconfig_changes(
    tmp_path: Path,
) -> None:
    _require_typescript()
    bridge_exports = SimpleNamespace(resolveImport=lambda: "resolveImport")
    project_root = _bridge_project_with_jsonc_extends_alias(tmp_path)

    result = _run_node_expression(
        project_root,
        """
const before = bridge.resolveImport(ts, projectRoot, {
  command: 'resolveImport',
  specifier: '@ui/Button',
  importerModule: 'src/App.test'
});
const fs = require('fs');
const path = require('path');
fs.writeFileSync(
  path.join(projectRoot, 'tsconfig.base.json'),
  `{
    // JSONC syntax must still participate in cache invalidation.
    "compilerOptions": {
      "target": "ES2022",
      "module": "ESNext",
      "moduleResolution": "Bundler",
      "baseUrl": ".",
      "paths": { "@ui/*": ["src/new/*"] },
    },
  }`
);
const after = bridge.resolveImport(ts, projectRoot, {
  command: 'resolveImport',
  specifier: '@ui/Button',
  importerModule: 'src/App.test'
});
console.log(JSON.stringify({ before, after }));
""",
    )

    assert result == {"before": "src/old/Button", "after": "src/new/Button"}
    assert bridge_exports.resolveImport() == "resolveImport"


def test_compiler_resolver_bridge_import_resolution_keeps_missing_import_fail_closed(
    tmp_path: Path,
) -> None:
    _require_typescript()
    bridge_exports = SimpleNamespace(resolveImport=lambda: "resolveImport")
    project_root = _bridge_project(tmp_path)

    result = _run_node_expression(
        project_root,
        """
const resolved = bridge.resolveImport(ts, projectRoot, {
  command: 'resolveImport',
  specifier: '@/components/Missing',
  importerModule: 'src/App.test'
});
console.log(JSON.stringify(resolved));
""",
    )

    assert result is None
    assert bridge_exports.resolveImport() == "resolveImport"


def test_compiler_resolver_bridge_reexport_still_uses_program_backed_path(
    tmp_path: Path,
) -> None:
    _require_typescript()
    bridge_exports = SimpleNamespace(
        resolveReexport=lambda: "resolveReexport",
        loadProject=lambda: "loadProject",
    )
    project_root = _bridge_project(tmp_path)

    result = _run_node_expression(
        project_root,
        """
let createProgramCalls = 0;
const trackedTs = new Proxy(ts, {
  get(target, property, receiver) {
    if (property === 'createProgram') {
      return (...args) => {
        createProgramCalls += 1;
        return target.createProgram(...args);
      };
    }
    return Reflect.get(target, property, receiver);
  }
});
const resolved = bridge.resolveReexport(trackedTs, projectRoot, {
  command: 'resolveReexport',
  module: 'src/components',
  name: 'Button'
});
console.log(JSON.stringify({ resolved, createProgramCalls }));
""",
    )

    assert result == {
        "resolved": {"module": "src/components/Button", "name": "Button"},
        "createProgramCalls": 1,
    }
    assert {bridge_exports.resolveReexport(), bridge_exports.loadProject()} == {
        "resolveReexport",
        "loadProject",
    }


def _bridge_project(project_root: Path) -> Path:
    _write_json(
        project_root / "tsconfig.json",
        {
            "compilerOptions": {
                "target": "ES2022",
                "module": "ESNext",
                "moduleResolution": "Bundler",
                "baseUrl": ".",
                "paths": {"@/*": ["src/*"]},
            },
            "include": ["src/**/*"],
        },
    )
    src = project_root / "src"
    components = src / "components"
    components.mkdir(parents=True)
    (src / "App.test.ts").write_text(
        "import { Button } from '@/components/Button';\nButton();\n"
    )
    (components / "index.ts").write_text("export { Button } from './Button';\n")
    (components / "Button.ts").write_text("export function Button() {}\n")
    return project_root


def _bridge_project_with_switchable_alias(project_root: Path) -> Path:
    _write_json(
        project_root / "tsconfig.json",
        {
            "compilerOptions": {
                "target": "ES2022",
                "module": "ESNext",
                "moduleResolution": "Bundler",
                "baseUrl": ".",
                "paths": {"@ui/*": ["src/old/*"]},
            },
            "include": ["src/**/*"],
        },
    )
    src = project_root / "src"
    old = src / "old"
    new = src / "new"
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    (src / "App.test.ts").write_text(
        "import { Button } from '@ui/Button';\nButton();\n"
    )
    (old / "Button.ts").write_text("export function Button() {}\n")
    (new / "Button.ts").write_text("export function Button() {}\n")
    return project_root


def _bridge_project_with_jsonc_extends_alias(project_root: Path) -> Path:
    (project_root / "tsconfig.json").write_text(
        """{
  // The extending config itself uses JSONC syntax.
  "extends": "./tsconfig.base.json",
  "include": ["src/**/*"],
}
"""
    )
    (project_root / "tsconfig.base.json").write_text(
        """{
  // JSONC syntax is accepted by TypeScript config parsing.
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "baseUrl": ".",
    "paths": { "@ui/*": ["src/old/*"] },
  },
}
"""
    )
    src = project_root / "src"
    old = src / "old"
    new = src / "new"
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    (src / "App.test.ts").write_text(
        "import { Button } from '@ui/Button';\nButton();\n"
    )
    (old / "Button.ts").write_text("export function Button() {}\n")
    (new / "Button.ts").write_text("export function Button() {}\n")
    return project_root


def _run_bridge(payload: dict[str, object]) -> object:
    completed = subprocess.run(
        ["node", str(_bridge_path())],
        input=json.dumps(payload),
        check=True,
        capture_output=True,
        text=True,
    )
    response = json.loads(completed.stdout)
    assert response["ok"] is True
    return response["result"]


def _run_node_expression(project_root: Path, expression: str) -> object:
    script = (
        f"const bridge = require({json.dumps(str(_bridge_path()))});\n"
        "const ts = require('typescript');\n"
        f"const projectRoot = {json.dumps(str(project_root))};\n"
        f"{expression}"
    )
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _bridge_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "maid_runner"
        / "core"
        / "ts_compiler_resolver.cjs"
    )
