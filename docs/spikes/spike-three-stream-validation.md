# Three-Stream Validation: Integrating ATDD, arch-spec, and MAID Runner

**Version:** 1.0
**Date:** 2026-03-25
**Status:** Spike / Architectural Proposal
**Scope:** arch-spec, MAID Runner v2, maid-agents

---

## Abstract

This document proposes a three-stream validation architecture that combines the
best ideas from Acceptance Test Driven Development (ATDD), arch-spec's
specification capabilities, and MAID Runner's structural validation into a
unified, closed-loop AI development pipeline. The result is a system where
AI-generated code is constrained by three independent verification layers:
acceptance tests (WHAT the system does), structural validation (the code
SKELETON matches the contract), and unit tests (HOW internal logic works).

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Prior Art Analysis](#2-prior-art-analysis)
3. [Architecture Overview](#3-architecture-overview)
4. [Stream Definitions](#4-stream-definitions)
5. [Translation Layer](#5-translation-layer)
6. [Leakage Detection](#6-leakage-detection)
7. [Updated MAID Workflow](#7-updated-maid-workflow)
8. [Manifest Schema Additions](#8-manifest-schema-additions)
9. [arch-spec Enhancements](#9-arch-spec-enhancements)
10. [MAID Runner v2 Enhancements](#10-maid-runner-v2-enhancements)
11. [maid-agents Integration](#11-maid-agents-integration)
12. [Implementation Roadmap](#12-implementation-roadmap)
13. [Appendix A: ATDD Comparison](#appendix-a-atdd-comparison)
14. [Appendix B: Existing Tool Landscape](#appendix-b-existing-tool-landscape)

---

## 1. Problem Statement

### The TDD Failure Mode in AI-Assisted Development

AI coding agents (including top-tier models like Claude Opus) consistently fail
to follow Test-Driven Development properly. The observed failure pattern:

1. Agent claims to follow TDD
2. Agent writes some tests
3. Agent implements the feature
4. Tests are incomplete or coupled to the implementation the agent imagined
5. The implementation drives the tests, not the other way around

This happens because **a single context window cannot maintain the separation
between test-writer and implementer**. The test-writer's analysis bleeds into
the implementer's thinking. Tests end up validating the implementation that was
imagined, not the behavior that was specified.

### The Handoff Problem

arch-spec generates comprehensive specifications (data models, API endpoints,
features, Gherkin test cases, implementation prompts) but has no enforcement
mechanism. After exporting a ZIP file, the workflow becomes "good luck" — there
is no feedback loop verifying that implemented code matches the specification.

### The Manual Authoring Problem

MAID Runner provides structural and behavioral validation, but requires manual
manifest authoring. For a project with 50+ features, writing manifests by hand
is a significant overhead that limits adoption.

### The Single-Stream Problem

MAID Runner validates one test stream (behavioral tests from Phase 2). ATDD
argues that a single test stream is insufficient — you need at least two
independent streams to properly constrain AI development. Uncle Bob's insight:

> "The two different streams of tests cause Claude to think much more deeply
> about the structure of the code. It can't just willy-nilly plop code around
> and write a unit test for it. It is also constrained by the structure of the
> acceptance tests."
> — Robert C. Martin

---

## 2. Prior Art Analysis

### ATDD (swingerman/atdd)

An implementation of Robert C. Martin's Acceptance Test Driven Development for
Claude Code. Adapted from Uncle Bob's empire-2025 project.

**Key concepts adopted:**
- Two-stream testing (acceptance + unit) constrains development
- Given/When/Then specs in domain language, free of implementation details
- Implementation leakage detection (spec-guardian agent)
- Immutable specs — the implementer cannot modify acceptance criteria
- Mutation testing as a third quality layer

**Key concepts not adopted:**
- Parser -> IR -> test generator pipeline (arch-spec eliminates this need)
- `.txt` spec files requiring custom parsing (arch-spec has structured JSON)
- Pipeline-builder agent per project (replaced by translation layer)

**Source:** https://github.com/swingerman/atdd

### Matt Pocock's TDD Skill (mattpocock/skills)

A Claude Code skill focused on behavioral testing through public interfaces.

**Key insight adopted:**
- Tests should read like specifications — "user can checkout with valid cart"
- Tests verify behavior through public interfaces, not implementation details
- Good tests survive complete internal refactors

**Key insight not adopted:**
- Vertical slicing (one test at a time) — MAID uses "all tests first" approach

**Source:** https://github.com/mattpocock/skills/tree/main/tdd

### Superpowers (obra/superpowers)

An agentic skills framework with 107K+ GitHub stars. Enforces TDD by deleting
code written before tests exist.

**Key insight adopted:**
- Fresh subagents per task prevent context drift
- Enforcement through tooling, not just instructions

**Source:** https://github.com/obra/superpowers

### TDD Guard (nizos/tdd-guard)

Hook-based TDD enforcement for Claude Code. Blocks Write/Edit operations that
violate TDD principles.

**Key insight adopted:**
- Real-time enforcement via PreToolUse hooks
- Prevention is more effective than post-hoc validation

**Source:** https://github.com/nizos/tdd-guard

---

## 3. Architecture Overview

```
+---------------------------------------------------------+
|                    arch-spec (Layer 5)                   |
|              "What should we build?"                     |
|                                                         |
|  Structured Data (Pydantic/JSON):                       |
|  +----------+ +------------+ +----------------------+   |
|  | Entities | | API Routes | | Gherkin Test Cases    |  |
|  | & Fields | | & Methods  | | (Given/When/Then)     |  |
|  +----+-----+ +-----+------+ +----------+-----------+   |
|       |              |                   |               |
+-------+--------------+-------------------+--------------+
        |              |                   |
   +----v--------------v-------------------v----+
   |        Translation Layer (NEW)              |
   |  "Convert specs to enforceable contracts"   |
   |                                             |
   |  +-----------------+  +------------------+  |
   |  | MAID Manifests  |  | Acceptance Test  |  |
   |  | (structural     |  | Scaffolds        |  |
   |  |  contracts)     |  | (behavioral      |  |
   |  |                 |  |  contracts)       |  |
   |  +--------+--------+  +--------+---------+  |
   +-----------+---------------------+------------+
               |                     |
   +-----------v---------------------v------------+
   |          MAID Runner v2 (Layer 2)             |
   |     "Verify it's correct - THREE streams"     |
   |                                               |
   |  Stream 1          Stream 2         Stream 3  |
   |  ACCEPTANCE         STRUCTURAL      UNIT      |
   |  (from Gherkin)    (from manifest)  (from dev)|
   |                                               |
   |  "Does it do       "Does the code   "Does the |
   |   what the spec     have the right   internal  |
   |   says?"            skeleton?"       logic     |
   |                                      work?"    |
   |  +----------+     +----------+    +---------+  |
   |  |Leakage   |     |AST-based |    |Standard |  |
   |  |Detection |     |Artifact  |    |Test     |  |
   |  |(from ATDD|     |Validation|    |Execution|  |
   |  |guardian) |     |(existing)|    |(existing|  |
   |  +----------+     +----------+    +---------+  |
   +-----------------------------------------------+
               |
   +-----------v-----------------------------------+
   |          maid-agents (Layer 4)                 |
   |     "Build it autonomously"                    |
   |                                               |
   |  Constrained by ALL THREE streams:            |
   |  - Can't fake behavior (acceptance tests)     |
   |  - Can't skip structure (manifest artifacts)  |
   |  - Can't skip correctness (unit tests)        |
   +-----------------------------------------------+
```

### The Full-Cycle Pipeline

```
Layer 5: arch-spec          "What should we build?"   (specification)
Layer 4: Translation Layer  "Here are the contracts"  (generated from arch-spec)
Layer 3: maid-agents        "Build it autonomously"   (orchestration)
Layer 2: MAID Runner v2     "Verify it's correct"     (three-stream validation)
Layer 1: Code + Tests       "The actual product"      (output)
```

No single tool in the market provides this complete loop.

---

## 4. Stream Definitions

### Stream 1: Acceptance Validation (WHAT)

**Purpose:** Verify that the system does what the specification says it should
do, as described in domain language.

**Source:** arch-spec's Gherkin test cases, translated into executable test
scaffolds.

**Characteristics:**
- Tests describe external observables only
- No references to implementation details (class names, API endpoints, database
  tables, framework terms)
- Immutable during implementation — the AI cannot modify acceptance tests
- Survive complete internal refactors
- A non-developer should understand what each test verifies

**Validation command example:**
```bash
pytest tests/acceptance/ -v
```

**Lifecycle:**
- Created during Phase 2 (from arch-spec import or manual authoring)
- Locked before Phase 3 begins
- Never modified during implementation
- Only modified if the specification changes (requires human approval)

### Stream 2: Structural Validation (SKELETON)

**Purpose:** Verify that the code defines the declared artifacts (classes,
functions, attributes, parameters, return types) as specified in the manifest.

**Source:** MAID manifests (generated from arch-spec or hand-authored).

**Characteristics:**
- AST-based validation — parses source code and checks artifact existence
- Language-aware (Python via stdlib ast, TypeScript via tree-sitter)
- Validates strict mode (creatableFiles: exact match) and permissive mode
  (editableFiles: contains at least)
- Manifest chain tracks chronological evolution

**Validation command example:**
```bash
maid validate manifests/feature-auth.manifest.yaml --mode implementation
```

**Lifecycle:**
- Created during Phase 2 (from arch-spec import or manual authoring)
- Validated via AST analysis during Phase 3
- Manifest chain is immutable — only the current task's manifest can change

### Stream 3: Unit Test Validation (HOW)

**Purpose:** Verify that the internal logic of the implementation is correct.

**Source:** Unit tests written during Phase 3 implementation.

**Characteristics:**
- Written by the developer/AI during implementation
- Test internal structure and logic
- May use mocks, fixtures, and implementation-aware assertions
- May change during refactoring (unlike acceptance tests)
- Follow the unit testing rules defined in `docs/unit-testing-rules.md`

**Validation command example:**
```bash
pytest tests/unit/ -v
```

**Lifecycle:**
- Created during Phase 3 alongside implementation
- May be refactored during Phase 3.5
- Must remain green after any change

### Three-Stream Comparison

| Aspect | Stream 1: Acceptance | Stream 2: Structural | Stream 3: Unit |
|--------|---------------------|---------------------|----------------|
| Verifies | WHAT the system does | Code SKELETON matches contract | HOW internal logic works |
| Source | arch-spec Gherkin | MAID manifest | Developer/AI during implementation |
| Created | Phase 2 | Phase 2 | Phase 3 |
| Mutable during impl? | No (immutable) | No (manifest is contract) | Yes (written alongside code) |
| Implementation-aware? | No (domain language only) | Yes (artifact names/types) | Yes (internal details) |
| Survives refactor? | Yes | Yes (public API unchanged) | May need updates |
| Validated by | Test execution | AST analysis | Test execution |

---

## 5. Translation Layer

The translation layer converts arch-spec's structured data into MAID-consumable
contracts. This replaces ATDD's parser -> IR -> generator pipeline.

### 5.1 Entity -> Manifest Artifacts

```
arch-spec Entity:
  Entity(
    name="User",
    description="Application user",
    fields=[
      EntityField(name="email", type="string", unique=True, required=True),
      EntityField(name="password_hash", type="string", required=True),
      EntityField(name="display_name", type="string"),
      EntityField(name="created_at", type="datetime", generated=True),
    ]
  )

Generated MAID manifest artifact:
  files:
    create:
      - path: src/models/user.py       # from ProjectStructure spec
        expect:
          - class: User
          - attr: User.email (type: str)
          - attr: User.password_hash (type: str)
          - attr: User.display_name (type: str)
          - attr: User.created_at (type: datetime)
```

### 5.2 API Endpoint -> Manifest Artifacts

```
arch-spec ApiEndpoint:
  ApiEndpoint(
    path="/users",
    description="User management",
    methods=["GET", "POST"],
    auth=True,
    roles=["admin"]
  )

Generated MAID manifest artifact:
  files:
    create:
      - path: src/routes/users.py
        expect:
          - function: get_users() -> list[User]
          - function: create_user(data: UserCreate) -> User
```

### 5.3 Gherkin Test Cases -> Acceptance Test Scaffolds

```
arch-spec GherkinTestCase:
  {
    "feature": "User Authentication",
    "title": "Login with valid credentials",
    "scenarios": [{
      "name": "Successful login",
      "steps": [
        {"type": "given", "text": "the user has a registered account"},
        {"type": "when", "text": "the user enters valid credentials"},
        {"type": "then", "text": "the user is logged in successfully"}
      ]
    }]
  }

Generated acceptance test scaffold (pytest):
  class TestUserAuthentication:
      """Acceptance tests for: User Authentication

      Generated from arch-spec. DO NOT add implementation details.
      These tests verify WHAT the system does, not HOW.
      """

      def test_successful_login(self, app):
          """Scenario: Successful login
          Given the user has a registered account
          When the user enters valid credentials
          Then the user is logged in successfully
          """
          # GIVEN: the user has a registered account
          user = register_user(email="bob@example.com", password="secret123")

          # WHEN: the user enters valid credentials
          result = login(email="bob@example.com", password="secret123")

          # THEN: the user is logged in successfully
          assert result.success
          assert result.user.email == "bob@example.com"
```

### 5.4 Domain-to-Code Mapping

The fixture code in acceptance test scaffolds (`register_user`, `login`) requires
a mapping between domain concepts and code-level operations. This is configured
once per project:

```yaml
# domain-mapping.yaml
project:
  language: python
  test_framework: pytest

concepts:
  "registered user":
    setup: "register_user(email={email}, password={password})"
    model: User

  "registers with email {email} and password {password}":
    action: "register(email={email}, password={password})"

  "logs in":
    action: "login(email={email}, password={password})"

  "is logged in":
    assertion: "assert result.success"

  "registered users":
    query: "count_users()"

  "{n} registered user(s)":
    assertion: "assert count_users() == {n}"
```

**Generation strategy:**
1. arch-spec generates an initial mapping from data model + API endpoints
2. The developer refines domain concepts to match their codebase
3. The mapping is committed to the repository alongside specs
4. Subsequent acceptance test generation uses the refined mapping

This replaces ATDD's entire pipeline infrastructure with a simple, editable
configuration file.

### 5.5 Feature -> Manifest Group

```
arch-spec FeatureModule:
  FeatureModule(
    name="Authentication",
    description="User registration, login, and session management"
  )

Generated MAID manifest:
  schema: "2"
  goal: "Implement Authentication feature"
  type: feature

  acceptance:
    specs: specs/test-cases.md#user-authentication
    tests: tests/acceptance/test_auth.py
    mapping: domain-mapping.yaml

  files:
    create:
      - path: src/auth/service.py
        expect:
          - class: AuthService
          - method: AuthService.register(email: str, password: str) -> User
          - method: AuthService.login(email: str, password: str) -> LoginResult
          - method: AuthService.logout(session_id: str) -> bool

      - path: src/auth/models.py
        expect:
          - class: LoginResult
          - attr: LoginResult.success (type: bool)
          - attr: LoginResult.user (type: User)
          - attr: LoginResult.session_id (type: str)

    read:
      - src/models/user.py

  validate:
    - pytest tests/acceptance/test_auth.py -v
    - pytest tests/unit/test_auth_service.py -v
```

---

## 6. Leakage Detection

Adapted from ATDD's spec-guardian concept. Leakage detection scans acceptance
tests for implementation details that should not be present.

### 6.1 What Constitutes Leakage

Acceptance tests must describe external observables only. The following are
violations:

**Code references:**
- Class names: `AuthService`, `UserRepository`, `CartController`
- Function/method names: `create_user()`, `validate_input()`, `process_payment()`
- Variable names or internal state
- Module or file path references

**Infrastructure references:**
- Database operations: `session.query()`, `db.commit()`, `SELECT FROM`
- HTTP details: `status_code`, `response.headers`, `Content-Type`
- API endpoints: `/api/users`, `POST /login`
- Queue/cache keys

**Framework references:**
- Framework terms: middleware, controller, reducer, resolver, provider
- ORM terms: model, migration, schema, relation
- Library-specific concepts: hook, store, dispatch

### 6.2 What Is Acceptable

- Domain language: user, order, product, payment, cart
- Observable actions: registers, logs in, adds to cart, checks out
- Observable outcomes: is registered, cart contains, receives email
- Business rules: within 24 hours, exceeds limit, is expired
- User-facing concepts: error message, confirmation, notification

### 6.3 Detection Implementation

```python
class LeakageDetector:
    """Scans acceptance tests for implementation coupling.

    Runs as part of 'maid validate --mode full' on files referenced
    in the manifest's acceptance.tests field.
    """

    # Pattern categories with descriptions for violation messages
    PATTERNS = {
        "internal_import": {
            "patterns": [
                r"from\s+(?:src|app|lib)\.\S+\s+import",
                r"import\s+(?:src|app|lib)\.\S+",
            ],
            "message": "Acceptance tests should not import internal modules",
            "suggestion": "Use the application's public interface or test fixtures",
        },
        "database_access": {
            "patterns": [
                r"session\.",
                r"\.query\(",
                r"\.commit\(",
                r"\.rollback\(",
                r"db\.",
                r"SELECT\s+",
                r"INSERT\s+",
            ],
            "message": "Database operations are implementation details",
            "suggestion": "Assert on domain outcomes, not database state",
        },
        "http_details": {
            "patterns": [
                r"status_code",
                r"response\.headers",
                r"content.type",
                r"response\.json\(",
            ],
            "message": "HTTP details are implementation details",
            "suggestion": "Assert on domain outcomes, not HTTP responses",
        },
        "framework_terms": {
            "patterns": [
                r"@router\.",
                r"@app\.",
                r"middleware",
                r"controller",
                r"repository",
                r"\.dependency",
            ],
            "message": "Framework terms are implementation details",
            "suggestion": "Use domain language to describe behavior",
        },
    }

    def check(self, test_file: Path) -> list[LeakageViolation]:
        """Scan a file and return all leakage violations found."""
        ...

    def report(self, violations: list[LeakageViolation]) -> str:
        """Format violations as a human-readable report."""
        ...
```

### 6.4 Report Format

```
Leakage Detection: tests/acceptance/test_auth.py
-----------------------------------------------
Line 3:  "from src.auth.service import AuthService"
         Violation: Acceptance tests should not import internal modules
         Suggestion: Use the application's public interface or test fixtures

Line 15: "assert response.status_code == 201"
         Violation: HTTP details are implementation details
         Suggestion: Assert on domain outcomes, not HTTP responses

Line 22: "session.query(User).count()"
         Violation: Database operations are implementation details
         Suggestion: Assert on domain outcomes, not database state

Summary: 3 violations found in 1 file
Result: NEEDS CLEANUP
```

### 6.5 When Leakage Detection Runs

- During `maid validate --mode full` (on files listed in `acceptance.tests`)
- During `maid validate --mode behavioral` (as part of Phase 2 planning)
- On-demand via `maid check-leakage tests/acceptance/`
- Optionally as a PreToolUse hook (warn when editing acceptance test files)

---

## 7. Updated MAID Workflow

### Phase 1: Goal Definition

Unchanged from current MAID workflow. The developer defines the high-level goal.

**Alternative entry point:** Import from arch-spec export, which auto-generates
manifests and acceptance test scaffolds (skipping manual authoring).

```bash
maid import arch-spec ./my-project-specs/
```

### Phase 2: Planning Loop

Enhanced with acceptance test creation and leakage checking.

1. **Draft the manifest** (structural contract)
   - Declare files, artifacts, types
   - If imported from arch-spec, review and refine the generated manifest

2. **Draft acceptance tests** (behavioral contract)
   - Write tests that describe WHAT the system does in domain language
   - If imported from arch-spec, review and refine generated scaffolds
   - No implementation details allowed

3. **Leakage check** on acceptance tests
   ```bash
   maid check-leakage tests/acceptance/test_feature.py
   ```

4. **Behavioral validation** (existing)
   ```bash
   maid validate manifest.yaml --validation-mode behavioral --use-manifest-chain
   ```

5. Iterate until all checks pass and the plan is approved.

**Gate:** Manifest validated, acceptance tests written, leakage check clean.

### Phase 3: Implementation

Enhanced with three-stream validation.

1. AI reads manifest to load context (existing)
2. AI runs acceptance tests — confirms they FAIL (red)
3. AI implements code to pass acceptance tests (Stream 1: WHAT)
4. AI writes unit tests during implementation (Stream 3: HOW)
5. MAID validates structural artifacts exist (Stream 2: SKELETON)
6. All three streams must be green before Phase 3 is complete

**Critical rule:** The AI cannot modify acceptance tests during implementation.
Acceptance tests are the contract. If an acceptance test seems wrong, the AI
must stop and ask the developer.

```bash
# Full three-stream validation
maid validate manifest.yaml --mode implementation --use-manifest-chain
# Runs: acceptance tests + structural validation + unit tests
```

### Phase 3.5: Refactoring

Enhanced with acceptance test stability guarantee.

1. Acceptance tests MUST still pass (they are implementation-agnostic)
2. Structural validation must pass (public API unchanged)
3. Unit tests may be updated (they test HOW, which may change)

This is where three-stream validation shines: acceptance tests guarantee that
refactoring doesn't break behavior, even if unit tests change.

### Phase 4: Integration

Enhanced with optional mutation testing.

1. All manifests validated
2. All three test streams green across all active manifests
3. **Optional: Mutation testing** (from ATDD)
   ```bash
   maid mutate src/auth/  # or: mutmut run --paths-to-mutate src/auth/
   ```
   Target: 90%+ mutation score. Remaining survivors documented as equivalent
   mutants.

### Workflow Diagram

```
Phase 1    Phase 2                     Phase 3                Phase 3.5    Phase 4
-------    -------                     -------                ---------    -------

Goal  -->  Manifest (structural)  -->  Implement code    -->  Refactor --> Integrate
           Acceptance tests (WHAT)     Unit tests (HOW)       All green    All green
           Leakage check               Structural check       Acceptance   Mutation
           Behavioral validation       All 3 streams green    stable       testing
                                                                           (optional)
```

---

## 8. Manifest Schema Additions

### 8.1 Acceptance Field

New top-level `acceptance` field in MAID v2 manifest schema:

```yaml
schema: "2"
goal: "Implement user authentication"
type: feature

# NEW: Acceptance test configuration
acceptance:
  # Reference to the arch-spec Gherkin source (for traceability)
  specs: specs/test-cases.md#user-authentication

  # Path to the acceptance test file(s)
  tests:
    - tests/acceptance/test_auth.py

  # Domain-to-code mapping configuration
  mapping: domain-mapping.yaml

files:
  create:
    - path: src/auth/service.py
      expect:
        - class: AuthService
        - method: AuthService.login(email: str, password: str) -> LoginResult

validate:
  # Stream 1: Acceptance tests (WHAT)
  - pytest tests/acceptance/test_auth.py -v
  # Stream 3: Unit tests (HOW)
  - pytest tests/unit/test_auth_service.py -v
```

### 8.2 Validation Mode Extensions

The `--mode` flag gains a new option:

| Mode | Streams Validated | Use During |
|------|-------------------|------------|
| `behavioral` | Tests USE declared artifacts | Phase 2 planning |
| `implementation` | Code DEFINES artifacts + test execution | Phase 3 |
| `full` | All 3 streams + leakage detection + coherence | Phase 4 integration |

### 8.3 Leakage Rules Configuration

Optional per-project configuration for leakage detection:

```yaml
# .maid/leakage-rules.yaml
# Customize leakage detection for this project

# Additional patterns to flag
custom_violations:
  - pattern: "redis\\.get|redis\\.set"
    message: "Cache operations are implementation details"
    suggestion: "Assert on domain outcomes"

# Patterns to allow (domain-specific technical terms)
allow:
  - "database"   # This project IS a database tool — "database" is domain language
  - "query"      # Same — querying IS the domain
```

---

## 9. arch-spec Enhancements

### 9.1 MAID Manifest Exporter

New export capability in arch-spec that generates MAID v2 manifests from
structured specifications.

**Location:** `arch-spec/backend/app/services/maid_export_service.py`

**Input:** All arch-spec spec types (DataModel, Api, Features, TestCases,
ProjectStructure)

**Output:** MAID v2 YAML manifests, one per feature module

**Translation rules:**

| arch-spec Section | MAID Manifest Output |
|---|---|
| `Entity` | `class` artifact + `attr` artifacts for each field |
| `Relationship` (1:many) | `attr` artifact with list type |
| `Relationship` (many:many) | Junction entity class + attributes |
| `ApiEndpoint` (GET) | `function` artifact with return type |
| `ApiEndpoint` (POST) | `function` artifact with typed args |
| `ApiEndpoint` (PUT/PATCH) | `function` artifact with id + data args |
| `ApiEndpoint` (DELETE) | `function` artifact with id arg |
| `FeatureModule` | Groups related file artifacts into one manifest |
| `GherkinTestCase` | `acceptance.specs` reference + test scaffold |
| `ProjectStructure` | File paths for manifest `files` sections |

### 9.2 Acceptance Test Scaffold Exporter

New export capability that generates executable test stubs from Gherkin test
cases.

**Input:** `TestCases` spec + `domain-mapping.yaml` (if available)

**Output:** pytest/jest test files with Given/When/Then structure

**Without domain mapping:** Generates test stubs with TODO placeholders:

```python
def test_successful_login(self):
    """Scenario: Successful login"""
    # GIVEN: the user has a registered account
    # TODO: Set up a registered user

    # WHEN: the user enters valid credentials
    # TODO: Perform login action

    # THEN: the user is logged in successfully
    # TODO: Assert login success
    raise NotImplementedError("Fill in acceptance test fixture code")
```

**With domain mapping:** Generates complete test code using the mapping.

### 9.3 Updated ZIP Export Structure

```
project-name.zip
+-- README.md
+-- CLAUDE.md                          # Enhanced with MAID validation commands
+-- .cursorrules
+-- .windsurfrules
+-- specs/
|   +-- project-name-basics.md
|   +-- project-name-tech-stack.md
|   +-- project-name-requirements.md
|   +-- project-name-features.md
|   +-- project-name-pages.md
|   +-- project-name-data-model.md
|   +-- project-name-api-endpoints.md
|   +-- project-name-test-cases.md      # Gherkin source (human-readable)
|   +-- project-name-ui-design.md
|   +-- implementation-prompts.md
+-- manifests/                          # NEW: MAID v2 manifests
|   +-- feature-auth.manifest.yaml
|   +-- feature-user-management.manifest.yaml
|   +-- feature-dashboard.manifest.yaml
|   +-- ...
+-- tests/                              # NEW: Acceptance test scaffolds
|   +-- acceptance/
|       +-- test_auth.py
|       +-- test_user_management.py
|       +-- test_dashboard.py
|       +-- ...
+-- domain-mapping.yaml                 # NEW: Domain-to-code mapping (initial)
```

### 9.4 Enhanced CLAUDE.md Generation

The generated CLAUDE.md includes MAID validation instructions:

```markdown
## Development Workflow

This project uses MAID (Manifest-driven AI Development) for validation.

### Validation Commands

# Validate all manifests
maid validate

# Run all tests (acceptance + unit)
maid test

# Check acceptance tests for implementation leakage
maid check-leakage tests/acceptance/

### Rules

- Never modify acceptance tests without explicit permission
- Every feature has a manifest in manifests/
- Run maid validate before committing
- Both acceptance tests AND unit tests must pass
```

---

## 10. MAID Runner v2 Enhancements

### 10.1 Three-Stream Validation Engine

The validation engine gains awareness of acceptance vs unit test streams:

```python
class ValidationEngine:
    def validate(self, manifest: Manifest, mode: ValidationMode) -> ValidationResult:
        results = []

        if mode in (ValidationMode.BEHAVIORAL, ValidationMode.FULL):
            # Check that tests USE declared artifacts
            results.append(self._validate_behavioral(manifest))

        if mode in (ValidationMode.IMPLEMENTATION, ValidationMode.FULL):
            # Stream 2: Check that code DEFINES declared artifacts (AST)
            results.append(self._validate_structural(manifest))

        if mode == ValidationMode.FULL:
            # Stream 1: Run acceptance tests
            if manifest.acceptance and manifest.acceptance.tests:
                results.append(self._run_acceptance_tests(manifest))
                # Leakage detection on acceptance test files
                results.append(self._check_leakage(manifest))

        # Stream 1 + 3: Run all validation commands
        for cmd in manifest.validate:
            results.append(self._run_command(cmd))

        return ValidationResult.merge(results)
```

### 10.2 `maid import arch-spec` Command

New CLI command that consumes arch-spec exports:

```bash
# Import from an unzipped arch-spec export
maid import arch-spec ./my-project-specs/

# Options
maid import arch-spec ./specs/ --output-dir manifests/
maid import arch-spec ./specs/ --test-framework pytest  # or jest, junit
maid import arch-spec ./specs/ --dry-run                # preview without writing
maid import arch-spec ./specs/ --json                   # output as JSON
```

**Import process:**
1. Read arch-spec markdown files from `specs/` directory
2. Parse data model entities, API endpoints, features, test cases
3. Generate MAID v2 manifests (one per feature)
4. Generate acceptance test scaffolds (one per feature)
5. Generate initial domain-mapping.yaml
6. Report what was generated

### 10.3 `maid check-leakage` Command

New CLI command for leakage detection:

```bash
# Check specific file
maid check-leakage tests/acceptance/test_auth.py

# Check all acceptance tests referenced by manifests
maid check-leakage

# Check with custom rules
maid check-leakage --rules .maid/leakage-rules.yaml
```

### 10.4 Mutation Testing Integration (Optional)

New CLI command wrapping mutation testing frameworks:

```bash
# Run mutation testing on source files referenced by manifest
maid mutate manifests/feature-auth.manifest.yaml

# Run on specific directory
maid mutate src/auth/

# Use specific framework
maid mutate src/auth/ --framework mutmut  # or stryker, pit
```

**Supported frameworks** (auto-detected by language):
- Python: mutmut
- TypeScript/JavaScript: Stryker
- Java: PIT (pitest)

---

## 11. maid-agents Integration

### 11.1 Agent Constraints

When maid-agents orchestrates implementation, each agent is constrained by all
three streams:

```
maid-manifest-architect:
  - Reads arch-spec export
  - Generates manifests + acceptance test scaffolds
  - Runs leakage detection on generated acceptance tests

maid-test-designer:
  - Writes acceptance tests (Stream 1) - domain language only
  - Cannot reference implementation details
  - Tests are locked after Phase 2

maid-developer:
  - Cannot modify acceptance tests (immutable contract)
  - Writes unit tests (Stream 3) during implementation
  - Must pass all three streams before reporting done

maid-auditor:
  - Validates all three streams are green
  - Runs leakage detection
  - Optional: runs mutation testing
```

### 11.2 Context Isolation

Following ATDD's insight about context bleed-through:

- The **test-designer** agent never sees implementation code
- The **developer** agent never sees the specification reasoning (only the
  manifest and acceptance tests)
- The **auditor** agent sees everything but cannot modify anything

This prevents the TDD failure mode where test-writer knowledge bleeds into
implementer thinking.

---

## 12. Implementation Roadmap

### Priority 1: MAID Runner v2 - Leakage Detection

**Effort:** Small
**Dependencies:** None
**Value:** Immediate standalone value, no arch-spec dependency

Implement the `LeakageDetector` class and `maid check-leakage` command. Can be
used with hand-written acceptance tests today, before any arch-spec integration.

### Priority 2: MAID Runner v2 - Three-Stream Manifest Schema

**Effort:** Medium
**Dependencies:** v2 manifest schema (YAML format)

Add the `acceptance` field to the manifest schema. Update the validation engine
to distinguish acceptance vs unit test streams. Add `--mode full` validation.

### Priority 3: arch-spec - MAID Manifest Exporter

**Effort:** Medium
**Dependencies:** MAID Runner v2 manifest schema finalized

Build the translation layer in arch-spec's backend. New service that walks
Pydantic models (Entity, ApiEndpoint, FeatureModule) and emits MAID v2 YAML
manifests. Estimated ~500-800 lines.

### Priority 4: arch-spec - Acceptance Test Scaffold Exporter

**Effort:** Medium
**Dependencies:** Manifest exporter (Priority 3)

Build the Gherkin -> executable test scaffold generator. Supports pytest and
jest initially. Uses domain-mapping.yaml for fixture code.

### Priority 5: MAID Runner v2 - `maid import arch-spec`

**Effort:** Small
**Dependencies:** Manifest exporter output format (Priority 3)

CLI command that reads arch-spec export directory and invokes the library API.
Thin command — most logic is in the translation layer.

### Priority 6: arch-spec - Domain-to-Code Mapping

**Effort:** Medium
**Dependencies:** Scaffold exporter (Priority 4)

New spec type or configuration in arch-spec that maps domain concepts to code
operations. Auto-generated initial mapping from data model + API endpoints.
User-editable.

### Priority 7: MAID Runner v2 - Mutation Testing

**Effort:** Small
**Dependencies:** None (standalone)

`maid mutate` command that wraps mutmut/Stryker. Auto-detects language and
framework. Reports mutation score and surviving mutants. Lowest priority but
completes the quality picture.

### Timeline Estimate

```
Priorities 1-2: During MAID Runner v2 rewrite (current work)
Priorities 3-5: After v2 stabilizes (arch-spec integration sprint)
Priorities 6-7: Polish phase
```

---

## Appendix A: ATDD Comparison

### What ATDD Does That This Architecture Adopts

| ATDD Concept | Adoption |
|---|---|
| Two-stream testing | Extended to three streams |
| Given/When/Then specs | arch-spec Gherkin test cases |
| Spec-guardian leakage detection | `maid check-leakage` command |
| Immutable specs during implementation | Acceptance tests locked in Phase 2 |
| Mutation testing | Optional Phase 4.5 via `maid mutate` |
| Multi-agent team (spec-writer, implementer, reviewer) | Maps to maid-agents roles |

### What ATDD Does That This Architecture Replaces

| ATDD Concept | Replacement | Rationale |
|---|---|---|
| `.txt` spec files | arch-spec structured JSON | Already machine-readable, no parsing needed |
| Parser -> IR -> generator pipeline | Translation layer | arch-spec data IS the IR; pipeline is unnecessary |
| Pipeline-builder agent | `maid import arch-spec` | One-time import, not per-feature pipeline generation |
| Generated tests are gitignored | Acceptance tests are committed | They are the contract, not disposable artifacts |

### What This Architecture Adds Beyond ATDD

| Capability | Details |
|---|---|
| Structural validation (Stream 2) | AST-based artifact checking, not just test execution |
| Manifest chaining / chronology | Tracks evolution of codebase over time |
| File tracking analysis | Detects undeclared, registered, and fully tracked files |
| Specification generation | arch-spec generates specs from requirements via AI |
| Full-cycle pipeline | Spec -> Contract -> Build -> Validate (no tool in market does this) |

---

## Appendix B: Existing Tool Landscape

### Tools Evaluated

| Tool | Stars | Approach | Key Insight |
|---|---|---|---|
| [obra/superpowers](https://github.com/obra/superpowers) | 107K | 7-phase agentic framework | Enforcement by deletion; fresh subagents prevent context drift |
| [swingerman/atdd](https://github.com/swingerman/atdd) | Low | Uncle Bob's ATDD for Claude Code | Two-stream testing; implementation leakage detection |
| [mattpocock/skills/tdd](https://github.com/mattpocock/skills/tree/main/tdd) | 9.3K | Behavioral TDD skill | Tests through public interfaces; tests read like specifications |
| [nizos/tdd-guard](https://github.com/nizos/tdd-guard) | 1.8K | Hook-based TDD enforcement | Real-time prevention via PreToolUse hooks |
| [alexop.dev multi-agent TDD](https://alexop.dev/posts/custom-tdd-workflow-claude-code-vue/) | N/A | Context-isolated TDD subagents | Single-context TDD fails due to knowledge bleed-through |

### Market Gap

No existing tool provides:
1. AI-generated specifications (arch-spec)
2. Automatic contract generation from those specs (translation layer)
3. Three-stream validation (acceptance + structural + unit)
4. Implementation leakage detection
5. Chronological tracking via manifest chains

This architecture fills the gap by connecting existing Codefrost tools into a
unified pipeline.

---

## References

- Robert C. Martin, "empire-2025" — https://github.com/unclebob/empire-2025
- swingerman/atdd — https://github.com/swingerman/atdd
- mattpocock/skills — https://github.com/mattpocock/skills
- obra/superpowers — https://github.com/obra/superpowers
- nizos/tdd-guard — https://github.com/nizos/tdd-guard
- alexop.dev, "Forcing Claude Code to TDD" — https://alexop.dev/posts/custom-tdd-workflow-claude-code-vue/
- MAID Specification v1.3 — `docs/maid_specs.md`
- Unit Testing Rules — `docs/unit-testing-rules.md`
