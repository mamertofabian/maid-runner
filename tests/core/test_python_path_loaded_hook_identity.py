"""Exact path identity for bounded standard importlib loader helpers."""

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine
from maid_runner.validators.python import PythonValidator


_POSITIVE = [
    "literal",
    "file_parents",
    "repo_root",
    "import_aliases",
    "bound_hook",
    "unittest",
    "caller_local_shadow",
    "ordinary_package",
    "dotted_directory",
    "legacy_literal_loader",
    "hidden_skill_import",
]
_NEGATIVE = [
    "other_file",
    "dynamic_path",
    "shadowed_importlib",
    "shadowed_path",
    "decorated_helper",
    "helper_rebound",
    "root_rebound",
    "local_helper_alias",
    "extra_helper_statement",
    "caller_import_with_shadowed_global",
    "ancestor_escape",
    "file_rebound",
    "global_file_rebind",
    "global_loader_rebind",
    "global_path_rebind",
    "package_cannot_cover_dotted_file",
    "dotted_file_cannot_cover_package",
    "ordinary_package_import",
    "ordinary_directory_cannot_cover_dotted_directory",
    "restored_path_import",
]


def _source(scenario: str) -> str:
    imports = "import importlib.util\nfrom pathlib import Path\n"
    root = "REPO_ROOT = Path(__file__).resolve().parent.parent\n"
    spec = 'importlib.util.spec_from_file_location("arbitrary_runtime_name", REPO_ROOT / "gunicorn.conf.py")'
    module = "importlib.util.module_from_spec(spec)"
    extra = ""
    prefix = ""
    decorator = ""
    tail = ""
    if scenario == "literal":
        spec = 'importlib.util.spec_from_file_location("arbitrary_runtime_name", "gunicorn.conf.py")'
    elif scenario == "file_parents":
        spec = 'importlib.util.spec_from_file_location("arbitrary_runtime_name", Path(__file__).resolve().parents[1] / "gunicorn.conf.py")'
    elif scenario == "import_aliases":
        imports = "from importlib.util import spec_from_file_location as make_spec, module_from_spec as make_module\nfrom pathlib import Path as P\n"
        root = "REPO_ROOT = P(__file__).resolve().parent.parent\n"
        spec = 'make_spec("arbitrary_runtime_name", REPO_ROOT / "gunicorn.conf.py")'
        module = "make_module(spec)"
    elif scenario == "other_file":
        spec = 'importlib.util.spec_from_file_location("gunicorn.conf", REPO_ROOT / "other.conf.py")'
    elif scenario == "dynamic_path":
        prefix = 'def _target():\n    return REPO_ROOT / "gunicorn.conf.py"\n'
        spec = 'importlib.util.spec_from_file_location("arbitrary_runtime_name", _target())'
    elif scenario in {"shadowed_importlib", "caller_import_with_shadowed_global"}:
        root += "from types import SimpleNamespace\n_actual_util = importlib.util\nimportlib = SimpleNamespace(util=_actual_util)\n"
    elif scenario == "shadowed_path":
        imports += 'Path = lambda value: __import__("pathlib").Path(value)\n'
    elif scenario == "decorated_helper":
        prefix = "def _decorate(fn):\n    return fn\n"
        decorator = "@_decorate\n"
    elif scenario == "helper_rebound":
        tail = "_actual_loader = _load\n_load = _actual_loader\n"
    elif scenario == "root_rebound":
        root += "REPO_ROOT = REPO_ROOT\n"
    elif scenario == "extra_helper_statement":
        extra = "    module.extra = True\n"
    if scenario == "ancestor_escape":
        spec = 'importlib.util.spec_from_file_location("arbitrary_runtime_name", Path(__file__).resolve().parent.parent.parent / "gunicorn.conf.py")'
    elif scenario == "file_rebound":
        imports += '_saved_file = __file__\n__file__ = str(Path(__file__).resolve().parent.parent / "other/tests/test_hook.py")\n'
        root += "__file__ = _saved_file\n"
    elif scenario == "global_file_rebind":
        imports += '_saved_file = __file__\ndef _retarget_file():\n    global __file__\n    __file__ = str(Path(_saved_file).resolve().parent.parent / "other/tests/test_hook.py")\ndef _restore_file():\n    global __file__\n    __file__ = _saved_file\n_retarget_file()\n'
        root += "_restore_file()\n"
    elif scenario == "global_loader_rebind":
        imports += 'from types import SimpleNamespace\n_real_util = importlib.util\ndef _redirect_spec(label, path):\n    return _real_util.spec_from_file_location(label, REPO_ROOT / "other/gunicorn.conf.py")\ndef _retarget_loader():\n    global importlib\n    importlib = SimpleNamespace(util=SimpleNamespace(spec_from_file_location=_redirect_spec, module_from_spec=_real_util.module_from_spec))\n_retarget_loader()\n'
    elif scenario == "global_path_rebind":
        imports += '_real_path = Path\ndef _retarget_path():\n    global Path\n    Path = lambda value: _real_path(__file__).resolve().parent.parent / "other/tests/test_hook.py"\n_retarget_path()\n'
    elif scenario == "package_cannot_cover_dotted_file":
        spec = 'importlib.util.spec_from_file_location("gunicorn.conf", REPO_ROOT / "gunicorn/conf.py")'
    if scenario == "dotted_directory":
        spec = 'importlib.util.spec_from_file_location("arbitrary_runtime_name", REPO_ROOT / "a.b/conf.py")'
    elif scenario == "ordinary_directory_cannot_cover_dotted_directory":
        spec = 'importlib.util.spec_from_file_location("a.b.conf", REPO_ROOT / "a/b/conf.py")'
    if scenario == "restored_path_import":
        imports += '_real_path = Path\nPath = lambda value: _real_path(__file__).resolve().parent.parent / "other/tests/test_hook.py"\n'
        root += "from pathlib import Path\n"
    if scenario == "hidden_skill_import":
        return 'import sys\nfrom pathlib import Path\nSCRIPTS_DIR = Path(__file__).resolve().parent.parent / ".codex/skills/demo-skill/scripts"\nsys.path.insert(0, str(SCRIPTS_DIR))\nfrom hook_module import post_worker_init\n\ndef test_hook():\n    worker = []\n    post_worker_init(worker)\n    assert worker == ["ready"]\n'
    if scenario == "legacy_literal_loader":
        return 'import importlib.util\n\ndef load_module(module_name, relative_path):\n    spec = importlib.util.spec_from_file_location(module_name, relative_path)\n    module = importlib.util.module_from_spec(spec)\n    spec.loader.exec_module(module)\n    return module\n\nconf = load_module("speak_summary", "hooks.v2/speak-summary.py")\n\ndef test_hook():\n    worker = []\n    conf.post_worker_init(worker)\n    assert worker == ["ready"]\n'
    if scenario in {"ordinary_package", "ordinary_package_import"}:
        return 'from gunicorn.conf import post_worker_init\n\ndef test_hook():\n    worker = []\n    post_worker_init(worker)\n    assert worker == ["ready"]\n'
    helper = (
        decorator
        + "def _load():\n"
        + f"    spec = {spec}\n"
        + f"    module = {module}\n"
        + "    spec.loader.exec_module(module)\n"
        + extra
        + "    return module\n"
    )
    body = "    conf = _load()\n    worker = []\n"
    if scenario == "caller_local_shadow":
        body = "    importlib = Path = REPO_ROOT = object()\n" + body
    elif scenario == "caller_import_with_shadowed_global":
        body = "    import importlib.util\n" + body
    if scenario == "local_helper_alias":
        tail += "_actual_loader = _load\n"
        body = "    _load = _actual_loader\n" + body
    if scenario == "bound_hook":
        body += "    hook = conf.post_worker_init\n    hook(worker)\n"
    else:
        body += "    conf.post_worker_init(worker)\n"
    body += '    assert worker == ["ready"]\n'
    if scenario == "unittest":
        imports += "from unittest import TestCase\n"
        test = (
            "class HookTests(TestCase):\n    def test_hook(self):\n"
            + "\n".join("    " + line for line in body.splitlines())
            + "\n"
        )
    else:
        test = "def test_hook():\n" + body
    return imports + root + "\n" + prefix + helper + tail + "\n" + test


def _target_path(scenario: str) -> str:
    if scenario == "hidden_skill_import":
        return ".codex/skills/demo-skill/scripts/hook_module.py"
    if scenario == "legacy_literal_loader":
        return "hooks.v2/speak-summary.py"
    if scenario in {"ordinary_package", "dotted_file_cannot_cover_package"}:
        return "gunicorn/conf.py"
    if scenario in {
        "dotted_directory",
        "ordinary_directory_cannot_cover_dotted_directory",
    }:
        return "a.b/conf.py"
    return "gunicorn.conf.py"


def _project(root: Path, scenario: str) -> tuple[Path, str]:
    workspace = root
    root = workspace / "project"
    root.mkdir()
    (root / "tests").mkdir()
    (root / "manifests").mkdir()
    implementation = 'def post_worker_init(worker):\n    worker.append("ready")\n'
    (root / "gunicorn.conf.py").write_text(implementation)
    (root / "other.conf.py").write_text(implementation)
    (workspace / "gunicorn.conf.py").write_text(implementation)
    (root / "other/tests").mkdir(parents=True)
    (root / "other/gunicorn.conf.py").write_text(implementation)
    (root / "gunicorn").mkdir()
    (root / "gunicorn/__init__.py").write_text("")
    (root / "gunicorn/conf.py").write_text(implementation)
    (root / "a.b").mkdir()
    (root / "a.b/conf.py").write_text(implementation)
    (root / "hooks.v2").mkdir()
    (root / "hooks.v2/speak-summary.py").write_text(implementation)
    (root / ".codex/skills/demo-skill/scripts").mkdir(parents=True)
    (root / ".codex/skills/demo-skill/scripts/hook_module.py").write_text(
        implementation
    )
    (root / "a/b").mkdir(parents=True)
    (root / "a/__init__.py").write_text("")
    (root / "a/b/__init__.py").write_text("")
    (root / "a/b/conf.py").write_text(implementation)
    source = _source(scenario)
    (root / "tests/test_hook.py").write_text(source)
    manifest = {
        "schema": "2",
        "goal": "Cover exact path-loaded hook",
        "files": {
            "edit": [
                {
                    "path": _target_path(scenario),
                    "artifacts": [
                        {
                            "kind": "function",
                            "name": "post_worker_init",
                            "args": [{"name": "worker", "type": "Any"}],
                            "returns": "Any",
                        }
                    ],
                }
            ],
            "read": ["tests/test_hook.py"],
        },
        "validate": [["pytest", "tests/test_hook.py", "-q"]],
    }
    path = root / "manifests/hook.manifest.yaml"
    path.write_text(yaml.safe_dump(manifest))
    executed = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_hook.py", "-q"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert executed.returncode == 0, executed.stdout + executed.stderr
    return path, source


@pytest.mark.parametrize("scenario", _POSITIVE)
def test_standard_loader_helper_records_exact_file_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    manifest, source = _project(tmp_path, scenario)
    monkeypatch.chdir(manifest.parent.parent)
    result = PythonValidator().collect_behavioral_artifacts(
        source, "tests/test_hook.py"
    )
    assert not result.errors
    references = [
        artifact for artifact in result.artifacts if artifact.name == "post_worker_init"
    ]
    target = _target_path(scenario)
    expected = (
        "hook_module"
        if scenario == "hidden_skill_import"
        else PythonValidator().module_path(target, manifest.parent.parent)
    )
    assert any(reference.import_source == expected for reference in references)
    assert all(
        reference.import_source != "arbitrary_runtime_name" for reference in references
    )


@pytest.mark.parametrize("scenario", _POSITIVE)
def test_executed_path_loaded_hook_satisfies_public_behavioral_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    manifest, _ = _project(tmp_path, scenario)
    monkeypatch.chdir(manifest.parent.parent)
    result = ValidationEngine(project_root=manifest.parent.parent).validate(
        manifest, mode=ValidationMode.BEHAVIORAL
    )
    assert result.success, [error.message for error in result.errors]


@pytest.mark.parametrize("scenario", _NEGATIVE)
def test_unproven_or_different_loader_identity_does_not_cover_declared_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    manifest, source = _project(tmp_path, scenario)
    monkeypatch.chdir(manifest.parent.parent)
    collected = PythonValidator().collect_behavioral_artifacts(
        source, "tests/test_hook.py"
    )
    assert not collected.errors
    target = _target_path(scenario)
    expected = PythonValidator().module_path(target, manifest.parent.parent)
    assert not any(
        artifact.name == "post_worker_init" and artifact.import_source == expected
        for artifact in collected.artifacts
    )
    result = ValidationEngine(project_root=manifest.parent.parent).validate(
        manifest, mode=ValidationMode.BEHAVIORAL
    )
    assert any(
        error.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS for error in result.errors
    )


@pytest.mark.parametrize(
    "expression",
    [
        "Path(__file__).resolve().parents[-1] / 'gunicorn.conf.py'",
        "Path(__file__).resolve().parent.parent.parent.parent / 'gunicorn.conf.py'",
    ],
)
def test_outside_ancestry_remains_unproven(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, expression: str
) -> None:
    monkeypatch.chdir(tmp_path)
    source = _source("repo_root").replace('REPO_ROOT / "gunicorn.conf.py"', expression)
    collected = PythonValidator().collect_behavioral_artifacts(
        source, "tests/test_hook.py"
    )
    expected = PythonValidator().module_path("gunicorn.conf.py", tmp_path)
    assert not collected.errors
    assert not any(
        artifact.name == "post_worker_init" and artifact.import_source == expected
        for artifact in collected.artifacts
    )


def test_dotted_file_identity_is_distinct_from_normal_package_identity(
    tmp_path: Path,
) -> None:
    validator = PythonValidator()
    assert (
        validator.module_path(tmp_path / "gunicorn/conf.py", tmp_path)
        == "gunicorn.conf"
    )
    assert (
        validator.module_path(tmp_path / "gunicorn.conf.py", tmp_path)
        != "gunicorn.conf"
    )
    assert validator.module_path(
        tmp_path / "gunicorn.conf.py", tmp_path
    ) == validator.module_path("gunicorn.conf.py", tmp_path)

    assert validator.module_path(tmp_path / "a/b/conf.py", tmp_path) == "a.b.conf"
    assert validator.module_path(
        tmp_path / "a.b/conf.py", tmp_path
    ) != validator.module_path(tmp_path / "a/b/conf.py", tmp_path)

    assert (
        validator.module_path(
            ".codex/skills/demo-skill/scripts/hook_module.py", tmp_path
        )
        == ".codex.skills.demo-skill.scripts.hook_module"
    )
