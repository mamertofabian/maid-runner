"""Behavioral contract for immutable deduplicated knockout planning."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import TestRunResult
from maid_runner.core.types import TestStream


def _write_source(root: Path) -> str:
    (root / "src").mkdir(parents=True, exist_ok=True)
    source = (
        "def alpha() -> str:\n"
        "    return 'alpha'\n\n"
        "def beta() -> str:\n"
        "    return 'beta'\n"
    )
    (root / "src" / "target.py").write_text(source)
    return source


def _write_manifest(
    root: Path,
    slug: str,
    *,
    artifacts=("alpha",),
    commands=("pytest -q tests/test_target.py",),
    file_path="src/target.py",
):
    manifest_dir = root / "manifests"
    manifest_dir.mkdir(exist_ok=True)
    payload = {
        "schema": "2",
        "goal": f"Knockout plan for {slug}",
        "type": "refactor",
        "created": "2026-08-12T00:00:00Z",
        "files": {
            "edit": [
                {
                    "path": file_path,
                    "artifacts": [
                        {"kind": "function", "name": name, "args": []}
                        for name in artifacts
                    ],
                }
            ]
        },
        "validate": list(commands),
    }
    path = manifest_dir / f"{slug}.manifest.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False))
    return load_manifest(path)


def _result(command, exit_code=1):
    return TestRunResult(
        manifest_slug="test",
        command=tuple(command),
        exit_code=exit_code,
        stdout="",
        stderr="",
        duration_ms=1.0,
        stream=TestStream.IMPLEMENTATION,
    )


def test_duplicate_declarations_build_one_unique_spec_without_combined_execution(
    tmp_path, monkeypatch
):
    from maid_runner.core import knockout
    from maid_runner.core.knockout import (
        KnockoutArtifactIdentity,
        KnockoutDeclaration,
        KnockoutMutationSpec,
        build_knockout_mutation_specs,
        run_knockout,
    )

    original = _write_source(tmp_path)
    first = _write_manifest(tmp_path, "first")
    second = _write_manifest(tmp_path, "second")
    specs = build_knockout_mutation_specs((first, second), tmp_path)
    calls = []
    monkeypatch.setattr(knockout, "changed_files", lambda root: ())

    def record(command, **kwargs):
        mutated = (
            'raise NotImplementedError("maid-knockout")'
            in (tmp_path / "src" / "target.py").read_text()
        )
        calls.append(
            (
                kwargs["manifest_slug"],
                mutated,
            )
        )
        return _result(command, exit_code=(1 if mutated else 0))

    monkeypatch.setattr(knockout, "_run_test_command", record)
    first_report = run_knockout(first, tmp_path)
    assert (tmp_path / "src" / "target.py").read_text() == original
    second_report = run_knockout(second, tmp_path)

    assert len(specs) == 1
    assert isinstance(specs[0], KnockoutMutationSpec)
    assert isinstance(specs[0].identity, KnockoutArtifactIdentity)
    assert all(
        isinstance(declaration, KnockoutDeclaration)
        for declaration in specs[0].declarations
    )
    assert len(specs[0].declarations) == 2
    assert first_report.success is True
    assert second_report.success is True
    assert calls == [
        (first.slug, False),
        (first.slug, True),
        (first.slug, False),
        (second.slug, False),
        (second.slug, True),
        (second.slug, False),
    ]
    assert (tmp_path / "src" / "target.py").read_text() == original


def test_unique_spec_retains_independent_manifest_declaration_records(tmp_path):
    from maid_runner.core.knockout import build_knockout_mutation_specs

    _write_source(tmp_path)
    first = _write_manifest(
        tmp_path,
        "first",
        commands=("pytest -q tests/test_first.py", "python tests/check_first.py"),
    )
    second = _write_manifest(
        tmp_path,
        "second",
        commands=("pytest -q tests/test_second.py",),
        file_path="./src/target.py",
    )

    (spec,) = build_knockout_mutation_specs((first, second), tmp_path)

    assert spec.identity.file_path == "src/target.py"
    assert spec.identity.artifact_name == "alpha"
    assert spec.identity.artifact_kind == "function"
    assert spec.identity.parent_class is None
    assert [item.manifest_path for item in spec.declarations] == [
        first.source_path,
        second.source_path,
    ]
    assert [item.manifest_slug for item in spec.declarations] == [
        first.slug,
        second.slug,
    ]
    assert [item.declaration_index for item in spec.declarations] == [0, 0]
    assert [item.plan_index for item in spec.declarations] == [0, 1]
    assert spec.declarations[0].commands == first.validate_commands
    assert spec.declarations[1].commands == second.validate_commands


def test_spec_plan_preserves_legacy_declaration_and_command_order(tmp_path):
    from maid_runner.core.knockout import build_knockout_mutation_specs

    _write_source(tmp_path)
    first = _write_manifest(
        tmp_path,
        "first",
        artifacts=("beta", "alpha"),
        commands=("first-a", "first-b"),
    )
    second = _write_manifest(
        tmp_path,
        "second",
        artifacts=("alpha", "beta"),
        commands=("second-a", "second-b"),
    )

    specs = build_knockout_mutation_specs((first, second), tmp_path)

    assert [spec.identity.artifact_name for spec in specs] == ["beta", "alpha"]
    declarations = sorted(
        (declaration for spec in specs for declaration in spec.declarations),
        key=lambda item: item.plan_index,
    )
    assert [
        (declaration.manifest_slug, declaration.declaration_index)
        for declaration in declarations
    ] == [(first.slug, 0), (first.slug, 1), (second.slug, 0), (second.slug, 1)]
    assert [declaration.commands for declaration in declarations] == [
        first.validate_commands,
        first.validate_commands,
        second.validate_commands,
        second.validate_commands,
    ]
    assert [
        declaration.plan_index for spec in specs for declaration in spec.declarations
    ] == [0, 3, 1, 2]


def test_limit_selects_declaration_order_before_deduplication(tmp_path):
    from maid_runner.core.knockout import build_knockout_mutation_specs

    _write_source(tmp_path)
    first = _write_manifest(tmp_path, "first", artifacts=("alpha", "beta"))
    second = _write_manifest(tmp_path, "second", artifacts=("alpha", "beta"))

    specs = build_knockout_mutation_specs((first, second), tmp_path, limit=3)

    assert [spec.identity.artifact_name for spec in specs] == ["alpha", "beta"]
    assert [
        (
            declaration.manifest_slug,
            declaration.declaration_index,
            declaration.plan_index,
        )
        for declaration in specs[0].declarations
    ] == [(first.slug, 0, 0), (second.slug, 0, 2)]
    assert [
        (
            declaration.manifest_slug,
            declaration.declaration_index,
            declaration.plan_index,
        )
        for declaration in specs[1].declarations
    ] == [(first.slug, 1, 1)]


def test_source_digest_change_rejects_stale_spec(tmp_path):
    from maid_runner.core.knockout import (
        build_knockout_mutation_specs,
        knockout_mutation_spec_is_current,
    )

    original = _write_source(tmp_path)
    crlf_bytes = original.replace("\n", "\r\n").encode()
    (tmp_path / "src" / "target.py").write_bytes(crlf_bytes)
    manifest = _write_manifest(tmp_path, "only")
    (spec,) = build_knockout_mutation_specs((manifest,), tmp_path)

    assert spec.source_digest == hashlib.sha256(crlf_bytes).hexdigest()
    assert knockout_mutation_spec_is_current(spec, tmp_path) is True

    (tmp_path / "src" / "target.py").write_bytes(original.encode())

    assert knockout_mutation_spec_is_current(spec, tmp_path) is False


def test_inter_declaration_target_restore_and_command_side_effect_order_match_legacy(
    tmp_path, monkeypatch
):
    from maid_runner.core import knockout
    from maid_runner.core.knockout import (
        build_knockout_mutation_specs,
        run_knockout,
    )

    control_root = tmp_path / "control"
    planned_root = tmp_path / "planned"
    original = _write_source(control_root)
    _write_source(planned_root)
    control_manifests = (
        _write_manifest(control_root, "first", commands=("first",)),
        _write_manifest(control_root, "second", commands=("second",)),
    )
    planned_manifests = (
        _write_manifest(planned_root, "first", commands=("first",)),
        _write_manifest(planned_root, "second", commands=("second",)),
    )
    declarations = sorted(
        (
            declaration
            for spec in build_knockout_mutation_specs(planned_manifests, planned_root)
            for declaration in spec.declarations
        ),
        key=lambda item: item.plan_index,
    )
    expected_order = [
        command
        for declaration in declarations
        for command in declaration.commands
        for _phase in range(3)
    ]
    events = {control_root: [], planned_root: []}
    monkeypatch.setattr(knockout, "changed_files", lambda root: ())

    def record(command, **kwargs):
        root = Path(kwargs["cwd"])
        source = (root / "src" / "target.py").read_text()
        state_path = root / "command-state.log"
        prior_state = state_path.read_text() if state_path.exists() else ""
        state_path.write_text(prior_state + command[0] + "\n")
        events[root].append(
            (tuple(command), source, kwargs["manifest_slug"], prior_state)
        )
        mutated = 'raise NotImplementedError("maid-knockout")' in source
        return _result(command, exit_code=(1 if mutated else 0))

    monkeypatch.setattr(knockout, "_run_test_command", record)

    for root, manifests in (
        (control_root, control_manifests),
        (planned_root, planned_manifests),
    ):
        for manifest in manifests:
            assert run_knockout(manifest, root).success is True
            assert (root / "src" / "target.py").read_text() == original

    normalized_control = [
        (event[0], event[2], event[3]) for event in events[control_root]
    ]
    normalized_planned = [
        (event[0], event[2], event[3]) for event in events[planned_root]
    ]
    assert normalized_planned == normalized_control
    assert [event[0] for event in events[planned_root]] == expected_order
    assert [
        'raise NotImplementedError("maid-knockout")' in event[1]
        for event in events[planned_root]
    ] == [False, True, False, False, True, False]
    expected_state = "first\nfirst\nfirst\nsecond\nsecond\nsecond\n"
    assert (control_root / "command-state.log").read_text() == expected_state
    assert (planned_root / "command-state.log").read_text() == expected_state
