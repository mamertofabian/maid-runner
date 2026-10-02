"""Rust discovery and Cargo command integrity through public Runner behavior."""

import shutil

import pytest

from maid_runner.core._file_discovery import discover_source_files, is_test_file
from maid_runner.core._validation_test_artifacts import (
    collect_test_artifacts,
    find_test_files,
    get_cached_test_artifacts,
    validate_manifest_test_commands,
)
from maid_runner.core._test_command_targets import (
    test_files_covered_by_validate_command as covered_test_files,
)
from maid_runner.core.manifest import load_manifest
from maid_runner.validators.base import (
    BaseValidator,
    CollectionResult,
    DependencyCollectionResult,
    FoundArtifact,
)
from maid_runner.validators.registry import ValidatorRegistry


class _RustValidator(BaseValidator):
    @classmethod
    def supported_extensions(cls):
        return (".rs",)

    def collect_implementation_artifacts(self, source, file_path):
        return CollectionResult([], "rust", str(file_path))

    def collect_behavioral_artifacts(self, source, file_path):
        return CollectionResult(
            [FoundArtifact(kind="function", name="render")], "rust", str(file_path)
        )

    def get_test_function_bodies(self, source, file_path):
        return {"checks": "render();"} if "#[test]" in source else {}

    def collect_dependencies(self, source, file_path, project_root):
        return DependencyCollectionResult(
            modules=("src/math.rs",) if "mod math;" in source else ()
        )


@pytest.fixture
def rust_project(tmp_path, monkeypatch):
    if shutil.which("cargo") is None:
        pytest.skip("Cargo is required for real metadata target resolution")
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname="demo"\nversion="0.1.0"\nedition="2021"\n'
    )
    (tmp_path / "src/lib.rs").write_text(
        "pub fn render() {}\nmod math;\n#[cfg(test)] mod tests { #[test] fn checks() { super::render(); } }"
    )
    (tmp_path / "src/math.rs").write_text("#[test] fn checks_math() {}")
    (tmp_path / "src/unused.rs").write_text("#[test] fn never_loaded() {}")
    (tmp_path / "tests/render.rs").write_text("#[test] fn checks() { demo::render(); }")
    registry = ValidatorRegistry()
    registry.register(_RustValidator)
    monkeypatch.setattr(
        ValidatorRegistry, "with_builtin_validators", classmethod(lambda cls: registry)
    )
    return tmp_path, registry


def _manifest(root, commands, paths=("src/lib.rs", "tests/render.rs")):
    path = root / "manifests/rust.manifest.yaml"
    path.parent.mkdir(exist_ok=True)
    import yaml

    path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "type": "feature",
                "goal": "Exercise Rust tests",
                "created": "2026-10-02T00:00:00Z",
                "files": {
                    "edit": [
                        {
                            "path": "src/lib.rs",
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "render",
                                    "args": [],
                                    "returns": "()",
                                }
                            ],
                        }
                    ],
                    "read": list(paths),
                },
                "validate": [list(cmd) for cmd in commands],
            }
        )
    )
    return load_manifest(path)


def test_default_source_discovery_includes_rust_and_excludes_cargo_output(tmp_path):
    for path in ("src/lib.rs", "tests/render.rs", "target/debug/build/generated.rs"):
        full = tmp_path / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text("")
    assert discover_source_files(tmp_path) == ["src/lib.rs", "tests/render.rs"]
    assert is_test_file("tests/render.rs")
    assert not is_test_file("src/lib.rs")
    assert not is_test_file("src/contest.rs")


def test_inline_and_integration_tests_reach_plugin_collection(rust_project):
    root, registry = rust_project
    manifest = _manifest(root, [("cargo", "test")])
    files = find_test_files(manifest, root)
    assert "src/lib.rs" in files
    assert "tests/render.rs" in files
    errors = []
    collected = collect_test_artifacts(files, root, registry, errors)
    assert errors == []
    assert collected["src/lib.rs"][0].name == "render"


def test_inline_discovery_changes_when_source_gains_a_test(rust_project):
    root, _ = rust_project
    manifest = _manifest(root, [("cargo", "test")], ("src/math.rs",))
    (root / "src/math.rs").write_text("pub fn add() {}")
    assert "src/math.rs" not in find_test_files(manifest, root)
    (root / "src/math.rs").write_text("#[test] fn checks() {}")
    assert "src/math.rs" in find_test_files(manifest, root)


def test_cargo_test_covers_only_loaded_target_modules(rust_project):
    root, _ = rust_project
    files = ["src/lib.rs", "src/math.rs", "src/unused.rs", "tests/render.rs"]
    assert covered_test_files(("cargo", "test"), files, root) == {
        "src/lib.rs",
        "src/math.rs",
        "tests/render.rs",
    }

    assert (
        validate_manifest_test_commands(_manifest(root, [("cargo", "test")]), root)
        == []
    )


def test_all_targets_does_not_credit_build_script_test_attributes(rust_project):
    root, _ = rust_project
    (root / "build.rs").write_text("fn main() {} #[test] fn unexecuted() {}")
    assert (
        covered_test_files(("cargo", "test", "--all-targets"), ["build.rs"], root)
        == set()
    )


@pytest.mark.parametrize("selector", ["demo@0.1.0", "demo:0.1.0"])
def test_version_qualified_cargo_package_selectors_match_metadata(
    rust_project, selector
):
    root, _ = rust_project
    assert covered_test_files(
        ("cargo", "test", "-p", selector), ["src/lib.rs"], root
    ) == {"src/lib.rs"}
    assert (
        covered_test_files(
            ("cargo", "test", "-p", selector.replace("0.1.0", "0.2.0")),
            ["src/lib.rs"],
            root,
        )
        == set()
    )


@pytest.mark.parametrize(
    "args,expected",
    [
        (("--lib",), {"src/lib.rs", "src/math.rs"}),
        (("--test", "render"), {"tests/render.rs"}),
        (("--test=render",), {"tests/render.rs"}),
        (("--tests",), {"src/lib.rs", "src/math.rs", "tests/render.rs"}),
        (("--", "--nocapture"), {"src/lib.rs", "src/math.rs", "tests/render.rs"}),
    ],
)
def test_cargo_target_selectors_resolve_actual_metadata(rust_project, args, expected):
    root, _ = rust_project
    files = ["src/lib.rs", "src/math.rs", "tests/render.rs"]
    assert covered_test_files(("cargo", "test", *args), files, root) == expected


@pytest.mark.parametrize(
    "command",
    [
        ("cargo", "build"),
        ("cargo", "check"),
        ("cargo", "test", "--no-run"),
        ("cargo", "test", "--help"),
        ("cargo", "test", "checks"),
        ("cargo", "test", "--", "--list"),
        ("cargo", "test", "--", "--ignored"),
        ("cargo", "test", "--", "--skip", "checks"),
        ("cargo", "test", "--doc"),
        ("cargo", "test", "--test", "missing"),
        ("cargo", "test", "--config", "build.rustflags=[]"),
        ("cargo", "test", "--manifest-path", "../Cargo.toml"),
    ],
)
def test_nonexecuting_filtered_or_unresolved_cargo_commands_do_not_prove_coverage(
    rust_project, command
):
    root, _ = rust_project
    assert covered_test_files(command, ["src/lib.rs", "tests/render.rs"], root) == set()
    assert validate_manifest_test_commands(_manifest(root, [command]), root)


def test_wrong_cargo_target_does_not_cover_inline_unit_tests(rust_project):
    root, _ = rust_project
    assert validate_manifest_test_commands(
        _manifest(root, [("cargo", "test", "--test", "render")]), root
    )


def test_cargo_workspace_package_selection_does_not_cover_other_members(rust_project):
    root, _ = rust_project
    (root / "other/src").mkdir(parents=True)
    (root / "other/Cargo.toml").write_text(
        '[package]\nname="other"\nversion="0.1.0"\nedition="2021"\n'
    )
    (root / "other/src/lib.rs").write_text("#[test] fn other() {}")
    with (root / "Cargo.toml").open("a") as stream:
        stream.write('\n[workspace]\nmembers=["other"]\n')
    files = ["src/lib.rs", "other/src/lib.rs"]
    assert covered_test_files(("cargo", "test", "-p", "other"), files, root) == {
        "other/src/lib.rs"
    }
    assert covered_test_files(("cargo", "test", "--workspace"), files, root) == set(
        files
    )


def test_cargo_shell_working_directory_and_custom_test_path(rust_project):
    root, _ = rust_project
    (root / "nested/src").mkdir(parents=True)
    (root / "nested/checks").mkdir()
    (root / "nested/src/lib.rs").write_text("pub fn f() {}")
    (root / "nested/checks/custom.rs").write_text("#[test] fn checks() {}")
    (root / "nested/Cargo.toml").write_text(
        '[package]\nname="nested"\nversion="0.1.0"\nedition="2021"\n[[test]]\nname="custom"\npath="checks/custom.rs"\n'
    )
    command = ("bash", "-c", "cd nested && cargo test --test custom")
    assert covered_test_files(
        command, ["nested/checks/custom.rs", "src/lib.rs"], root
    ) == {"nested/checks/custom.rs"}


def test_module_uncertainty_does_not_prove_cargo_execution(rust_project, monkeypatch):
    root, _ = rust_project
    monkeypatch.setattr(
        _RustValidator,
        "collect_dependencies",
        lambda self, source, file_path, project_root: DependencyCollectionResult(
            unresolved=("cfg requires compiler evidence",)
        ),
    )
    assert (
        covered_test_files(("cargo", "test"), ["src/lib.rs", "tests/render.rs"], root)
        == set()
    )


def test_inline_directory_discovery_invalidates_when_source_changes(rust_project):
    root, _ = rust_project
    manifest = _manifest(root, [("cargo", "test")], ("src",))
    (root / "src/math.rs").write_text("pub fn math() {}")
    assert "src/math.rs" not in find_test_files(manifest, root)
    (root / "src/math.rs").write_text("#[test] fn checks_math() {}")
    assert "src/math.rs" in find_test_files(manifest, root)


def test_cargo_does_not_credit_inactive_required_feature_targets(rust_project):
    root, _ = rust_project
    (root / "tests/hidden.rs").write_text("#[test] fn hidden() {}")
    with (root / "Cargo.toml").open("a") as stream:
        stream.write(
            '\n[features]\nextra=[]\n[[test]]\nname="hidden"\nrequired-features=["extra"]\n'
        )
    assert covered_test_files(("cargo", "test"), ["tests/hidden.rs"], root) == set()
    assert (
        covered_test_files(
            ("cargo", "test", "--test", "hidden"), ["tests/hidden.rs"], root
        )
        == set()
    )


def test_cargo_default_required_features_can_enable_a_target(rust_project):
    root, _ = rust_project
    (root / "tests/hidden.rs").write_text("#[test] fn hidden() {}")
    with (root / "Cargo.toml").open("a") as stream:
        stream.write(
            '\n[features]\ndefault=["extra"]\nextra=[]\n[[test]]\nname="hidden"\nrequired-features=["extra"]\n'
        )
    assert covered_test_files(
        ("cargo", "test", "--test", "hidden"), ["tests/hidden.rs"], root
    ) == {"tests/hidden.rs"}


def test_cargo_custom_harness_is_not_ordinary_test_execution(rust_project):
    root, _ = rust_project
    with (root / "Cargo.toml").open("a") as stream:
        stream.write('\n[[test]]\nname="render"\nharness=false\n')
    assert (
        covered_test_files(
            ("cargo", "test", "--test", "render"), ["tests/render.rs"], root
        )
        == set()
    )


def test_exact_plugin_references_require_matching_kind_and_owner():
    from maid_runner.core.identity import match_artifact_to_references
    from maid_runner.core.types import ArtifactKind
    from pathlib import Path

    declared = FoundArtifact(kind=ArtifactKind.METHOD, name="read", of="Widget")
    for reference in (
        FoundArtifact(
            kind=ArtifactKind.METHOD, name="read", of="Other", reference_context="exact"
        ),
        FoundArtifact(
            kind=ArtifactKind.ATTRIBUTE,
            name="read",
            of="Widget",
            reference_context="exact",
        ),
    ):
        assert not match_artifact_to_references(declared, [reference], Path("."))
    correct = FoundArtifact(
        kind=ArtifactKind.METHOD, name="read", of="Widget", reference_context="exact"
    )
    assert match_artifact_to_references(declared, [correct], Path("."))


def test_rust_collection_receives_project_absolute_source_context(
    rust_project, monkeypatch
):
    from pathlib import Path

    root, registry = rust_project

    def collect(self, source, file_path):
        errors = (
            []
            if Path(file_path).is_absolute()
            else ["Rust module context is unavailable"]
        )
        return CollectionResult(
            [FoundArtifact(kind="function", name="render")],
            "rust",
            str(file_path),
            errors,
        )

    monkeypatch.setattr(_RustValidator, "collect_behavioral_artifacts", collect)
    table = get_cached_test_artifacts("tests/render.rs", root, registry)
    assert table is not None
    assert table.errors == ()
    assert table.artifacts[0].name == "render"


def test_nonvirtual_workspace_uses_configured_default_members(rust_project):
    root, _ = rust_project
    (root / "member/src").mkdir(parents=True)
    (root / "member/Cargo.toml").write_text(
        '[package]\nname="member"\nversion="0.1.0"\nedition="2021"\n'
    )
    (root / "member/src/lib.rs").write_text("#[test] fn member() {}")
    with (root / "Cargo.toml").open("a") as stream:
        stream.write('\n[workspace]\nmembers=["member"]\ndefault-members=["member"]\n')
    assert covered_test_files(
        ("cargo", "test"), ["src/lib.rs", "member/src/lib.rs"], root
    ) == {"member/src/lib.rs"}


def test_explicit_library_selection_overrides_default_test_false(rust_project):
    root, _ = rust_project
    with (root / "Cargo.toml").open("a") as stream:
        stream.write("\n[lib]\ntest=false\n")
    assert covered_test_files(("cargo", "test", "--lib"), ["src/lib.rs"], root) == {
        "src/lib.rs"
    }
    assert covered_test_files(("cargo", "test"), ["src/lib.rs"], root) == set()


def test_default_cargo_execution_includes_test_enabled_examples(rust_project):
    root, _ = rust_project
    (root / "examples").mkdir()
    (root / "examples/demo.rs").write_text("#[test] fn demo() {}")
    with (root / "Cargo.toml").open("a") as stream:
        stream.write('\n[[example]]\nname="demo"\ntest=true\n')
    assert covered_test_files(("cargo", "test"), ["examples/demo.rs"], root) == {
        "examples/demo.rs"
    }


def test_named_workspace_target_only_needs_to_exist_in_one_selected_package(
    rust_project,
):
    root, _ = rust_project
    (root / "member/src").mkdir(parents=True)
    (root / "member/tests").mkdir()
    (root / "member/Cargo.toml").write_text(
        '[package]\nname="member"\nversion="0.1.0"\nedition="2021"\n'
    )
    (root / "member/src/lib.rs").write_text("")
    (root / "member/tests/api.rs").write_text("#[test] fn api() {}")
    with (root / "Cargo.toml").open("a") as stream:
        stream.write('\n[workspace]\nmembers=["member"]\n')
    assert covered_test_files(
        ("cargo", "test", "--workspace", "--test", "api"),
        ["member/tests/api.rs", "src/lib.rs"],
        root,
    ) == {"member/tests/api.rs"}


def test_tests_selector_respects_test_flags_and_includes_enabled_examples(rust_project):
    root, _ = rust_project
    (root / "src/main.rs").write_text("fn main() {} #[test] fn bin_test() {}")
    (root / "examples").mkdir()
    (root / "examples/demo.rs").write_text("#[test] fn example_test() {}")
    with (root / "Cargo.toml").open("a") as stream:
        stream.write(
            '\n[lib]\ntest=false\n[[bin]]\nname="demo"\ntest=false\n[[example]]\nname="demo"\ntest=true\n'
        )
    files = ["src/lib.rs", "src/main.rs", "examples/demo.rs", "tests/render.rs"]
    assert covered_test_files(("cargo", "test", "--tests"), files, root) == {
        "examples/demo.rs",
        "tests/render.rs",
    }
    assert covered_test_files(("cargo", "test", "--tests", "--lib"), files, root) == {
        "src/lib.rs",
        "examples/demo.rs",
        "tests/render.rs",
    }


def test_workspace_selection_still_rejects_unknown_package_specs(rust_project):
    root, _ = rust_project
    assert (
        covered_test_files(
            ("cargo", "test", "--workspace", "-p", "missing"), ["src/lib.rs"], root
        )
        == set()
    )


def test_default_dependency_feature_activation_enables_implicit_optional_feature(
    rust_project,
):
    root, _ = rust_project
    (root / "dependency/src").mkdir(parents=True)
    (root / "dependency/Cargo.toml").write_text(
        '[package]\nname="dep_feature"\nversion="0.1.0"\nedition="2021"\n[features]\nextra=[]\n'
    )
    (root / "dependency/src/lib.rs").write_text("")
    (root / "tests/feature.rs").write_text("#[test] fn feature() {}")
    with (root / "Cargo.toml").open("a") as stream:
        stream.write(
            '\n[dependencies]\ndep_feature={path="dependency",optional=true}\n[features]\ndefault=["dep_feature/extra"]\n[[test]]\nname="feature"\nrequired-features=["dep_feature"]\n'
        )
    assert covered_test_files(("cargo", "test"), ["tests/feature.rs"], root) == {
        "tests/feature.rs"
    }


def test_exact_module_identity_does_not_apply_python_source_root_equivalence():
    from pathlib import Path
    from maid_runner.core.identity import match_artifact_to_references
    from maid_runner.core.types import ArtifactKind

    declaration = FoundArtifact(
        kind=ArtifactKind.FUNCTION, name="run", module_path="demo"
    )
    foreign = FoundArtifact(
        kind=ArtifactKind.FUNCTION,
        name="run",
        import_source="src.demo",
        reference_context="exact",
    )
    assert not match_artifact_to_references(declaration, [foreign], Path("."))
    direct = FoundArtifact(
        kind=ArtifactKind.FUNCTION,
        name="run",
        import_source="demo",
        reference_context="exact",
    )
    assert match_artifact_to_references(declaration, [direct], Path("."))


def test_undefined_default_feature_does_not_enable_a_required_target(rust_project):
    root, _ = rust_project
    (root / "tests/api.rs").write_text("#[test] fn api() {}")
    with (root / "Cargo.toml").open("a") as stream:
        stream.write('\n[[test]]\nname="api"\nrequired-features=["default"]\n')
    assert covered_test_files(("cargo", "test"), ["tests/api.rs"], root) == set()


@pytest.mark.parametrize(
    "arguments",
    [
        ("--lib", "--lib"),
        ("--manifest-path", "Cargo.toml", "--manifest-path", "Cargo.toml"),
        ("--quiet", "--quiet"),
        ("-q", "--quiet"),
        ("--tests", "--tests"),
    ],
)
def test_repeated_cargo_singleton_options_do_not_prove_test_execution(
    rust_project, arguments
):
    root, _ = rust_project
    assert (
        covered_test_files(("cargo", "test", *arguments), ["src/lib.rs"], root) == set()
    )


def test_repeatable_cargo_package_and_target_options_remain_supported(rust_project):
    root, _ = rust_project
    assert covered_test_files(
        (
            "cargo",
            "test",
            "-p",
            "demo",
            "-p",
            "demo",
            "--test",
            "render",
            "--test",
            "render",
        ),
        ["tests/render.rs"],
        root,
    ) == {"tests/render.rs"}


@pytest.mark.parametrize(
    "arguments",
    [
        ("--nocapture", "--nocapture"),
        ("--show-output", "--show-output"),
        ("--test-threads=1", "--test-threads", "2"),
        ("--test-threads", "1", "--test-threads=2"),
    ],
)
def test_duplicate_rust_harness_options_do_not_prove_execution(rust_project, arguments):
    root, _ = rust_project
    assert (
        covered_test_files(("cargo", "test", "--", *arguments), ["src/lib.rs"], root)
        == set()
    )


@pytest.mark.parametrize(
    "arguments",
    [("--quiet", "--verbose"), ("-q", "-v"), ("--verbose", "-q"), ("-v", "--quiet")],
)
def test_conflicting_cargo_output_flags_do_not_prove_execution(rust_project, arguments):
    root, _ = rust_project
    assert (
        covered_test_files(("cargo", "test", *arguments), ["src/lib.rs"], root) == set()
    )


def test_identity_free_exact_reference_cannot_cover_a_resolved_module():
    from pathlib import Path
    from maid_runner.core.identity import match_artifact_to_references
    from maid_runner.core.types import ArtifactKind

    declaration = FoundArtifact(
        kind=ArtifactKind.FUNCTION, name="render", module_path="demo.math"
    )
    unresolved = FoundArtifact(
        kind=ArtifactKind.FUNCTION, name="render", reference_context="exact"
    )
    assert not match_artifact_to_references(declaration, [unresolved], Path("."))


def test_mixed_explicit_selectors_reject_inactive_required_binary(rust_project):
    root, _ = rust_project
    (root / "src/main.rs").write_text("fn main() {} #[test] fn binary() {}")
    with (root / "Cargo.toml").open("a") as stream:
        stream.write(
            '\n[features]\nextra=[]\n[[bin]]\nname="probe"\npath="src/main.rs"\nrequired-features=["extra"]\n'
        )
    assert (
        covered_test_files(
            ("cargo", "test", "--lib", "--bin", "probe"),
            ["src/lib.rs", "src/main.rs"],
            root,
        )
        == set()
    )


def test_mixed_explicit_selectors_reject_missing_library_targets(rust_project):
    root, _ = rust_project
    (root / "src/main.rs").write_text("fn main() {} #[test] fn binary() {}")
    (root / "Cargo.toml").write_text(
        '[package]\nname="demo"\nversion="0.1.0"\nedition="2021"\nautolib=false\n'
    )
    assert (
        covered_test_files(
            ("cargo", "test", "--lib", "--bin", "demo"), ["src/main.rs"], root
        )
        == set()
    )


def test_rust_implementation_collection_receives_project_context_and_refreshes(
    rust_project, monkeypatch
):
    from pathlib import Path
    from maid_runner.core.types import ArtifactKind
    from maid_runner.core.validate import validate

    root, _ = rust_project
    context = root / "owner-context.txt"
    context.write_text("()")

    class ContextRustValidator(_RustValidator):
        def collect_implementation_artifacts(self, source, file_path):
            path = Path(file_path)
            if not path.is_absolute():
                return CollectionResult([], "rust", str(file_path))
            return CollectionResult(
                [
                    FoundArtifact(
                        kind=ArtifactKind.FUNCTION,
                        name="render",
                        returns=(path.parent.parent / "owner-context.txt").read_text(),
                    )
                ],
                "rust",
                str(file_path),
            )

        def collect_behavioral_artifacts(self, source, file_path):
            return CollectionResult(
                [FoundArtifact(kind=ArtifactKind.FUNCTION, name="render")],
                "rust",
                str(file_path),
            )

    registry = ValidatorRegistry()
    registry.register(ContextRustValidator)
    monkeypatch.setattr(
        ValidatorRegistry, "with_builtin_validators", classmethod(lambda cls: registry)
    )
    _manifest(root, [("cargo", "test")])
    path = root / "manifests/rust.manifest.yaml"
    first = validate(path, project_root=root, mode="implementation", registry=registry)
    assert first.success, first.errors
    context.write_text("u32")
    second = validate(path, project_root=root, mode="implementation", registry=registry)
    assert not second.success
    assert any(error.code.value == "E302" for error in second.errors)


@pytest.mark.parametrize("surface", ["removal-validation", "supersession-audit"])
def test_rust_removal_checks_reject_still_present_project_qualified_methods(
    rust_project, monkeypatch, surface
):
    from dataclasses import replace
    from pathlib import Path

    import yaml
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.result import ErrorCode
    from maid_runner.core.supersession_audit import SupersessionAuditor
    from maid_runner.core.types import ArtifactKind, RemovedArtifactSpec
    from maid_runner.core.validate import ValidationEngine

    root, _ = rust_project
    source = root / "src/actions.rs"
    source.write_text("use super::model::Widget; impl Widget { pub fn run(&self) {} }")
    context = root / "owner-context.txt"
    context.write_text("absent")

    class ContextRustValidator(_RustValidator):
        def collect_implementation_artifacts(self, source, file_path):
            path = Path(file_path)
            present = context.read_text() == "present"
            owner = "crate::model::Widget" if path.is_absolute() else "Widget"
            return CollectionResult(
                (
                    [FoundArtifact(kind=ArtifactKind.METHOD, name="run", of=owner)]
                    if present
                    else []
                ),
                "rust",
                str(file_path),
            )

    registry = ValidatorRegistry()
    registry.register(ContextRustValidator)
    monkeypatch.setattr(
        ValidatorRegistry, "with_builtin_validators", classmethod(lambda cls: registry)
    )
    manifest = _manifest(root, [("cargo", "test")])
    removed = RemovedArtifactSpec(
        kind=ArtifactKind.METHOD,
        name="run",
        of="crate::model::Widget",
        file="src/actions.rs",
        reason="retire",
    )
    manifest = replace(manifest, removed_artifacts=(removed,))
    if surface == "removal-validation":
        engine = ValidationEngine(project_root=root, registry=registry)
        assert engine.validate_removed_artifacts(manifest) == []
        context.write_text("present")
        errors = engine.validate_removed_artifacts(manifest)
        assert any(e.code == ErrorCode.REMOVED_ARTIFACT_STILL_PRESENT for e in errors)
    else:
        directory = root / "audit-manifests"
        directory.mkdir()
        common = {
            "schema": "2",
            "type": "feature",
            "goal": "Retire method",
            "created": "2026-10-02T00:00:00Z",
            "validate": [["cargo", "test"]],
        }
        old = {
            **common,
            "files": {
                "edit": [
                    {
                        "path": "src/actions.rs",
                        "artifacts": [
                            {
                                "kind": "method",
                                "name": "run",
                                "of": "crate::model::Widget",
                            }
                        ],
                    }
                ]
            },
        }
        new = {
            **common,
            "supersedes": ["old"],
            "removed_artifacts": [
                {
                    "kind": "method",
                    "name": "run",
                    "of": "crate::model::Widget",
                    "file": "src/actions.rs",
                    "reason": "retire",
                }
            ],
            "files": {
                "edit": [
                    {
                        "path": "src/lib.rs",
                        "artifacts": [{"kind": "function", "name": "render"}],
                    }
                ]
            },
        }
        (directory / "old.manifest.yaml").write_text(yaml.safe_dump(old))
        (directory / "new.manifest.yaml").write_text(yaml.safe_dump(new))
        chain = ManifestChain(directory, project_root=root)
        auditor = SupersessionAuditor(project_root=root, registry=registry)
        assert auditor.find_violations(chain) == ()
        context.write_text("present")
        violations = auditor.find_violations(chain)
        assert any(
            v.artifact_key == "method:crate::model::Widget.run" for v in violations
        )


def test_exact_reference_with_known_crate_does_not_cover_unknown_definition_identity(
    tmp_path,
):
    from maid_runner.core.identity import match_artifact_to_references
    from maid_runner.core.types import ArtifactKind

    artifact = FoundArtifact(kind=ArtifactKind.FUNCTION, name="render")
    reference = FoundArtifact(
        kind=ArtifactKind.FUNCTION,
        name="render",
        import_source="other",
        reference_context="exact",
    )
    assert not match_artifact_to_references(artifact, [reference], tmp_path)
