"""Tests for maid_runner.core.types - all enums and dataclasses."""

import pytest

from maid_runner.core.types import (
    AcceptanceConfig,
    ArtifactKind,
    ArtifactSpec,
    ArgSpec,
    DeleteSpec,
    FileMode,
    FileSpec,
    Manifest,
    TaskType,
    TestFunctionDetails,
    TestFunctionSetup,
    TestStream,
    ValidationMode,
)


class TestArtifactKind:
    def test_values(self):
        assert ArtifactKind.CLASS == "class"
        assert ArtifactKind.FUNCTION == "function"
        assert ArtifactKind.METHOD == "method"
        assert ArtifactKind.ATTRIBUTE == "attribute"
        assert ArtifactKind.INTERFACE == "interface"
        assert ArtifactKind.TYPE == "type"
        assert ArtifactKind.ENUM == "enum"
        assert ArtifactKind.NAMESPACE == "namespace"
        assert ArtifactKind.TEST_FUNCTION == "test_function"

    def test_is_string_enum(self):
        assert isinstance(ArtifactKind.CLASS, str)
        assert ArtifactKind("class") == ArtifactKind.CLASS


class TestTaskType:
    def test_values(self):
        assert TaskType.FEATURE == "feature"
        assert TaskType.FIX == "fix"
        assert TaskType.REFACTOR == "refactor"
        assert TaskType.SNAPSHOT == "snapshot"
        assert TaskType.SYSTEM_SNAPSHOT == "system-snapshot"

    def test_is_string_enum(self):
        assert isinstance(TaskType.FEATURE, str)
        assert TaskType("feature") == TaskType.FEATURE


class TestValidationMode:
    def test_values(self):
        assert ValidationMode.BEHAVIORAL == "behavioral"
        assert ValidationMode.IMPLEMENTATION == "implementation"


class TestFileMode:
    def test_values(self):
        assert FileMode.CREATE == "create"
        assert FileMode.EDIT == "edit"
        assert FileMode.READ == "read"
        assert FileMode.DELETE == "delete"
        assert FileMode.SNAPSHOT == "snapshot"


class TestArgSpec:
    def test_basic(self):
        arg = ArgSpec(name="x", type="int")
        assert arg.name == "x"
        assert arg.type == "int"
        assert arg.default is None

    def test_with_default(self):
        arg = ArgSpec(name="y", type="str", default='"hello"')
        assert arg.default == '"hello"'

    def test_name_only(self):
        arg = ArgSpec(name="data")
        assert arg.type is None
        assert arg.default is None

    def test_frozen(self):
        arg = ArgSpec(name="x")
        with pytest.raises(AttributeError):
            arg.name = "y"  # type: ignore[misc]


class TestTestFunctionDetails:
    def test_defaults(self):
        setup = TestFunctionSetup()
        details = TestFunctionDetails()
        spec = ArtifactSpec(
            kind=ArtifactKind.TEST_FUNCTION,
            name="test_contract",
            test_details=details,
        )

        assert setup.auth_required is False
        assert setup.test_data == {}
        assert setup.setup_actions == ()
        assert details.source_scenario == ""
        assert details.tags == ()
        assert details.setup == setup
        assert details.actions == ()
        assert details.expected == {}
        assert details.dependencies == {}
        assert spec.test_details == details

    def test_equality(self):
        assert ArgSpec(name="x", type="int") == ArgSpec(name="x", type="int")
        assert ArgSpec(name="x", type="int") != ArgSpec(name="x", type="str")

    def test_hashable(self):
        arg = ArgSpec(name="x", type="int")
        assert hash(arg) == hash(ArgSpec(name="x", type="int"))
        s = {arg, ArgSpec(name="x", type="int")}
        assert len(s) == 1


class TestArtifactSpec:
    def test_basic_class(self):
        spec = ArtifactSpec(kind=ArtifactKind.CLASS, name="UserService")
        assert spec.kind == ArtifactKind.CLASS
        assert spec.name == "UserService"
        assert spec.of is None
        assert spec.args == ()
        assert spec.returns is None

    def test_method_with_of(self):
        spec = ArtifactSpec(
            kind=ArtifactKind.METHOD,
            name="login",
            of="AuthService",
            args=(ArgSpec("username", "str"), ArgSpec("password", "str")),
            returns="Token",
        )
        assert spec.of == "AuthService"
        assert len(spec.args) == 2
        assert spec.returns == "Token"

    def test_async_function(self):
        spec = ArtifactSpec(
            kind=ArtifactKind.FUNCTION,
            name="fetch_data",
            is_async=True,
            args=(ArgSpec("url", "str"),),
            returns="dict",
        )
        assert spec.is_async is True

    def test_class_with_bases(self):
        spec = ArtifactSpec(
            kind=ArtifactKind.CLASS,
            name="UserService",
            bases=("ABC",),
        )
        assert spec.bases == ("ABC",)

    def test_attribute_with_type(self):
        spec = ArtifactSpec(
            kind=ArtifactKind.ATTRIBUTE,
            name="MAX_RETRIES",
            type_annotation="int",
        )
        assert spec.type_annotation == "int"

    def test_class_attribute(self):
        spec = ArtifactSpec(
            kind=ArtifactKind.ATTRIBUTE,
            name="debug",
            of="Config",
        )
        assert spec.of == "Config"

    def test_qualified_name_with_parent(self):
        spec = ArtifactSpec(kind=ArtifactKind.METHOD, name="login", of="AuthService")
        assert spec.qualified_name == "AuthService.login"

    def test_qualified_name_without_parent(self):
        spec = ArtifactSpec(kind=ArtifactKind.FUNCTION, name="greet")
        assert spec.qualified_name == "greet"

    def test_is_private_underscore(self):
        spec = ArtifactSpec(kind=ArtifactKind.FUNCTION, name="_helper")
        assert spec.is_private is True

    def test_is_private_dunder(self):
        spec = ArtifactSpec(kind=ArtifactKind.METHOD, name="__init__", of="Foo")
        assert spec.is_private is True

    def test_is_not_private(self):
        spec = ArtifactSpec(kind=ArtifactKind.FUNCTION, name="greet")
        assert spec.is_private is False

    def test_is_private_inherited_from_parent(self):
        """Members of _-prefixed types inherit privacy."""
        spec = ArtifactSpec(
            kind=ArtifactKind.ATTRIBUTE, name="headers", of="_AuthRequest"
        )
        assert spec.is_private is True

    def test_is_not_private_public_parent(self):
        """Members of public types are not private."""
        spec = ArtifactSpec(kind=ArtifactKind.ATTRIBUTE, name="status", of="Response")
        assert spec.is_private is False

    def test_merge_key_method(self):
        spec = ArtifactSpec(kind=ArtifactKind.METHOD, name="login", of="AuthService")
        assert spec.merge_key() == "AuthService.login"

    def test_merge_key_attribute_with_class(self):
        spec = ArtifactSpec(kind=ArtifactKind.ATTRIBUTE, name="debug", of="Config")
        assert spec.merge_key() == "Config.debug"

    def test_merge_key_function(self):
        spec = ArtifactSpec(kind=ArtifactKind.FUNCTION, name="greet")
        assert spec.merge_key() == "greet"

    def test_merge_key_class(self):
        spec = ArtifactSpec(kind=ArtifactKind.CLASS, name="Foo")
        assert spec.merge_key() == "Foo"

    def test_frozen(self):
        spec = ArtifactSpec(kind=ArtifactKind.CLASS, name="Foo")
        with pytest.raises(AttributeError):
            spec.name = "Bar"  # type: ignore[misc]

    def test_with_raises(self):
        spec = ArtifactSpec(
            kind=ArtifactKind.FUNCTION,
            name="divide",
            raises=("ZeroDivisionError",),
        )
        assert spec.raises == ("ZeroDivisionError",)

    def test_with_description(self):
        spec = ArtifactSpec(
            kind=ArtifactKind.CLASS,
            name="Service",
            description="Main service class",
        )
        assert spec.description == "Main service class"


class TestFileSpec:
    def test_basic(self):
        spec = FileSpec(
            path="src/greet.py",
            artifacts=(ArtifactSpec(kind=ArtifactKind.FUNCTION, name="greet"),),
        )
        assert spec.path == "src/greet.py"
        assert len(spec.artifacts) == 1
        assert spec.status == "present"
        assert spec.mode == FileMode.CREATE

    def test_is_strict_create(self):
        spec = FileSpec(
            path="src/greet.py",
            artifacts=(),
            mode=FileMode.CREATE,
        )
        assert spec.is_strict is True

    def test_is_strict_snapshot(self):
        spec = FileSpec(
            path="src/greet.py",
            artifacts=(),
            mode=FileMode.SNAPSHOT,
        )
        assert spec.is_strict is True

    def test_is_not_strict_edit(self):
        spec = FileSpec(
            path="src/greet.py",
            artifacts=(),
            mode=FileMode.EDIT,
        )
        assert spec.is_strict is False

    def test_is_absent_by_status(self):
        spec = FileSpec(
            path="src/old.py",
            artifacts=(),
            status="absent",
        )
        assert spec.is_absent is True

    def test_is_absent_by_delete_mode(self):
        spec = FileSpec(
            path="src/old.py",
            artifacts=(),
            mode=FileMode.DELETE,
        )
        assert spec.is_absent is True

    def test_is_not_absent(self):
        spec = FileSpec(
            path="src/app.py",
            artifacts=(),
        )
        assert spec.is_absent is False

    def test_frozen(self):
        spec = FileSpec(path="src/a.py", artifacts=())
        with pytest.raises(AttributeError):
            spec.path = "src/b.py"  # type: ignore[misc]


class TestDeleteSpec:
    def test_basic(self):
        spec = DeleteSpec(path="src/old.py")
        assert spec.path == "src/old.py"
        assert spec.reason is None

    def test_with_reason(self):
        spec = DeleteSpec(path="src/old.py", reason="Replaced by new.py")
        assert spec.reason == "Replaced by new.py"

    def test_frozen(self):
        spec = DeleteSpec(path="src/old.py")
        with pytest.raises(AttributeError):
            spec.path = "src/new.py"  # type: ignore[misc]


class TestManifest:
    @pytest.fixture()
    def simple_manifest(self):
        return Manifest(
            slug="add-greet",
            source_path="/manifests/add-greet.manifest.yaml",
            goal="Add greeting function",
            validate_commands=(("pytest", "tests/test_greet.py", "-v"),),
            files_create=(
                FileSpec(
                    path="src/greet.py",
                    artifacts=(
                        ArtifactSpec(
                            kind=ArtifactKind.FUNCTION,
                            name="greet",
                            args=(ArgSpec("name", "str"),),
                            returns="str",
                        ),
                    ),
                    mode=FileMode.CREATE,
                ),
            ),
            files_read=("tests/test_greet.py",),
            task_type=TaskType.FEATURE,
            schema_version="2",
        )

    @pytest.fixture()
    def multi_file_manifest(self):
        return Manifest(
            slug="add-auth",
            source_path="/manifests/add-auth.manifest.yaml",
            goal="Add auth service",
            validate_commands=(("pytest", "tests/test_auth.py", "-v"),),
            files_create=(
                FileSpec(
                    path="src/auth/service.py",
                    artifacts=(
                        ArtifactSpec(kind=ArtifactKind.CLASS, name="AuthService"),
                        ArtifactSpec(
                            kind=ArtifactKind.METHOD,
                            name="login",
                            of="AuthService",
                        ),
                    ),
                    mode=FileMode.CREATE,
                ),
                FileSpec(
                    path="src/auth/models.py",
                    artifacts=(ArtifactSpec(kind=ArtifactKind.CLASS, name="Token"),),
                    mode=FileMode.CREATE,
                ),
            ),
            files_edit=(
                FileSpec(
                    path="src/config.py",
                    artifacts=(
                        ArtifactSpec(
                            kind=ArtifactKind.ATTRIBUTE,
                            name="AUTH_SECRET",
                            type_annotation="str",
                        ),
                    ),
                    mode=FileMode.EDIT,
                ),
            ),
            files_read=("src/database.py",),
        )

    def test_frozen(self, simple_manifest):
        with pytest.raises(AttributeError):
            simple_manifest.goal = "Changed"  # type: ignore[misc]

    def test_all_file_specs(self, multi_file_manifest):
        specs = multi_file_manifest.all_file_specs
        assert len(specs) == 3
        paths = [s.path for s in specs]
        assert "src/auth/service.py" in paths
        assert "src/auth/models.py" in paths
        assert "src/config.py" in paths

    def test_all_writable_paths(self, multi_file_manifest):
        paths = multi_file_manifest.all_writable_paths
        assert "src/auth/service.py" in paths
        assert "src/auth/models.py" in paths
        assert "src/config.py" in paths
        assert "src/database.py" not in paths

    def test_all_referenced_paths(self, multi_file_manifest):
        paths = multi_file_manifest.all_referenced_paths
        assert "src/database.py" in paths
        assert "src/auth/service.py" in paths

    def test_file_spec_for_found(self, multi_file_manifest):
        spec = multi_file_manifest.file_spec_for("src/auth/service.py")
        assert spec is not None
        assert spec.path == "src/auth/service.py"

    def test_file_spec_for_not_found(self, multi_file_manifest):
        spec = multi_file_manifest.file_spec_for("nonexistent.py")
        assert spec is None

    def test_artifacts_for_found(self, multi_file_manifest):
        artifacts = multi_file_manifest.artifacts_for("src/auth/service.py")
        assert len(artifacts) == 2
        names = [a.name for a in artifacts]
        assert "AuthService" in names
        assert "login" in names

    def test_artifacts_for_not_found(self, multi_file_manifest):
        artifacts = multi_file_manifest.artifacts_for("nonexistent.py")
        assert artifacts == ()

    def test_defaults(self):
        m = Manifest(
            slug="test",
            source_path="/test.yaml",
            goal="Test",
            validate_commands=(("pytest",),),
        )
        assert m.files_create == ()
        assert m.files_edit == ()
        assert m.files_read == ()
        assert m.files_delete == ()
        assert m.files_snapshot == ()
        assert m.schema_version == "2"
        assert m.task_type is None
        assert m.description is None
        assert m.supersedes == ()
        assert m.created is None
        assert m.metadata is None

    def test_all_writable_paths_with_delete(self):
        m = Manifest(
            slug="remove-old",
            source_path="/test.yaml",
            goal="Remove old module",
            validate_commands=(("pytest",),),
            files_delete=(DeleteSpec(path="src/old.py"),),
        )
        assert "src/old.py" in m.all_writable_paths

    def test_all_writable_paths_with_snapshot(self):
        m = Manifest(
            slug="snapshot",
            source_path="/test.yaml",
            goal="Snapshot",
            validate_commands=(("pytest",),),
            files_snapshot=(
                FileSpec(
                    path="src/engine.py",
                    artifacts=(),
                    mode=FileMode.SNAPSHOT,
                ),
            ),
        )
        assert "src/engine.py" in m.all_writable_paths

    def test_is_superseded_by_raises(self, simple_manifest):
        with pytest.raises(NotImplementedError):
            _ = simple_manifest.is_superseded_by

    def test_acceptance_default_none(self):
        m = Manifest(
            slug="test",
            source_path="/test.yaml",
            goal="Test",
            validate_commands=(("pytest",),),
        )
        assert m.acceptance is None

    def test_acceptance_with_config(self):
        acc = AcceptanceConfig(
            tests=(("pytest", "tests/acceptance/test_auth.py", "-v"),),
            immutable=True,
        )
        m = Manifest(
            slug="test",
            source_path="/test.yaml",
            goal="Test",
            validate_commands=(("pytest",),),
            acceptance=acc,
        )
        assert m.acceptance is not None
        assert m.acceptance.tests == (
            ("pytest", "tests/acceptance/test_auth.py", "-v"),
        )
        assert m.acceptance.immutable is True


class TestTestStream:
    def test_values(self):
        assert TestStream.ACCEPTANCE == "acceptance"
        assert TestStream.IMPLEMENTATION == "implementation"

    def test_is_string_enum(self):
        assert isinstance(TestStream.ACCEPTANCE, str)
        assert TestStream("acceptance") == TestStream.ACCEPTANCE


class TestAcceptanceConfig:
    def test_basic(self):
        acc = AcceptanceConfig(
            tests=(("pytest", "tests/acceptance/test_auth.py", "-v"),),
        )
        assert len(acc.tests) == 1
        assert acc.immutable is True

    def test_immutable_false(self):
        acc = AcceptanceConfig(
            tests=(("pytest", "tests/acceptance/test_auth.py"),),
            immutable=False,
        )
        assert acc.immutable is False

    def test_defaults(self):
        acc = AcceptanceConfig()
        assert acc.tests == ()
        assert acc.immutable is True

    def test_frozen(self):
        acc = AcceptanceConfig(tests=(("echo", "test"),))
        with pytest.raises(AttributeError):
            acc.immutable = False  # type: ignore[misc]

    def test_multiple_commands(self):
        acc = AcceptanceConfig(
            tests=(
                ("pytest", "tests/acceptance/test_auth.py", "-v"),
                ("pytest", "tests/acceptance/test_users.py", "-v"),
            ),
        )
        assert len(acc.tests) == 2
