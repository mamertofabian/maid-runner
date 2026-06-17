"""Behavioral tests for entry-point validator plugin discovery."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.metadata
from pathlib import Path

from maid_runner.core.result import ErrorCode, Severity, ValidationError
from maid_runner.validators.base import BaseValidator, CollectionResult
from maid_runner.validators.python import PythonValidator
import maid_runner.validators.registry as registry_module
from maid_runner.validators.registry import ValidatorRegistry

ENTRY_POINT_GROUP = "maid_runner.validators"


class _GoValidator(BaseValidator):
    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".go",)

    def collect_implementation_artifacts(self, source, file_path):
        return CollectionResult(artifacts=[], language="go", file_path=str(file_path))

    def collect_behavioral_artifacts(self, source, file_path):
        return CollectionResult(artifacts=[], language="go", file_path=str(file_path))


class _RustValidator(BaseValidator):
    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".rs",)

    def collect_implementation_artifacts(self, source, file_path):
        return CollectionResult(artifacts=[], language="rust", file_path=str(file_path))

    def collect_behavioral_artifacts(self, source, file_path):
        return CollectionResult(artifacts=[], language="rust", file_path=str(file_path))


class _PythonPluginValidator(BaseValidator):
    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".py",)

    def collect_implementation_artifacts(self, source, file_path):
        return CollectionResult(
            artifacts=[], language="python-plugin", file_path=str(file_path)
        )

    def collect_behavioral_artifacts(self, source, file_path):
        return CollectionResult(
            artifacts=[], language="python-plugin", file_path=str(file_path)
        )


class _MixedValidator(BaseValidator):
    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".go", ".py")

    def collect_implementation_artifacts(self, source, file_path):
        return CollectionResult(
            artifacts=[], language="mixed", file_path=str(file_path)
        )

    def collect_behavioral_artifacts(self, source, file_path):
        return CollectionResult(
            artifacts=[], language="mixed", file_path=str(file_path)
        )


@dataclass(frozen=True)
class _FakeDistribution:
    name: str
    version: str = "1.0.0"

    @property
    def metadata(self) -> dict[str, str]:
        return {"Name": self.name}


class _FakeEntryPoint:
    def __init__(
        self,
        *,
        name: str,
        distribution: str,
        validator_class: type[BaseValidator] | None = None,
        version: str = "1.0.0",
        load_error: Exception | None = None,
    ) -> None:
        self.name = name
        self.group = ENTRY_POINT_GROUP
        self.value = f"{distribution}:{name}"
        self.dist = _FakeDistribution(distribution, version)
        self._validator_class = validator_class
        self._load_error = load_error
        self.load_count = 0

    def load(self):
        self.load_count += 1
        if self._load_error is not None:
            raise self._load_error
        return self._validator_class


class _FakeEntryPoints(tuple):
    def select(self, *, group: str | None = None):
        if group is None:
            return self
        return type(self)(ep for ep in self if ep.group == group)


def _patch_entry_points(monkeypatch, entry_points: list[_FakeEntryPoint]) -> None:
    fake_entry_points = _FakeEntryPoints(entry_points)

    def entry_points_lookup(*, group: str | None = None):
        if group is None:
            return fake_entry_points
        return fake_entry_points.select(group=group)

    monkeypatch.setattr(importlib.metadata, "entry_points", entry_points_lookup)


def _validator_record_type():
    return getattr(registry_module, "ValidatorRecord", None)


def _validator_record(*args, **kwargs):
    validator_record = _validator_record_type()
    assert validator_record is not None
    return validator_record(*args, **kwargs)


def _plugin_records(registry: ValidatorRegistry) -> list:
    return [
        record for record in registry.validator_records() if record.source != "builtin"
    ]


def test_with_builtin_validators_has_active_builtin_records_without_plugins(
    monkeypatch,
):
    _patch_entry_points(monkeypatch, [])

    registry = ValidatorRegistry.with_builtin_validators()
    records = registry.validator_records()
    diagnostics = registry.plugin_diagnostics()

    validator_record = registry_module.ValidatorRecord
    assert validator_record is _validator_record_type()
    assert records
    assert records[0].name == "PythonValidator"
    assert records[0].source == "builtin"
    assert records[0].status == "active"
    assert ".py" in records[0].extensions
    assert records[0].detail is None
    assert all(record.source == "builtin" for record in records)
    assert all(record.status == "active" for record in records)
    assert diagnostics == []


def test_well_formed_plugin_claiming_unclaimed_extension_becomes_active(monkeypatch):
    go_entry = _FakeEntryPoint(
        name="go",
        distribution="maid-validator-go",
        version="1.2.3",
        validator_class=_GoValidator,
    )
    _patch_entry_points(monkeypatch, [go_entry])

    registry = ValidatorRegistry.with_builtin_validators()

    assert isinstance(registry.get(Path("main.go")), _GoValidator)
    assert registry.has_validator("main.go") is True
    assert registry.has_validator_for_extension(".go") is True
    assert ".go" in registry.supported_extensions()
    assert _plugin_records(registry) == [
        _validator_record(
            name="go",
            extensions=(".go",),
            source="maid-validator-go 1.2.3",
            status="active",
            detail=None,
        )
    ]


def test_plugin_conflicting_with_builtin_does_not_replace_builtin(monkeypatch):
    py_entry = _FakeEntryPoint(
        name="python",
        distribution="maid-validator-python",
        validator_class=_PythonPluginValidator,
    )
    _patch_entry_points(monkeypatch, [py_entry])

    registry = ValidatorRegistry.with_builtin_validators()
    diagnostics = registry.plugin_diagnostics()

    assert isinstance(registry.get("example.py"), PythonValidator)
    assert _plugin_records(registry)[0].status == "conflict"
    assert ".py" in (_plugin_records(registry)[0].detail or "")
    assert [diagnostic.code for diagnostic in diagnostics] == [
        ErrorCode.VALIDATOR_PLUGIN_CONFLICT
    ]
    assert [diagnostic.severity for diagnostic in diagnostics] == [Severity.WARNING]
    assert "maid-validator-python" in diagnostics[0].message
    assert ".py" in diagnostics[0].message


def test_plugin_import_failure_isolated_from_builtins_and_other_plugins(monkeypatch):
    broken_entry = _FakeEntryPoint(
        name="broken",
        distribution="maid-validator-broken",
        load_error=RuntimeError("broken import"),
    )
    go_entry = _FakeEntryPoint(
        name="go",
        distribution="maid-validator-go",
        validator_class=_GoValidator,
    )
    _patch_entry_points(monkeypatch, [broken_entry, go_entry])

    registry = ValidatorRegistry.with_builtin_validators()
    diagnostics = registry.plugin_diagnostics()

    assert isinstance(registry.get("main.py"), PythonValidator)
    assert isinstance(registry.get("main.go"), _GoValidator)
    assert [record.status for record in _plugin_records(registry)] == [
        "error",
        "active",
    ]
    assert [diagnostic.code for diagnostic in diagnostics] == [
        ErrorCode.VALIDATOR_PLUGIN_LOAD_FAILURE
    ]
    assert diagnostics[0].severity == Severity.WARNING
    assert "maid-validator-broken" in diagnostics[0].message
    assert "broken import" in diagnostics[0].message


def test_discovery_and_record_order_are_deterministic(monkeypatch):
    beta_go = _FakeEntryPoint(
        name="z-go",
        distribution="maid-validator-beta",
        validator_class=_GoValidator,
    )
    alpha_rust = _FakeEntryPoint(
        name="b-rust",
        distribution="maid-validator-alpha",
        validator_class=_RustValidator,
    )
    alpha_go = _FakeEntryPoint(
        name="a-go",
        distribution="maid-validator-alpha",
        validator_class=_GoValidator,
    )
    _patch_entry_points(monkeypatch, [beta_go, alpha_rust, alpha_go])

    registry = ValidatorRegistry.with_builtin_validators()

    assert [record.name for record in _plugin_records(registry)] == [
        "a-go",
        "b-rust",
        "z-go",
    ]
    assert isinstance(registry.get("main.go"), _GoValidator)
    assert _plugin_records(registry)[2].status == "conflict"
    assert "maid-validator-alpha" in registry.plugin_diagnostics()[0].message
    assert "maid-validator-beta" in registry.plugin_diagnostics()[0].message


def test_plugin_claiming_builtin_and_unclaimed_extensions_partially_registers(
    monkeypatch,
):
    mixed_entry = _FakeEntryPoint(
        name="mixed",
        distribution="maid-validator-mixed",
        validator_class=_MixedValidator,
    )
    _patch_entry_points(monkeypatch, [mixed_entry])

    registry = ValidatorRegistry.with_builtin_validators()

    assert isinstance(registry.get("main.go"), _MixedValidator)
    assert isinstance(registry.get("main.py"), PythonValidator)
    assert _plugin_records(registry) == [
        _validator_record(
            name="mixed",
            extensions=(".go", ".py"),
            source="maid-validator-mixed 1.0.0",
            status="conflict",
            detail="conflicting extensions: .py",
        )
    ]


def test_disable_environment_records_plugins_without_importing_them(
    monkeypatch,
):
    go_entry = _FakeEntryPoint(
        name="go",
        distribution="maid-validator-go",
        validator_class=_GoValidator,
    )
    _patch_entry_points(monkeypatch, [go_entry])
    monkeypatch.setenv("MAID_DISABLE_VALIDATOR_PLUGINS", "1")

    registry = ValidatorRegistry.with_builtin_validators()

    assert go_entry.load_count == 0
    assert registry.has_validator_for_extension(".go") is False
    assert _plugin_records(registry) == [
        _validator_record(
            name="go",
            extensions=(),
            source="maid-validator-go 1.0.0",
            status="disabled",
            detail="disabled by MAID_DISABLE_VALIDATOR_PLUGINS=1",
        )
    ]
    assert registry.plugin_diagnostics() == []


def test_discovery_runs_once_at_construction(monkeypatch):
    go_entry = _FakeEntryPoint(
        name="go",
        distribution="maid-validator-go",
        validator_class=_GoValidator,
    )
    lookup_count = 0

    def entry_points_lookup(*, group: str | None = None):
        nonlocal lookup_count
        lookup_count += 1
        points = _FakeEntryPoints([go_entry])
        if group is None:
            return points
        return points.select(group=group)

    monkeypatch.setattr(importlib.metadata, "entry_points", entry_points_lookup)

    registry = ValidatorRegistry.with_builtin_validators()
    registry.get("one.go")
    registry.get("two.go")
    registry.has_validator("three.go")
    registry.has_validator_for_extension(".go")

    assert lookup_count == 1
    assert go_entry.load_count == 1


def test_clone_copies_records_and_diagnostics_without_sharing_instances(monkeypatch):
    py_entry = _FakeEntryPoint(
        name="python",
        distribution="maid-validator-python",
        validator_class=_PythonPluginValidator,
    )
    _patch_entry_points(monkeypatch, [py_entry])
    registry = ValidatorRegistry.with_builtin_validators()
    registry.get("main.py")

    clone = registry.clone()

    assert clone.validator_records() == registry.validator_records()
    assert clone.plugin_diagnostics() == registry.plugin_diagnostics()
    assert isinstance(clone.plugin_diagnostics()[0], ValidationError)
    assert clone.get("main.py") is not registry.get("main.py")


def test_clear_removes_validators_records_and_diagnostics(monkeypatch):
    py_entry = _FakeEntryPoint(
        name="python",
        distribution="maid-validator-python",
        validator_class=_PythonPluginValidator,
    )
    _patch_entry_points(monkeypatch, [py_entry])
    registry = ValidatorRegistry.with_builtin_validators()

    registry.clear()

    assert registry.supported_extensions() == set()
    assert registry.validator_records() == ()
    assert registry.plugin_diagnostics() == []
