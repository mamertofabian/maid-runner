# MAID Runner

[![PyPI version](https://badge.fury.io/py/maid-runner.svg)](https://badge.fury.io/py/maid-runner)
[![Python Version](https://img.shields.io/pypi/pyversions/maid-runner.svg)](https://pypi.org/project/maid-runner/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A tool-agnostic validation framework and Python library for the Manifest-driven AI Development (MAID) methodology. MAID Runner validates that code artifacts align with declarative YAML manifests, ensuring architectural integrity in AI-assisted development. Integrates with [ArchSpec](https://archspec.dev) for spec-to-code pipelines.

**[Watch the introductory video](https://youtu.be/0a9ys-F63fQ)**

> [Full AI Compiler workflow guide](docs/ai-compiler-workflow.md)

## Why MAID Runner?

LLMs generate code based on statistical likelihood, optimizing for "plausibility" rather than architectural soundness. Without intervention, this leads to "AI Slop" -- code that is syntactically valid but architecturally chaotic.

**MAID Runner enforces three-stream validation:**
- **Acceptance (WHAT)**: Immutable tests from specifications define system behavior
- **Structural (SKELETON)**: AST-level verification that code matches manifest contracts
- **Unit (HOW)**: Implementation-level tests verify internal correctness

This transforms AI from a "Junior Developer" requiring reactive code review into a "Stochastic Compiler" that translates rigid specifications into implementation details.

> [Full philosophy documentation](docs/maid-philosophy-and-vision.md)

## Supported Languages

| Language | Extensions | Parser | Key Features |
|----------|------------|--------|--------------|
| **Python** | `.py` | AST (built-in) | Classes, functions, methods, attributes, type hints, async/await, decorators |
| **TypeScript/JS** | `.ts`, `.tsx`, `.js`, `.jsx` | tree-sitter | Classes, interfaces, type aliases, enums, namespaces, generics, JSX/TSX; React and Angular through TypeScript-backed parsing |
| **Svelte** | `.svelte` | tree-sitter | Components, props, exports, script blocks, reactive statements |

### Validator Plugins

For language requests, use the validator plugin path instead of adding new
in-tree parsers to this repository. See
[docs/validator-plugin-authoring.md](docs/validator-plugin-authoring.md) for the
plugin contract, `maid_runner.validators` entry-point packaging, conformance
kit usage, `maid validators` audit command, and support boundary.

## Quick Start

```bash
# Install
pip install maid-runner  # or: uv pip install maid-runner

# Initialize MAID in your project
maid init

# Interactive guide
maid howto --section quickstart

# Brownfield entry: rank existing files, then generate reviewed drafts per change
maid bootstrap --rank --limit 20
maid manifest from-diff --base-ref <parent-branch> --slug describe-the-change
maid validate manifests/drafts/describe-the-change.manifest.yaml --mode schema --quiet
```

## Installation

### Claude Code Plugin (Recommended)

```bash
/plugin marketplace add aidrivencoder/claude-plugins
/plugin install maid-runner@aidrivencoder
```

### From PyPI

```bash
pip install maid-runner              # Python only (core — no tree-sitter)
pip install maid-runner[all]         # All language support (TypeScript, Svelte)
pip install maid-runner[typescript]  # TypeScript/JS only
pip install maid-runner[watch]       # File watching for TDD mode
```

### Multi-Tool Support

```bash
maid init                        # Claude Code (default)
maid init --tool codex           # Codex repo skills
maid init --tool cursor          # Cursor IDE
maid init --tool windsurf        # Windsurf IDE
maid init --tool generic         # Generic MAID.md
```

### Repo-Level Claude Install

Use `maid init --tool claude` inside shared repositories as a repo-level Claude install
for the MAID-only Claude skills, implementation-review agent, and marked
`CLAUDE.md` guidance. The `.claude/skills` source payload includes the
current MAID workflow skills for planning, plan review, implementation,
implementation review, evolution, auditing, and incident logging.

### Repo-Level Codex Install

Use `maid init --tool codex` inside repositories that should receive the
repo-owned Codex MAID skills. It installs `.codex/manifest.json`, the
distributed `.codex/skills` payload, skill-local agent metadata, and a marked
MAID Runner section in `AGENTS.md`.

## CLI Reference

| Command | Purpose | Key Options |
|---------|---------|-------------|
| `maid validate [manifest]` | Validate manifest against code | `--mode schema\|behavioral\|implementation`, `--artifact-coverage`, `--no-chain`, `--coherence`, `--file-tracking`, `--worktree-scope`, `--changed-scope`, `--json`, `--packet [path]`, `--watch`, `--watch-all` |
| `maid validators` | List discovered validator records for auditability | `--json` |
| `maid test` | Run validation commands from manifests | `--manifest <path>`, `--jobs N`, `--watch`, `--watch-all`, `--fail-fast`, `--json` |
| `maid verify` | Run the combined done gate | `--strict`, `--advisory`, `--artifact-coverage`, `--knockout`, `--knockout-limit N`, `--knockout-allow-dirty`, `--require-plan-lock`, `--require-red-evidence`, `--worktree-scope`, `--changed-scope`, `--no-changed-scope`, `--since`, `--base-ref`, `--test-jobs N`, `--json`, `--packet [path]` |
| `maid plan lock\|revise\|status <manifest>` | Tamper-evident plan locks over a manifest and its behavioral tests | `--reason` (revise), `--json` (status), `--project-root` |
| `maid task start\|stop\|status` | Manage the active task manifest pointer in `.maid/active-manifest` | `start <manifest-path>`, `status --json` |
| `maid hook scope-check` | Check whether a file path is inside the active task manifest scope | `--path <file-path>`, `--stdin`, `--strict` |
| `maid benchmark [project ...]` | Run local benchmark timings for MAID validation gates | `--manifest-dir`, `--command-prefix`, `--repeat`, `--json-output`, `--markdown-output`, `--json` |
| `maid incident capture\|update\|list` | Store and review caller-asserted gaming incident records | `capture --manifest <path> --packet <path> --rejected-diff <path> --tags <comma-list>`, `update <incident-path> --chosen-diff <path>`, `list --tag <tag> --json` |
| `maid snapshot <file>` | Generate manifest from existing code | `--output-dir`, `--output`, `--with-tests`, `--force`, `--dry-run`, `--json` |
| `maid snapshot-system` | Aggregate all active manifests | `--output`, `--manifest-dir` |
| `maid bootstrap [directory]` | Bootstrap manifests for an existing project | `--output-dir`, `--exclude`, `--include-private`, `--dry-run`, `--json` |
| `maid learn` | Refresh the deterministic Outcome index | `--manifest-dir`, `--output`, `--include-status`, `--json`, `--quiet` |
| `maid recall` | Search the deterministic Outcome index | `--text`, `--tag`, `--path`, `--artifact`, `--validation-command`, `--manifest-slug`, `--allow-stale-index`, `--json` |
| `maid insights` | Aggregate deterministic Outcome insights | `--index`, `--manifest-dir`, `--allow-stale-index`, `--limit`, `--json` |
| `maid manifests <file>` | List manifests referencing a file | `--manifest-dir`, `--quiet` |
| `maid files` | Show file tracking status | `--manifest-dir`, `--quiet` |
| `maid graph` | Knowledge graph operations | `query`, `export`, `analyze` |
| `maid coherence` | Run coherence checks | `--checks`, `--exclude`, `--json` |
| `maid schema` | Display manifest JSON Schema | |
| `maid audit supersessions` | Audit supersession artifact preservation | `--manifest-dir`, `--seal`, `--unseal`, `--lock`, `--json`, `--quiet` |
| `maid init` | Initialize MAID in project | `--tool claude\|codex\|cursor\|windsurf\|generic\|auto` |
| `maid howto` | Interactive methodology guide | `--section intro\|principles\|workflow\|quickstart\|patterns\|commands\|troubleshooting` |
| `maid manifest create <file>` | Create manifest for a file | `--goal`, `--artifacts`, `--dry-run` |
| `maid chain log` | Show manifest event log | `--until-seq N`, `--version-tag TAG`, `--active`, `--json` |
| `maid chain replay` | Preview effective artifacts at a point in time | `--until-seq N`, `--version-tag TAG`, `--json` |
| `maid serve` | Run a long-lived validator daemon over a Unix socket | `--socket`, `--pidfile`, `--project-root`, `--client-timeout` |

**General exit codes:** `0` = success, `1` = validation failure or internal
error, `2` = usage error. Command-specific contracts can define narrower meanings.
For example, `maid hook scope-check` exits `2` for a denied scope decision.
Use `--quiet` for automation.

### Failure Packets For Agent Retries

Agent retry loops can run gates with packet output:

```bash
maid validate --packet
maid verify --packet
```

Each packet-aware gate writes a failure packet only when the run fails with exit
code 1. A passing packet-aware run writes no packet and removes any stale packet at that path, so agents cannot replay outdated failure state. Passing `--packet`
without a path uses
`.maid/last-failure-packet.json`.

On failure, read the packet before retrying. It includes the failed command,
exit code, project root, failed manifest excerpts, diagnostics with
`next_action`, failed-command output tails, and environment versions. Retry
loops should respect `next_action` kinds, stay within manifest scope, and stop
at the documented attempt bound instead of silently weakening tests or manifests.

## Edit-Time Scope Enforcement

MAID can expose the active implementation contract to editor and agent hooks so
out-of-scope writes are rejected before handoff. After promoting a draft
manifest, start the task pointer:

```bash
maid task start manifests/<slug>.manifest.yaml
```

At handoff, after implementation review and Outcome capture, clear the pointer
idempotently:

```bash
maid task stop
```

The active task resolver uses `MAID_ACTIVE_MANIFEST` first, then the
single-line `.maid/active-manifest` file written by `maid task start`, and then
falls back to no active task. `maid task status --json` reports the resolved
path and whether it came from the environment, the file, or no active task.

Hook integrations call `maid hook scope-check --path <file-path>` or pipe an
agent event object to `maid hook scope-check --stdin` with a JSON
`{"path": "..."}` payload. The command prints one JSON decision object:

```json
{"decision": "allow"|"deny", "reason": "...", "active_manifest": "..."}
```

It exits with exit code 0 for allow, 2 for deny, and 1 for internal errors. With
no active task, the default fail-open policy allows the write with reason
`no-active-task`; broken hook execution also fails open so an interactive editor
is not bricked. Locked-down autonomous loops should pass `--strict`, which
turns both no-active-task and internal-error outcomes into denies.

With an active task, the hook allows the manifest's `files.create`,
`files.edit`, and `files.delete` paths, the active manifest file, declared test
files, and paths under `manifests/drafts/`. Other paths are denied with a
reason naming the active manifest and nearby declared scope entries. The hook
is fast advisory infrastructure only: maid verify changed-scope checks remain
the authoritative handoff evidence, and hook decisions do not add `ErrorCode`
entries.

Hook wiring is installed by `maid init` payloads. Claude receives PreToolUse settings for write/edit tool events.
Cursor receives `hooks.json`, and Codex receives managed `AGENTS.md` guidance
for the same pre-edit decision semantics.

Run `maid howto --section commands` for detailed usage and examples. For common
failure modes, see [docs/troubleshooting.md](docs/troubleshooting.md) or run
`maid howto --section troubleshooting`.

### Common Workflows

```bash
# Validate all manifests (chains enabled by default)
maid validate

# Validate a single manifest
maid validate manifests/add-auth.manifest.yaml

# Validate without chain merging
maid validate manifests/add-auth.manifest.yaml --no-chain

# Validate behavioral tests
maid validate manifests/add-auth.manifest.yaml --mode behavioral

# End the approved planning loop with a tamper-evident plan lock
maid plan lock manifests/add-auth.manifest.yaml

# Validate with coherence checks
maid validate --coherence

# TDD watch mode (single manifest)
maid test --manifest manifests/add-auth.manifest.yaml --watch

# Multi-manifest watch (entire codebase)
maid test --watch-all

# Run all validation commands
maid test

# Branch handoff gate for humans, CI, and AI agents
maid verify --base-ref <parent-branch>

# Implementation handoff gate requiring the approved plan lock and red phase
maid verify --require-plan-lock --require-red-evidence

# Opt-in Python-only constraint evidence gates for high-risk review
maid validate --artifact-coverage manifests/add-auth.manifest.yaml
maid verify --artifact-coverage --knockout

# Brownfield onboarding: rank candidates before adding contracts
maid bootstrap --rank --limit 20

# Draft a manifest from one implemented change; choose exactly one baseline
maid manifest from-diff --since <commit> --slug describe-the-change
maid manifest from-diff --base-ref <parent-branch> --slug describe-the-change
maid manifest from-diff --worktree --slug describe-the-change

# JSON output for CI/CD
maid validate --json

# Audit supersession drops and seal current legacy drops
maid audit supersessions --manifest-dir manifests --json
maid audit supersessions --manifest-dir manifests --seal
```

### Plan Locks And Red-Phase Evidence

`maid plan lock <manifest>` seals the approved manifest and its behavioral test
files after the planning loop passes behavioral validation and the user approves
the plan. `maid plan revise <manifest> --reason "<text>"` records intentional
plan changes with a required reason, and `maid plan status <manifest>` reports
lock state, hash matches or mismatches, and red evidence.

Red-phase evidence uses exit-code-only classification: pytest exit 1 is valid
red, exits 2/3/4/5 are invalid, and exit 0 means the tests already pass and are
not red. `maid plan lock --no-run` records `red_evidence: null`.

Plan-lock enforcement is opt-in. The implementation handoff command
`maid verify --require-plan-lock --require-red-evidence` scopes requirement
errors to the task window: E700 PLAN_LOCK_MISSING, E704
RED_PHASE_EVIDENCE_MISSING, and E705 RED_PHASE_EVIDENCE_INVALID apply to active
manifests whose manifest file changed in the verify run. E704 also applies when
an in-scope manifest has no plan lock under `--require-red-evidence`. Integrity
errors apply regardless of task-window scope: E701
BEHAVIORAL_TEST_MODIFIED_AFTER_LOCK, E702
MANIFEST_CONTRACT_WEAKENED_AFTER_LOCK, E703 PLAN_LOCK_STALE, and E706
PLAN_LOCK_UNREADABLE.

### Constraint Evidence Gates

`maid verify --artifact-coverage` and `maid validate --artifact-coverage` run
the manifest's pytest-based `validate:` commands under coverage.py and fail
when a declared Python public function, method, or class body is never executed
by the tests. The gate is opt-in and Python-only. Attribute artifacts are
excluded, and a class passes when any declared method on the class executes.
Install the optional quality extra with `maid-runner[quality]`; requesting the
gate without that extra fails closed with `E307` semantics instead of silently
skipping the evidence check.

`maid verify --knockout` is an opt-in Python-only gate that replaces each
declared public function or method body with
`raise NotImplementedError("maid-knockout")`, runs the manifest's validate
commands, and restores the source file with hash verification. Use
`--knockout-limit` to bound the number of artifacts tested and
`--knockout-allow-dirty` when a reviewed workflow deliberately allows dirty
target files. Knockout runs in manifest declaration order and is not full mutation testing; it checks one bounded failure mode rather than promising general mutation coverage.

### CI/CD Integration

<!-- _ci_cd_integration_entrypoint -->

Use [CI/CD Integration](docs/ci-cd-integration.md) for GitHub Actions, GitLab
CI, Jenkins, CircleCI, and generic pipeline examples that run `maid verify`,
`maid test --json`, and publish `.maid/` JSON reports. GitHub users can also
start from the dedicated [GitHub Actions guide](docs/github-actions.md).

### File Tracking

When validating with manifest chains (default), MAID Runner reports file compliance status:

- **UNDECLARED**: Files not in any manifest (no audit trail)
- **REGISTERED**: Files tracked but incomplete (missing artifacts/tests)
- **TRACKED**: Files with full MAID compliance

### Changed-Scope Handoff Gate

`maid verify` runs changed-scope by default. Use it at branch handoff, review,
and CI boundaries to close the loophole where a file changed during the task is
listed only under `files.read` after the edit has already been committed.
Callers must opt out explicitly with `--no-changed-scope`.

Recommended branch review command:

```bash
maid verify --base-ref <parent-branch>
```

Use `--base-ref` for stacked branches because MAID compares from
`git merge-base <parent-branch> HEAD` to the current working tree. Use
`--since <commit-ish>` when the exact task baseline is known:

```bash
maid validate --changed-scope --since <task-start-commit>
maid verify --since <task-start-commit>
```

The baseline can also be recorded in active manifests:

```yaml
metadata:
  maid_task_base: <task-start-commit>
```

When `maid verify` runs without `--since`, `--base-ref`, or an unambiguous
`metadata.maid_task_base`, MAID fails closed with `E115` instead of guessing
`main`, `master`, `dev`, `development`, or a remote branch. Git does not retain
a reliable branch-origin fact after rebases and merges, and a default commit
count can miss task changes, so the baseline must be real evidence supplied by
the caller or manifest. `files.read` never grants write permission; changed
source files must be declared in `files.create`, `files.edit`, or
`files.delete`. Use `--include-tests` when the handoff should also enforce
changed test files.

Use `--worktree-scope` for fast live checks of uncommitted local changes. Use
`maid verify` for branch handoff because changed-scope checks committed,
staged, unstaged, and untracked files since the task baseline by default. Use
`maid validate --changed-scope` only when you want the lower-level validate
command to run the same gate explicitly.

### Brownfield Onboarding

For existing projects, start with a ranked adoption pass instead of bulk
snapshotting every file:

```bash
maid bootstrap --rank --limit 20
```

The ranked output is advisory and writes no manifests. It lists undeclared files
with raw `churn`, `inbound_refs`, and `public_artifacts` values, ordered by churn
descending, inbound references descending, public artifacts descending, then
path ascending. Use `--json` when automation needs the same raw signals.

Onboard the top files one at a time. For an implemented change, generate a draft
contract from the diff:

```bash
maid manifest from-diff --base-ref <parent-branch> --slug describe-the-change
```

`maid manifest from-diff` requires exactly one of `--since <commit>`,
`--base-ref <ref>`, or `--worktree`; MAID does not guess a baseline. Generated
manifests land in `manifests/drafts/` with `metadata.needs_review: true`, so the
author reviews the draft, replaces the goal placeholder, fills any placeholder
artifacts, clears `needs_review`, and then promotes through the draft workflow.

## Manifest Structure (v2 YAML)

```yaml
schema: "2"
goal: "Implement email validation"
type: feature
files:
  create:
    - path: validators/email_validator.py
      artifacts:
        - kind: class
          name: EmailValidator
        - kind: method
          name: validate
          of: EmailValidator
          args:
            - name: email
              type: str
          returns: bool
  read:
    - tests/test_email_validation.py
validate:
  - pytest tests/test_email_validation.py -v
```

V1 JSON manifests are auto-converted when loaded.

### Validation Modes

| Mode | Files | Behavior |
|------|-------|----------|
| **Strict** | `files.create` | Implementation must EXACTLY match declared artifacts |
| **Permissive** | `files.edit` | Implementation must CONTAIN declared artifacts |

### Artifact Kinds

**Common:** `class`, `function`, `method`, `attribute`

**TypeScript-specific:** `interface`, `type`, `enum`, `namespace`

### Angular TypeScript Boundary

Angular source files are supported as TypeScript files. MAID Runner collects
decorated classes, fields, methods, and signal-style `input()` / `output()`
fields through `TypeScriptValidator`; Angular decorator names and decorator
metadata are not public MAID artifacts.

Required-import validation uses the same TypeScript import scanner for Angular
standalone component imports and lazy `import()` route modules. Third-party
imports such as `@angular/core` remain package imports and do not satisfy
project-local required imports.

`maid snapshot` tracks literal Angular `templateUrl`, `styleUrl`, and
`styleUrls` companion files in `files.read` when those files exist. Template
HTML and CSS/SCSS contents are tracked as file boundaries, not parsed into
Angular artifacts.

### React TypeScript Boundary

React `.tsx` and `.jsx` files are supported through `TypeScriptValidator`.
MAID Runner collects ordinary TypeScript artifacts such as function
components, typed const components, custom hooks, provider functions, props
interfaces, and props type aliases. It also recognizes common inline wrapper
exports using `memo`, `React.memo`, `forwardRef`, `React.forwardRef`, and
anonymous default-exported arrow components as function artifacts.

Required-import validation uses TypeScript import identity for React tests and
components, including Testing Library test files, barrel imports,
`React.lazy(() => import(...))`, path aliases from `tsconfig.json`, and local
CSS module imports. Package imports such as `react`, `react-dom`, and
`@testing-library/*` remain external package imports and do not satisfy
project-local required imports.

`maid snapshot` tracks existing relative style and static asset imports from
React TSX/JSX files in `files.read`, including CSS modules, side-effect
stylesheets, SVGs, and other non-code assets. MAID Runner does not parse CSS,
assets, DOM behavior, React runtime semantics, React Native, Next.js, Remix,
Vite, or bundler-specific behavior as MAID artifacts.

### Manifest Event Log

MAID Runner v2.4.0 introduces an event-log system for tracking manifest history:

```yaml
schema: "2"
goal: "Add user authentication"
type: feature
sequence_number: 42         # optional — deterministic ordering
version_tag: "v2.4.0"       # optional — release label
```

**Inspect the event log:**
```bash
maid chain log                    # Full history (includes superseded)
maid chain log --until-seq 10     # Up to sequence 10
maid chain log --version-tag v2.4.0 --json
maid chain log --active           # Active manifests only
```

**Preview artifact state at a point in time:**
```bash
maid chain replay --until-seq 10 --json
maid chain replay --version-tag v2.4.0
```

The event log provides deterministic ordering via `sequence_number` (falls back to `created`), includes superseded manifests in the historical record, and supports point-in-time queries through `event_log_until()` and `replay_until()` APIs.

### Supersession Artifact Preservation

When manifest A supersedes manifest B, MAID Runner audits every public artifact
declared by B. Each superseded artifact must be accounted for by A in one of
three ways:

- Re-declare the artifact in A for the same file path.
- List the artifact's file under A's `files.delete` and ensure the file is gone.
- Declare the artifact under A's `removed_artifacts` and ensure the symbol is
  absent from the current source file.

If a replacement manifest drops artifacts without one of those structural
signals, `maid validate` reports `E110 ARTIFACT_DROPPED_BY_SUPERSESSION`.
This prevents a supersession from silently shrinking the validation surface.

Use the dedicated audit command to inspect these drops:

```bash
maid audit supersessions --manifest-dir manifests
maid audit supersessions --manifest-dir manifests --json
```

Brownfield repositories can seal existing legacy drops once:

```bash
maid audit supersessions --manifest-dir manifests --seal
```

This writes `.maid/legacy-grandfathered.lock`. The lock records each legacy
drop by superseding slug, superseding manifest content hash, superseded slug,
file path, and artifact key. After the lock exists, matching legacy drops are
reported as `E111 GRANDFATHERED_SUPERSESSION` info entries. New drops, or drops
from an edited superseding manifest whose content hash changed, are not covered
by the lock.

Re-sealing a repository with an existing sealed lock is blocked unless
`--unseal` is passed:

```bash
maid audit supersessions --manifest-dir manifests --seal --unseal
```

Treat `--unseal` as a deliberate migration action. It should be visible in
review because it can add or replace grandfathered drops.

To intentionally remove an artifact while superseding a manifest, declare it in
`removed_artifacts`:

```yaml
schema: "2"
goal: "Replace old auth helper"
type: refactor
supersedes:
  - add-old-auth-helper
removed_artifacts:
  - kind: function
    name: old_auth_helper
    file: src/auth/helpers.py
    reason: "Replaced by AuthService.authenticate"
files:
  edit:
    - path: src/auth/service.py
      artifacts:
        - kind: class
          name: AuthService
validate:
  - pytest tests/auth/test_service.py -v
```

`removed_artifacts` is not trusted as self-attestation. Implementation
validation verifies that the named symbol is absent from the referenced file and
reports `E311 REMOVED_ARTIFACT_STILL_PRESENT` if it is still defined, the file
cannot be parsed, the path escapes the project root, or no validator can inspect
that file type.

## Validator Daemon (`maid serve`)

A long-lived local daemon that exposes the validator over a Unix socket so
AI agents, editor integrations, and tight TDD loops can validate manifests
without paying Python startup per call. NDJSON protocol, repo-bound project
root, locked-down socket permissions.

```bash
maid serve --socket .maid/serve.sock --pidfile .maid/serve.pid
```

See [`docs/maid-serve.md`](docs/maid-serve.md) for protocol, methods,
security defaults, and example client.

## Development Workflow

### Phase 1: Goal Definition
Define the high-level feature or bug fix.

### Phase 2: Planning Loop
1. Create manifest: `maid manifest create <file> --goal "Description"`
2. Create behavioral tests in `tests/`
3. Validate: `maid validate <manifest> --mode behavioral`
4. Iterate until validation passes

For larger batches, use draft manifests as the planning queue: keep mutable
planning inventory in `manifests/drafts/`, promote one implementation-sized draft
into `manifests/`, then implement and validate the promoted path. See
[Draft Manifest Workflow](docs/draft-manifest-workflow.md).

### Phase 3: Implementation Loop
1. Implement code per manifest
2. Validate: `maid validate <manifest>`
3. Run tests: `maid test --manifest <manifest>`
4. Iterate until all tests pass

### Phase 4: Integration
Verify complete chain: `maid validate` and `maid test` pass for all active manifests.

## Library API

MAID Runner provides a Python library API for direct integration with tools, CI/CD, and custom scripts.

### Basic Validation

```python
from maid_runner import validate, validate_all

# Validate a single manifest
result = validate("manifests/add-auth.manifest.yaml")
if result.success:
    print("All checks passed")
else:
    for error in result.errors:
        print(f"{error.code.value}: {error.message}")

# Validate all manifests in directory
batch = validate_all("manifests/")
print(f"{batch.passed}/{batch.total_manifests} passed")
```

### Manifest Chain Operations

```python
from maid_runner import ManifestChain

chain = ManifestChain("manifests/")

for m in chain.active_manifests():
    print(f"{m.slug}: {m.goal}")

artifacts = chain.merged_artifacts_for("src/auth/service.py")
```

### Loading and Saving Manifests

```python
from maid_runner import load_manifest, save_manifest

manifest = load_manifest("manifests/add-auth.manifest.yaml")  # YAML v2 or JSON v1
print(manifest.goal)
save_manifest(manifest, "manifests/copy.manifest.yaml")
```

### Snapshot Generation

```python
from maid_runner import generate_snapshot

manifest = generate_snapshot("src/auth/service.py")
print(f"Found {len(manifest.all_file_specs[0].artifacts)} artifacts")
```

### JSON Output for Tool Integration

```python
from maid_runner import validate

result = validate("manifests/add-auth.manifest.yaml")
print(result.to_json())  # Structured JSON output
```

### Custom Validator Registration

```python
from maid_runner import ValidatorRegistry, BaseValidator, CollectionResult

class GoValidator(BaseValidator):
    @classmethod
    def supported_extensions(cls):
        return (".go",)

    def collect_implementation_artifacts(self, source, file_path):
        return CollectionResult(artifacts=[], language="go", file_path=str(file_path))

    def collect_behavioral_artifacts(self, source, file_path):
        return CollectionResult(artifacts=[], language="go", file_path=str(file_path))

ValidatorRegistry.register(GoValidator)
```

## MAID Ecosystem

| Tool | Purpose |
|------|---------|
| **[MAID Agents](https://github.com/mamertofabian/maid-agents)** | Automated workflow orchestration using Claude Code agents |
| **[MAID Runner MCP](https://github.com/mamertofabian/maid-runner-mcp)** | MCP server exposing validation to AI agents |
| **[MAID LSP](https://github.com/mamertofabian/maid-lsp)** | Language Server Protocol for real-time IDE validation |
| **[MAID for VS Code](https://github.com/mamertofabian/vscode-maid)** | VS Code/Cursor extension with manifest explorer and diagnostics |
| **[Claude Plugins](https://github.com/aidrivencoder/claude-plugins)** | Plugin marketplace including MAID Runner |
| **[ArchSpec](https://archspec.dev)** | AI-powered spec generation with MAID manifest export |

## Development Setup

```bash
# Install dependencies
uv sync
uv sync --group dev

# Run tests
uv run python -m pytest tests/ -v

# Code quality
make format      # Auto-fix formatting
make lint        # Check style
make type-check  # Type checking
```

## Project Structure

```
maid-runner/
├── docs/                    # Documentation
├── manifests/               # Active task manifests (YAML v2)
│   └── drafts/              # Mutable draft manifest queue
├── tests/
│   ├── core/                # Core module tests
│   ├── validators/          # Validator tests
│   ├── coherence/           # Coherence check tests
│   ├── graph/               # Knowledge graph tests
│   ├── compat/              # Compatibility tests
│   ├── cli/                 # CLI tests
│   ├── integration/         # Integration tests
│   └── e2e/                 # End-to-end tests
├── maid_runner/
│   ├── core/                # Manifest loading, validation, chain, types
│   ├── validators/          # Language-specific artifact collectors
│   ├── graph/               # Knowledge graph (manifest relationships)
│   ├── coherence/           # Architectural coherence checks
│   ├── compat/              # V1 JSON backward compatibility
│   ├── cli/commands/        # CLI command modules
│   └── schemas/             # JSON Schema (v1, v2)
├── examples/                # Example scripts
└── .claude/                 # Claude Code configuration
```

## Testing

```bash
uv run python -m pytest tests/ -v                    # All tests
uv run python -m pytest tests/core/ -v               # Core tests
uv run python -m pytest tests/validators/ -v          # Validator tests
maid test                                            # MAID validation commands
```

## Requirements

- Python 3.10+
- Core: `jsonschema`, `pyyaml`
- Optional: `tree-sitter`, `tree-sitter-typescript` (TypeScript/JS and Angular `.ts` support), `tree-sitter-svelte` (Svelte support)
- Dev: `black`, `ruff`, `mypy`, `pytest`

## Contributing

This project dogfoods MAID methodology. All changes require:
1. A manifest in `manifests/`
2. Behavioral tests in `tests/`
3. Passing structural validation
4. Passing behavioral tests

Use `manifests/drafts/` for mutable planned work that has not been promoted
into the active manifest chain yet.

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CLAUDE.md](CLAUDE.md) for guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.
