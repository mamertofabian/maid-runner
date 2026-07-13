"""Behavioral contract for adopting completed pre-plan-lock manifests."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from maid_runner.cli.commands._main import build_parser
from maid_runner.cli.commands.plan import cmd_plan_lock, cmd_plan_status
from maid_runner.core.chain import ManifestChain
from maid_runner.core.types import AgentProvenance
from maid_runner.core.plan_lock import (
    PlanLock,
    default_plan_lock_path,
    enforce_plan_locks,
)
from maid_runner.core.result import ErrorCode


def _git(project_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )


def _manifest_text(
    command: str,
    *,
    extra_artifact: str = "",
    extra_files: str = "",
    read_path: str = "tests/test_demo.py",
    additional_commands: tuple[str, ...] = (),
) -> str:
    validate_lines = "\n".join(
        f"  - {entry}" for entry in (command, *additional_commands)
    )
    return f"""schema: "2"
goal: "Completed legacy task"
type: fix
created: "2026-05-01T00:00:00Z"
files:
  edit:
    - path: src/demo.py
      artifacts:
        - kind: function
          name: demo
          args: []
          returns: int
{extra_artifact}{extra_files}  read:
    - {read_path}
validate:
{validate_lines}
"""


def _write_committed_legacy_project(
    project_root: Path,
    *,
    committed_command: str = "python scripts/validate.py",
    committed_additional_commands: tuple[str, ...] = (),
    validate_exit: int = 0,
    validation_mutation: str | None = None,
    validation_lock_payload: str | None = None,
    ignore_maid: bool = False,
) -> Path:
    (project_root / "manifests").mkdir(parents=True)
    (project_root / "src").mkdir()
    (project_root / "tests").mkdir()
    (project_root / "scripts").mkdir()
    (project_root / "src" / "demo.py").write_text(
        "def demo() -> int:\n    return 1\n", encoding="utf-8"
    )
    (project_root / "tests" / "test_demo.py").write_text(
        "from src.demo import demo\n\n\ndef test_demo() -> None:\n"
        "    assert demo() == 1\n",
        encoding="utf-8",
    )
    (project_root / "tests" / "test_other.py").write_text(
        "from src.demo import demo\n\n\ndef test_other() -> None:\n"
        "    assert demo() == 1\n",
        encoding="utf-8",
    )
    validation_source = "import sys\n" f"sys.exit({validate_exit})\n"
    if validation_mutation is not None:
        validation_source = (
            "from pathlib import Path\n"
            f"target = Path({validation_mutation!r})\n"
            "target.write_text(target.read_text(encoding='utf-8') + '# mutated\\n', "
            "encoding='utf-8')\n"
        )
    elif validation_lock_payload is not None:
        validation_source = (
            "from pathlib import Path\n"
            "import sys\n"
            "target = Path('.maid/plan-locks/legacy-task.lock.json')\n"
            "target.parent.mkdir(parents=True, exist_ok=True)\n"
            f"target.write_text({validation_lock_payload!r}, encoding='utf-8')\n"
            f"sys.exit({validate_exit})\n"
        )
    (project_root / "scripts" / "validate.py").write_text(
        validation_source, encoding="utf-8"
    )
    manifest_path = project_root / "manifests" / "legacy-task.manifest.yaml"
    manifest_path.write_text(
        _manifest_text(
            committed_command,
            additional_commands=committed_additional_commands,
        ),
        encoding="utf-8",
    )
    if ignore_maid:
        (project_root / ".gitignore").write_text(".maid/\n", encoding="utf-8")
    _git(project_root, "init", "-q")
    _git(project_root, "config", "user.email", "maid-test@example.com")
    _git(project_root, "config", "user.name", "MAID Test")
    _git(project_root, "add", ".")
    _git(project_root, "commit", "-qm", "legacy completed task")
    return manifest_path


def _lock_args(
    manifest_path: Path,
    project_root: Path,
    *,
    legacy_baseline: bool = False,
    reason: str | None = None,
    no_run: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="lock",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        legacy_baseline=legacy_baseline,
        reason=reason,
        no_run=no_run,
        json=False,
    )


def _status_args(
    manifest_path: Path, project_root: Path, *, json_mode: bool
) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="status",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        json=json_mode,
    )


def _strengthen_validate_command(manifest_path: Path) -> None:
    manifest_path.write_text(
        _manifest_text("python scripts/validate.py tests/test_demo.py"),
        encoding="utf-8",
    )


def _codes(errors) -> list[ErrorCode]:
    return [error.code for error in errors]


def test_lock_parser_exposes_legacy_baseline_with_reason() -> None:
    args = build_parser().parse_args(
        [
            "plan",
            "lock",
            "manifests/legacy-task.manifest.yaml",
            "--legacy-baseline",
            "--reason",
            "Repair a pre-plan-lock validate command",
        ]
    )

    assert args.legacy_baseline is True
    assert args.reason == "Repair a pre-plan-lock validate command"


def test_legacy_baseline_records_green_provenance_and_satisfies_strict_gate(
    tmp_path: Path,
) -> None:
    from maid_runner.core.plan_lock import (
        LegacyBaselineEvidence,
        capture_legacy_baseline_evidence,
    )

    manifest_path = _write_committed_legacy_project(tmp_path)
    _strengthen_validate_command(manifest_path)
    reason = "Add the already-declared behavioral test to legacy validation"

    evidence = capture_legacy_baseline_evidence(manifest_path, tmp_path, reason)

    assert isinstance(evidence, LegacyBaselineEvidence)
    assert evidence.reason == reason
    assert (
        evidence.baseline_commit == _git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    )
    assert len(evidence.baseline_manifest_hash) == 64
    assert evidence.contract_delta.artifacts_added == ()
    assert evidence.contract_delta.artifacts_removed == ()
    assert evidence.contract_delta.files_added == ()
    assert evidence.contract_delta.files_removed == ()
    assert evidence.commands[0].exit_code == 0
    assert evidence.commands[0].classification == "not_red"
    assert evidence.captured_at
    assert evidence.to_payload()["kind"] == "legacy_baseline"

    exit_code = cmd_plan_lock(
        _lock_args(
            manifest_path,
            tmp_path,
            legacy_baseline=True,
            reason=reason,
        )
    )

    assert exit_code == 0
    lock_path = default_plan_lock_path(tmp_path, "legacy-task")
    lock = PlanLock.load(lock_path)
    assert lock.red_evidence is None
    assert lock.legacy_baseline is not None
    assert lock.legacy_baseline["reason"] == reason
    assert lock.legacy_baseline["commands"][0]["classification"] == "not_red"

    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=True,
        changed_paths={"manifests/legacy-task.manifest.yaml"},
        plan_lock_scope="task",
    )

    assert errors == ()


def test_legacy_baseline_rejects_untracked_manifest(tmp_path: Path) -> None:
    manifest_path = _write_committed_legacy_project(tmp_path)
    manifest_path.rename(tmp_path / "manifests" / "original.manifest.yaml")
    manifest_path = tmp_path / "manifests" / "new-task.manifest.yaml"
    manifest_path.write_text(
        _manifest_text("python scripts/validate.py tests/test_demo.py"),
        encoding="utf-8",
    )

    exit_code = cmd_plan_lock(
        _lock_args(
            manifest_path,
            tmp_path,
            legacy_baseline=True,
            reason="Attempt to grandfather a new manifest",
        )
    )

    assert exit_code == 2
    assert not default_plan_lock_path(tmp_path, "new-task").exists()


def test_legacy_baseline_requires_reason_and_rejects_no_run(tmp_path: Path) -> None:
    missing_reason_root = tmp_path / "missing-reason"
    missing_reason_manifest = _write_committed_legacy_project(missing_reason_root)
    _strengthen_validate_command(missing_reason_manifest)

    missing_reason_exit = cmd_plan_lock(
        _lock_args(
            missing_reason_manifest,
            missing_reason_root,
            legacy_baseline=True,
        )
    )

    no_run_root = tmp_path / "no-run"
    no_run_manifest = _write_committed_legacy_project(no_run_root)
    _strengthen_validate_command(no_run_manifest)
    no_run_exit = cmd_plan_lock(
        _lock_args(
            no_run_manifest,
            no_run_root,
            legacy_baseline=True,
            reason="Green evidence cannot be skipped",
            no_run=True,
        )
    )

    assert missing_reason_exit == 2
    assert no_run_exit == 2
    assert not default_plan_lock_path(missing_reason_root, "legacy-task").exists()
    assert not default_plan_lock_path(no_run_root, "legacy-task").exists()


def test_legacy_baseline_rejects_dirty_implementation_or_test_paths(
    tmp_path: Path,
) -> None:
    for dirty_path in ("src/demo.py", "tests/test_demo.py"):
        project_root = tmp_path / dirty_path.split("/")[0]
        manifest_path = _write_committed_legacy_project(project_root)
        _strengthen_validate_command(manifest_path)
        target = project_root / dirty_path
        target.write_text(target.read_text(encoding="utf-8") + "# dirty\n")

        exit_code = cmd_plan_lock(
            _lock_args(
                manifest_path,
                project_root,
                legacy_baseline=True,
                reason="Metadata migration must not hide implementation work",
            )
        )

        assert exit_code == 2
        assert not default_plan_lock_path(project_root, "legacy-task").exists()


def test_legacy_baseline_rejects_contract_change_or_validate_weakening(
    tmp_path: Path,
) -> None:
    contract_root = tmp_path / "contract"
    contract_manifest = _write_committed_legacy_project(contract_root)
    contract_manifest.write_text(
        _manifest_text(
            "python scripts/validate.py tests/test_demo.py",
            extra_artifact=(
                "        - kind: function\n"
                "          name: extra_demo\n"
                "          args: []\n"
                "          returns: int\n"
            ),
        ),
        encoding="utf-8",
    )

    contract_exit = cmd_plan_lock(
        _lock_args(
            contract_manifest,
            contract_root,
            legacy_baseline=True,
            reason="Artifact additions are not metadata migration",
        )
    )

    weakening_root = tmp_path / "weakening"
    weakening_manifest = _write_committed_legacy_project(
        weakening_root,
        committed_command="python scripts/validate.py tests/test_demo.py",
    )
    weakening_manifest.write_text(
        _manifest_text("python scripts/validate.py"), encoding="utf-8"
    )
    weakening_exit = cmd_plan_lock(
        _lock_args(
            weakening_manifest,
            weakening_root,
            legacy_baseline=True,
            reason="Validate weakening must be refused",
        )
    )

    file_contract_exits = []
    for section, extra_files in {
        "scope": (
            "  scope:\n"
            "    - path: src/scoped.py\n"
            "      reason: Contract inventory cannot change\n"
        ),
        "delete": (
            "  delete:\n"
            "    - path: src/obsolete.py\n"
            "      reason: Contract inventory cannot change\n"
        ),
        "snapshot": (
            "  snapshot:\n"
            "    - path: src/demo.py\n"
            "      artifacts:\n"
            "        - kind: function\n"
            "          name: demo\n"
            "          args: []\n"
            "          returns: int\n"
        ),
    }.items():
        project_root = tmp_path / section
        manifest_path = _write_committed_legacy_project(project_root)
        manifest_path.write_text(
            _manifest_text(
                "python scripts/validate.py tests/test_demo.py",
                extra_files=extra_files,
            ),
            encoding="utf-8",
        )
        file_contract_exits.append(
            cmd_plan_lock(
                _lock_args(
                    manifest_path,
                    project_root,
                    legacy_baseline=True,
                    reason=f"{section} changes are not metadata migration",
                )
            )
        )

    nested_contract_exits = []
    for field_name, transform in {
        "imports": lambda text: text.replace(
            "      artifacts:\n",
            "      imports:\n        - os\n      artifacts:\n",
            1,
        ),
        "default-hook": lambda text: text.replace(
            "          returns: int\n",
            "          returns: int\n          default_hook: true\n",
            1,
        ),
    }.items():
        project_root = tmp_path / field_name
        manifest_path = _write_committed_legacy_project(project_root)
        manifest_path.write_text(
            transform(_manifest_text("python scripts/validate.py tests/test_demo.py")),
            encoding="utf-8",
        )
        nested_contract_exits.append(
            cmd_plan_lock(
                _lock_args(
                    manifest_path,
                    project_root,
                    legacy_baseline=True,
                    reason=f"{field_name} changes are not metadata migration",
                )
            )
        )

    assert contract_exit == 2
    assert weakening_exit == 2
    assert file_contract_exits == [2, 2, 2]
    assert nested_contract_exits == [2, 2]
    assert not default_plan_lock_path(contract_root, "legacy-task").exists()
    assert not default_plan_lock_path(weakening_root, "legacy-task").exists()


def test_legacy_baseline_rejects_filtering_suffix_arguments(tmp_path: Path) -> None:
    exits = []
    for case, committed_command in (
        ("appended-filter", "python scripts/validate.py"),
        ("trailing-filter", "python scripts/validate.py --ignore"),
    ):
        project_root = tmp_path / case
        manifest_path = _write_committed_legacy_project(
            project_root,
            committed_command=committed_command,
        )
        manifest_path.write_text(
            _manifest_text(
                "python scripts/validate.py --ignore tests/test_demo.py",
            ),
            encoding="utf-8",
        )
        exits.append(
            cmd_plan_lock(
                _lock_args(
                    manifest_path,
                    project_root,
                    legacy_baseline=True,
                    reason="Filtering arguments must not weaken legacy validation",
                )
            )
        )

    assert exits == [2, 2]


def test_legacy_baseline_accepts_overlapping_command_strengthening(
    tmp_path: Path,
) -> None:
    from maid_runner.core.plan_lock import capture_legacy_baseline_evidence

    manifest_path = _write_committed_legacy_project(
        tmp_path,
        committed_additional_commands=(
            "python scripts/validate.py tests/test_demo.py",
        ),
    )
    manifest_path.write_text(
        _manifest_text(
            "python scripts/validate.py tests/test_demo.py",
            additional_commands=("python scripts/validate.py tests/test_other.py",),
        ),
        encoding="utf-8",
    )

    evidence = capture_legacy_baseline_evidence(
        manifest_path,
        tmp_path,
        "Each prior command has one additive current counterpart",
    )

    assert len(evidence.commands) == 2
    assert {command.exit_code for command in evidence.commands} == {0}


def test_legacy_baseline_lock_creation_is_atomic_and_preserves_race_artifacts(
    tmp_path: Path,
) -> None:
    invalid_root = tmp_path / "invalid"
    invalid_manifest = _write_committed_legacy_project(
        invalid_root,
        validation_lock_payload="validation garbage",
    )
    _strengthen_validate_command(invalid_manifest)

    invalid_exit = cmd_plan_lock(
        _lock_args(
            invalid_manifest,
            invalid_root,
            legacy_baseline=True,
            reason="Validation-created garbage must not survive a failed lock",
        )
    )

    invalid_lock = default_plan_lock_path(invalid_root, "legacy-task")
    assert invalid_exit == 2
    assert invalid_lock.read_text(encoding="utf-8") == "validation garbage"

    competitor_payload = json.dumps(
        {
            "manifest_path": "manifests/competitor.manifest.yaml",
            "manifest_hash": "sha256:competitor",
            "test_hashes": {},
            "created_at": "2026-07-13T00:00:00Z",
            "revision": 1,
            "revisions": [],
            "red_evidence": None,
            "legacy_baseline": None,
            "agent": None,
        },
        indent=2,
    )
    competitor_root = tmp_path / "competitor"
    competitor_manifest = _write_committed_legacy_project(
        competitor_root,
        validation_lock_payload=competitor_payload,
        ignore_maid=True,
    )
    _strengthen_validate_command(competitor_manifest)

    competitor_exit = cmd_plan_lock(
        _lock_args(
            competitor_manifest,
            competitor_root,
            legacy_baseline=True,
            reason="A concurrent valid lock must never be overwritten",
        )
    )

    competitor_lock = default_plan_lock_path(competitor_root, "legacy-task")
    assert competitor_exit == 2
    assert competitor_lock.read_text(encoding="utf-8") == competitor_payload


@pytest.mark.parametrize("validate_exit", [1, 2])
def test_legacy_baseline_rejects_non_green_validation(
    tmp_path: Path, validate_exit: int
) -> None:
    manifest_path = _write_committed_legacy_project(
        tmp_path, validate_exit=validate_exit
    )
    _strengthen_validate_command(manifest_path)

    exit_code = cmd_plan_lock(
        _lock_args(
            manifest_path,
            tmp_path,
            legacy_baseline=True,
            reason="Current validation must be green",
        )
    )

    assert exit_code == 2
    assert not default_plan_lock_path(tmp_path, "legacy-task").exists()


def test_legacy_baseline_rejects_validation_that_mutates_contract(
    tmp_path: Path,
) -> None:
    for target in (
        "manifests/legacy-task.manifest.yaml",
        "tests/test_demo.py",
    ):
        project_root = tmp_path / target.split("/")[0]
        manifest_path = _write_committed_legacy_project(
            project_root, validation_mutation=target
        )
        _strengthen_validate_command(manifest_path)

        exit_code = cmd_plan_lock(
            _lock_args(
                manifest_path,
                project_root,
                legacy_baseline=True,
                reason="Validation must not rewrite the captured contract",
            )
        )

        assert exit_code == 2
        assert not default_plan_lock_path(project_root, "legacy-task").exists()


def test_ordinary_no_run_lock_still_fails_e704(tmp_path: Path) -> None:
    manifest_path = _write_committed_legacy_project(tmp_path)

    assert cmd_plan_lock(_lock_args(manifest_path, tmp_path, no_run=True)) == 0

    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=True,
        changed_paths={"manifests/legacy-task.manifest.yaml"},
        plan_lock_scope="task",
    )

    assert _codes(errors) == [ErrorCode.RED_PHASE_EVIDENCE_MISSING]


def test_plan_lock_preserves_positional_agent_compatibility() -> None:
    agent = AgentProvenance(model="legacy-positional-caller")

    lock = PlanLock(
        "manifests/task.manifest.yaml",
        "sha256:manifest",
        {},
        "2026-07-13T00:00:00Z",
        1,
        (),
        None,
        agent,
    )

    assert lock.agent is agent
    assert lock.legacy_baseline is None


def test_tampered_legacy_baseline_fails_e705(tmp_path: Path) -> None:
    tamper_cases = (
        "command-mismatch",
        "missing-reason",
        "nonzero-command",
        "misclassified-command",
        "artifact-delta",
        "file-delta",
        "simultaneous-channels",
    )
    for tamper_case in tamper_cases:
        project_root = tmp_path / tamper_case
        manifest_path = _write_committed_legacy_project(project_root)
        _strengthen_validate_command(manifest_path)
        assert (
            cmd_plan_lock(
                _lock_args(
                    manifest_path,
                    project_root,
                    legacy_baseline=True,
                    reason="Audited migration",
                )
            )
            == 0
        )
        lock_path = default_plan_lock_path(project_root, "legacy-task")
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        legacy = payload["legacy_baseline"]
        if tamper_case == "command-mismatch":
            legacy["commands"][0]["command"] = "python other.py"
        elif tamper_case == "missing-reason":
            legacy["reason"] = ""
        elif tamper_case == "nonzero-command":
            legacy["commands"][0]["exit_code"] = 1
        elif tamper_case == "misclassified-command":
            legacy["commands"][0]["classification"] = "red"
        elif tamper_case == "artifact-delta":
            legacy["contract_delta"]["artifacts_added"] = ["src/demo.py:extra"]
        elif tamper_case == "file-delta":
            legacy["contract_delta"]["files_removed"] = ["edit:src/demo.py"]
        elif tamper_case == "simultaneous-channels":
            payload["red_evidence"] = {
                "red": True,
                "captured_at": "2026-07-13T00:00:00Z",
                "commands": [
                    {
                        "command": legacy["commands"][0]["command"],
                        "exit_code": 1,
                        "output_tail": "expected red",
                        "classification": "red",
                    }
                ],
            }
        lock_path.write_text(json.dumps(payload), encoding="utf-8")

        errors = enforce_plan_locks(
            ManifestChain(project_root / "manifests", project_root),
            project_root,
            require_plan_lock=True,
            require_red_evidence=True,
            changed_paths={"manifests/legacy-task.manifest.yaml"},
            plan_lock_scope="task",
        )

        assert _codes(errors) == [ErrorCode.RED_PHASE_EVIDENCE_INVALID]
        assert "legacy baseline" in errors[0].message.lower()


def test_plan_status_distinguishes_legacy_baseline_from_red_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest_path = _write_committed_legacy_project(tmp_path)
    _strengthen_validate_command(manifest_path)
    assert (
        cmd_plan_lock(
            _lock_args(
                manifest_path,
                tmp_path,
                legacy_baseline=True,
                reason="Audited migration",
            )
        )
        == 0
    )
    capsys.readouterr()

    assert cmd_plan_status(_status_args(manifest_path, tmp_path, json_mode=True)) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["red_evidence"] is None
    assert payload["legacy_baseline"]["kind"] == "legacy_baseline"

    assert cmd_plan_status(_status_args(manifest_path, tmp_path, json_mode=False)) == 0
    text = capsys.readouterr().out
    assert "Red evidence: none" in text
    assert "Legacy baseline: recorded" in text


def test_plan_lock_docs_describe_legacy_baseline_boundaries() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    specs = Path("docs/maid_specs.md").read_text(encoding="utf-8")

    assert "--legacy-baseline" in readme
    assert "red evidence" in readme
    assert "tracked" in specs
    assert "green" in specs
    assert "red_evidence: null" in specs
    assert "--require-red-evidence" in specs
