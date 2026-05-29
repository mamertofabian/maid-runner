# MAID Validate Hardening Backlog

## Purpose

This document records confirmed `maid validate` and `maid verify` loopholes
that can let an AI agent claim MAID compliance without satisfying the real
validation intent. The goal is fail-closed validation: a green command should
mean the declared artifacts were covered by real, runnable tests inside the
manifest boundary.

MAID's core contract is:

1. The manifest declares the intended file and artifact boundary.
2. Behavioral tests prove the declared artifacts are exercised.
3. Implementation validation proves the code defines the declared artifacts.
4. Coherence, file tracking, worktree scope, and test execution make the result
   hard to game.

## Prior Hardening Wave

The original `030` hardening backlog items have been promoted into active
manifests:

- `030-01` fails closed on missing or empty manifest discovery.
- `030-02` makes `--coherence` affect `maid validate` exit status.
- `030-03` rejects manifest paths that escape the project root.
- `030-04` rejects duplicate YAML mapping keys.
- `030-05` promotes missing behavioral coverage to E200 errors.
- `030-06` exposes strict validation flags.
- `030-07` adds file-tracking fail gates.
- `030-08` adds `maid validate --run-tests`.
- `030-09` adds a worktree scope gate.
- `030-10` adds the combined `maid verify` done gate.

Those items are no longer the active backlog. The current backlog below is the
post-030 second pass.

## Confirmed Loopholes

### Post-032 Status

The original post-030 loopholes below were promoted as `032-01` through
`032-03`. A 2026-05-29 follow-up probe confirmed a remaining test-runner
configuration gap after those closures.

### 1. Name-Only Behavioral Coverage Still Covers Local Code

**Scenario:** A manifest declares `src/widget.py:update`, while the test file
defines and calls its own local `update()` without importing `src.widget`.
Implementation validation returned success.

**Observed command and exit:** A throwaway project under `/tmp` was validated
through `ValidationEngine.validate_all(..., mode=IMPLEMENTATION)`. The probe
reported `no_import_local_function: success=True passed=1 failed=0`.

**Why this matters:** An agent can satisfy E200 by writing a local helper with
the same name as the production artifact. This gives a green implementation
gate without proving the production artifact is imported or exercised.

**Code path:** `maid_runner/core/identity.py::match_artifact_to_references`
still accepts name-only fallback when no identity-bearing reference exists.
Python and TypeScript behavioral collectors can emit local function calls as
ordinary references with no `import_source`.

**Closure shape:** Require identity-backed coverage for declared production
artifacts that have a known module path. Preserve legitimate imported calls and
member access by enriching collectors where needed, not by restoring broad
name-only fallback.

### 2. Local Member Access Can Cover Declared Attributes

**Scenario:** A manifest declares `src/widget.py:Settings.timeout`. A test
imports `Settings` only to cover the class, then asserts against
`Local().timeout`. Implementation validation returned success. A test defining
its own local `Settings.timeout` with no production import also returned
success.

**Observed command and exit:** Throwaway `ValidationEngine` probes reported
`import_class_local_attribute success=True` and
`local_same_class_attr_no_import success=True`.

**Why this matters:** Class coverage and attribute coverage can be split across
unrelated objects. A manifest can appear to cover a production class attribute
while only touching a local fake.

**Code path:** `maid_runner/validators/python.py` records bare attribute names
for unresolved member access, and `maid_runner/core/identity.py` allows
name-only fallback for attributes when no matching identity-bearing attribute
reference is present.

**Closure shape:** Attribute coverage should carry owner/module identity when
it comes from an imported class/object, and unresolved local member access
should not cover a declared owned production attribute.

### 3. Verify Accepts Non-Test `validate:` Commands

**Scenario:** A manifest lists a real test file in `files.read`, but its
`validate:` command is `python -c 'raise SystemExit(0)'`. The static behavioral
and implementation gates pass, the no-op command exits 0, and `maid verify`
reports `PASS tests`.

**Observed command and exit:** A throwaway project run through
`maid_runner.cli.commands._main.main(["verify", "--keep-going"])` returned
`exit=0` and printed all stages as passing.

**Why this matters:** The combined done gate can execute no tests while still
claiming that the tests stage passed. This is a direct selective-compliance
path: the manifest can keep real tests in `files.read` for static reference
collection but run an unrelated green command.

**Code path:** `maid_runner/core/_validation_test_artifacts.py::find_test_files`
uses `files.read` and `validate:` commands for static discovery, while
`maid_runner/core/test_runner.py::run_tests` executes whatever commands the
manifest declares. No gate verifies that executed commands are test-runner
commands targeting the discovered test files.

**Closure shape:** Add a validation/test-command integrity check for
non-snapshot feature, fix, and refactor manifests. `maid verify` and
`maid validate --run-tests` should fail when a manifest has behavioral test
files but no validate command that runs those tests through a recognized test
runner.

### 4. `maid verify` Is Not Strict By Default

**Scenario:** A test imports and calls a declared production artifact but has no
assertions. `maid verify` exits 0 by default. `maid verify --strict` exits 1 on
the same project.

**Observed command and exit:** Throwaway probes reported
`verify_no_assertions_default exit=0` and
`verify_no_assertions_strict exit=1`.

**Why this matters:** The command positioned as the automation-safe done gate
still allows assertion-free behavioral tests unless the caller remembers to add
`--strict`. An agent can claim `maid verify` passed while tests only execute
the artifact without checking observable behavior.

**Code path:** `maid_runner/cli/commands/verify.py::cmd_verify` only enables
assertion checks, stub checks, and warning failure when `--strict` or individual
strict flags are passed.

**Closure shape:** Make `maid verify` strict by default, with an explicit
advisory escape hatch if interactive workflows still need permissive behavior.
The JSON and text output should make strict failures visible and structured.

### 5. Pytest Config `addopts` Can Deselect or Avoid Behavioral Tests

**Status:** The reproduced `pyproject.toml` pytest `addopts` bypass is
promoted as `044-01-reject-pytest-config-selector-addopts`. Follow-up coverage
for other pytest config sources remains separate deferred scope.

**Scenario:** A manifest declares `src/widget.py:update`, lists
`tests/test_widget.py` in `files.read`, and uses
`python -m pytest tests -q` as its `validate:` command. The test file imports
and asserts against `update()` in `test_declared_behavior`, but project pytest
configuration sets `addopts = '-k test_other'` or `addopts = '--collect-only'`.

**Observed command and exit:** Throwaway projects under `/tmp` were validated
through `maid_runner.cli.commands._main.main(["verify", "--no-changed-scope"])`.
Both probes reported `Verify: PASS` and `verify_exit=0` even though the
declared behavioral test would fail if executed, and `--collect-only` executes
no tests at all.

**Why this matters:** The 032 command-integrity gate verifies that the manifest
command structurally targets the discovered test directory, but pytest can
change execution through project config outside the manifest command text. An
agent can hide a failing behavioral test behind config-level selectors while
still using an apparently valid test-runner command.

**Code path:** `maid_runner/core/_validation_test_artifacts.py::
validate_manifest_test_commands` checks discovered files against command
targets and now rejects effective `pyproject.toml` pytest `addopts` values that
inject known selector or non-executing flags. The guard reuses
`maid_runner/core/_test_runner_invocation.py` classifiers for command
arguments, `PYTEST_ADDOPTS`, command-line `--override-ini`, and pyproject
addopts inspection. It also respects pytest config precedence so ignored
pyproject addopts do not produce false positives.

**Closure shape:** `044-01` fails closed for the reproduced `pyproject.toml`
`addopts` path when the effective pytest command can inherit known selector or
non-executing flags. Pytest can also load addopts from `pytest.ini`, `tox.ini`,
and `setup.cfg`; those formats are not part of this closure and should be
covered by a follow-up draft before expanding the guard.

## Gradual Closure Backlog

1. Require identity-backed behavioral coverage for production artifacts.
   Promoted as `032-01`.
2. Reject local member access as owned production attribute coverage unless it
   carries owner/module identity. Promoted as part of `032-01`.
3. Fail `maid verify` and `maid validate --run-tests` when `validate:` commands
   do not run the manifest's behavioral test files. Promoted as `032-02`.
4. Make `maid verify` strict by default. Promoted as `032-03`.
5. Reject reproduced `pyproject.toml` pytest `addopts` that can deselect
   declared behavioral tests or switch the runner into non-executing modes.
   Promoted as `044-01`. Follow-up coverage for `pytest.ini`, `tox.ini`, and
   `setup.cfg` is deferred until a separate scoped draft exists.
6. After those gates are stable, consider making strict identity coverage and
   assertion enforcement the default for directory-wide `maid validate` in a
   major-version release.

## Suggested Acceptance Criteria

For each closure item, include adversarial tests that prove the old gaming path
fails:

- The command exits non-zero or the API result has `success=False`.
- JSON output reports a structured error code and location when the entry point
  is CLI-facing.
- Text output names the exact manifest, file, artifact, or command that failed.
- Positive tests prove legitimate imported artifact use still passes.
- No closure relies on documentation telling agents to run a different command.

## Verification Notes

The current findings were exercised with throwaway projects under `/tmp` using
local `ValidationEngine` calls and the local CLI entry point via
`maid_runner.cli.commands._main.main`.

Planning inventory started under `manifests/drafts/032-*` for the post-030
hardening pass. The child contracts now live under `manifests/032-01` through
`manifests/032-03`; the remaining draft epic is inactive roadmap inventory.

The 2026-05-29 pytest-config finding was reproduced with `pyproject.toml`
`[tool.pytest.ini_options].addopts` set to `--collect-only` and `-k test_other`.
The pyproject closure is promoted as
`manifests/044-01-reject-pytest-config-selector-addopts.manifest.yaml`; the
consumed `044-00` epic remains under `manifests/drafts/` only as an archived
historical pointer.
