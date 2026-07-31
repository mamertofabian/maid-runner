from __future__ import annotations

from pathlib import Path


def test_base_validator_defaults_preserve_existing_plugin_compatibility() -> None:
    from maid_runner.core.types import ArtifactKind
    from maid_runner.validators.base import (
        BaseValidator,
        CollectionResult,
        ComplexityResult,
        DependencyCollectionResult,
        FoundArtifact,
    )

    class ExistingPlugin(BaseValidator):
        @classmethod
        def supported_extensions(cls) -> tuple[str, ...]:
            return (".custom",)

        def collect_implementation_artifacts(self, source, file_path):
            return CollectionResult(
                [FoundArtifact(kind=ArtifactKind.FUNCTION, name="run")],
                "custom",
                str(file_path),
            )

        def collect_behavioral_artifacts(self, source, file_path):
            return CollectionResult([], "custom", str(file_path))

    validator = ExistingPlugin()
    dependencies = validator.collect_dependencies("", "src/app.custom", Path("."))
    complexity = validator.collect_complexity("", "src/app.custom")

    assert isinstance(dependencies, DependencyCollectionResult)
    assert dependencies.modules == ()
    assert dependencies.unresolved == ()
    assert dependencies.errors == ()
    assert dependencies.supported is False
    assert isinstance(complexity, ComplexityResult)
    assert complexity.logical_lines is None
    assert complexity.decision_points is None
    assert complexity.largest_definition_lines is None
    assert complexity.public_artifacts is None
    assert complexity.errors == ()
    assert complexity.supported is False


def test_python_validator_collects_resolved_dependencies_and_complexity(
    tmp_path: Path,
) -> None:
    from maid_runner.validators.python import PythonValidator

    source = """
from src.dep import value

def choose(flag: bool) -> int:
    if flag:
        return value
    return 0
""".lstrip()
    validator = PythonValidator()

    dependencies = validator.collect_dependencies(
        source,
        "src/app.py",
        tmp_path,
    )
    complexity = validator.collect_complexity(source, "src/app.py")

    assert dependencies.supported is True
    assert dependencies.modules == ("src.dep",)
    assert dependencies.unresolved == ()
    assert dependencies.errors == ()
    assert complexity.supported is True
    assert complexity.logical_lines == 5
    assert complexity.decision_points == 1
    assert complexity.largest_definition_lines == 4
    assert complexity.public_artifacts == 1
    assert complexity.errors == ()


def test_typescript_and_svelte_hooks_return_language_aware_results(
    tmp_path: Path,
) -> None:
    from maid_runner.validators.svelte import SvelteValidator
    from maid_runner.validators.typescript import TypeScriptValidator

    typescript = TypeScriptValidator()
    ts_dependencies = typescript.collect_dependencies(
        "import { dep } from './dep';\nexport function run() { return dep ? 1 : 0; }\n",
        "src/app.ts",
        tmp_path,
    )
    ts_complexity = typescript.collect_complexity(
        "export function run() { return true ? 1 : 0; }\n",
        "src/app.ts",
    )

    svelte = SvelteValidator()
    svelte_dependencies = svelte.collect_dependencies(
        "<script>import { dep } from './dep';</script>\n<p>{dep}</p>\n",
        "src/App.svelte",
        tmp_path,
    )
    svelte_complexity = svelte.collect_complexity(
        "<script>let value = true ? 1 : 0;</script>\n<p>{value}</p>\n",
        "src/App.svelte",
    )

    assert ts_dependencies.modules == ("src/dep",)
    assert ts_dependencies.supported is True
    assert ts_complexity.supported is True
    assert ts_complexity.decision_points == 1
    assert svelte_dependencies.modules == ("src/dep",)
    assert svelte_dependencies.supported is True
    assert svelte_complexity.supported is True
    assert svelte_complexity.decision_points == 1


def test_risk_v1_signals_stay_pinned_after_hook_delegation(tmp_path: Path) -> None:
    from maid_runner.core.coverage_recommendation import recommend_coverage

    target = tmp_path / "src" / "target.py"
    target.parent.mkdir()
    target.write_text("def target(flag: bool):\n    return 1 if flag else 0\n")
    importer = tmp_path / "src" / "importer.py"
    importer.write_text(
        "from src.target import target\n\ndef use():\n    return target(True)\n"
    )

    report = recommend_coverage(tmp_path)
    recommendation = next(
        item for item in report.candidates if item.path == "src/target.py"
    )
    signals = {signal.name: signal for signal in recommendation.signals}

    assert signals["direct_dependents"].raw_value == 1
    assert signals["public_artifacts"].raw_value == 1
    assert signals["complexity"].raw_value == (
        "logical_lines=2; decision_points=1; "
        "largest_definition_lines=2; public_artifacts=1"
    )


def test_python_from_package_import_resolves_submodule_dependency(
    tmp_path: Path,
) -> None:
    from maid_runner.core.coverage_recommendation import recommend_coverage

    package = tmp_path / "src"
    package.mkdir()
    (package / "dep.py").write_text("def dep():\n    return 1\n")
    (package / "consumer.py").write_text(
        "from src import dep\n\ndef consume():\n    return dep.dep()\n"
    )

    report = recommend_coverage(tmp_path)
    recommendation = next(
        item for item in report.candidates if item.path == "src/dep.py"
    )
    direct = next(
        signal
        for signal in recommendation.signals
        if signal.name == "direct_dependents"
    )

    assert direct.raw_value == 1


def test_registered_extensions_are_discovered_by_recommender(tmp_path: Path) -> None:
    from maid_runner.core.coverage_recommendation import recommend_coverage

    source = tmp_path / "src" / "module.mts"
    source.parent.mkdir()
    source.write_text("export function run() { return 1; }\n")

    report = recommend_coverage(tmp_path)

    assert "src/module.mts" in {item.path for item in report.candidates}


def test_python_package_initializer_resolves_relative_submodule(
    tmp_path: Path,
) -> None:
    from maid_runner.core.coverage_recommendation import recommend_coverage

    package = tmp_path / "src"
    package.mkdir()
    (package / "__init__.py").write_text("from . import dep\n\nVALUE = dep.dep()\n")
    (package / "dep.py").write_text("def dep():\n    return 1\n")

    report = recommend_coverage(tmp_path)
    recommendation = next(
        item for item in report.candidates if item.path == "src/dep.py"
    )
    direct = next(
        signal
        for signal in recommendation.signals
        if signal.name == "direct_dependents"
    )

    assert direct.raw_value == 1


def test_python_mixed_package_import_retains_base_and_submodule_edges(
    tmp_path: Path,
) -> None:
    from maid_runner.core.coverage_recommendation import recommend_coverage

    package = tmp_path / "src"
    package.mkdir()
    (package / "__init__.py").write_text("VALUE = 1\n")
    (package / "dep.py").write_text("def dep():\n    return 1\n")
    (package / "consumer.py").write_text(
        "from src import dep, VALUE\n\nRESULT = dep.dep() + VALUE\n"
    )

    report = recommend_coverage(tmp_path)
    recommendations = {item.path: item for item in report.candidates}

    assert (
        next(
            signal
            for signal in recommendations["src/dep.py"].signals
            if signal.name == "direct_dependents"
        ).raw_value
        == 1
    )
    assert (
        next(
            signal
            for signal in recommendations["src/__init__.py"].signals
            if signal.name == "direct_dependents"
        ).raw_value
        == 1
    )


def test_plugin_module_identity_builds_dependency_edges(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from maid_runner.core.coverage_recommendation import recommend_coverage
    from maid_runner.core.types import ArtifactKind
    from maid_runner.validators.base import (
        BaseValidator,
        CollectionResult,
        ComplexityResult,
        DependencyCollectionResult,
        FoundArtifact,
    )
    from maid_runner.validators.registry import ValidatorRegistry

    class CustomValidator(BaseValidator):
        @classmethod
        def supported_extensions(cls) -> tuple[str, ...]:
            return (".custom",)

        def collect_implementation_artifacts(self, source, file_path):
            return CollectionResult(
                [FoundArtifact(kind=ArtifactKind.FUNCTION, name="run")],
                "custom",
                str(file_path),
            )

        def collect_behavioral_artifacts(self, source, file_path):
            return CollectionResult([], "custom", str(file_path))

        def module_path(self, file_path, project_root):
            return Path(file_path).with_suffix("").as_posix()

        def collect_dependencies(self, source, file_path, project_root):
            modules = tuple(
                line.removeprefix("import:").strip()
                for line in source.splitlines()
                if line.startswith("import:")
            )
            return DependencyCollectionResult(modules=modules)

        def collect_complexity(self, source, file_path):
            return ComplexityResult(
                logical_lines=1,
                decision_points=0,
                largest_definition_lines=1,
                public_artifacts=1,
            )

    registry = ValidatorRegistry()
    registry.register(CustomValidator)
    monkeypatch.setattr(
        ValidatorRegistry,
        "with_builtin_validators",
        classmethod(lambda cls: registry),
    )
    source = tmp_path / "src"
    source.mkdir()
    (source / "target.custom").write_text("run\n")
    (source / "consumer.custom").write_text("import:src/target\n")

    report = recommend_coverage(tmp_path)
    recommendation = next(
        item for item in report.candidates if item.path == "src/target.custom"
    )
    direct = next(
        signal
        for signal in recommendation.signals
        if signal.name == "direct_dependents"
    )

    assert direct.raw_value == 1
