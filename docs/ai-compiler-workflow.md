# The AI Compiler: ArchSpec + MAID Runner Workflow

## What It Is

A pipeline that turns a project description into **verified, working code** — with the AI constrained by machine-checkable contracts at every step.

```
"Build me a CRM with contacts and activity tracking"
        │
        ▼
   ┌─────────────┐
   │  ArchSpec    │  Generates structured specifications
   │  (SaaS/OSS) │  Data models, APIs, pages, test cases
   └──────┬──────┘
          │ Export as MAID project
          ▼
   ┌─────────────┐
   │  MAID        │  Manifests = machine-checkable contracts
   │  Manifests   │  What classes, functions, types MUST exist
   └──────┬──────┘
          │ AI implements against contracts
          ▼
   ┌─────────────┐
   │  AI Agent    │  Writes code, runs tests, retries on failure
   │  (Claude)    │  Constrained by manifests — can't hallucinate
   └──────┬──────┘
          │ Validates every change
          ▼
   ┌─────────────┐
   │  MAID Runner │  Checks code matches contracts (AST-level)
   │  (OSS)       │  Three-stream validation: acceptance + structure + unit
   └──────┬──────┘
          │
          ▼
   Working code + passing tests + audit trail
```

**The key insight:** AI generates plausible code. This pipeline generates *correct* code — because every output is validated against a contract the AI can't shortcut.

---

## Who Is This For

| Audience | What They Get |
|----------|---------------|
| **Solo developers** | Describe a project, get working code with tests. No prompt engineering. |
| **Teams using AI** | Architectural guardrails that prevent AI from drifting off-spec. |
| **Agencies/consultants** | Generate project scaffolds from client specs in minutes, not days. |
| **Enterprise** | Auditable AI development with contracts at every step. |

---

## The Workflow

### Step 1: Describe Your Project (ArchSpec)

Go to [archspec.dev](https://archspec.dev) (or self-host the open source version).

**What you do:**
- Describe your project in natural language
- AI generates structured specifications: data model, API endpoints, pages, features, UI design, test cases

**What you get:**
- Complete project specification with entities, fields, relationships
- API endpoint definitions with methods, auth, roles
- Page/component structure
- Gherkin-style acceptance test cases (Given/When/Then)
- Technology stack recommendations

**Example:**
```
Input: "A task management app with teams, projects, and kanban boards"

Output:
  Data Model: User, Team, Project, Task, Board, Column
  API: /teams (CRUD), /projects (CRUD), /tasks (CRUD + move), /boards (read + update)
  Pages: Dashboard, Project View, Kanban Board, Team Settings
  Tests: 15 Gherkin scenarios covering core workflows
```

**Pricing:** Free to explore. AI credits required for specification generation (pay-as-you-go or subscription).

### Step 2: Export as MAID Project

Click **"Export as MAID Project"** in ArchSpec.

**What happens:**
- ArchSpec converts your specifications into MAID v2 manifests
- Each manifest is a machine-checkable contract: "this file MUST contain these classes and functions with these types"
- Manifests are ordered by dependency (leaf entities first, then dependent ones)
- Acceptance test scaffolds are generated from your Gherkin test cases

**What you get (ZIP download):**
```
my-project/
├── manifests/
│   ├── feature-authentication.manifest.yaml
│   ├── feature-task-management.manifest.yaml
│   ├── feature-kanban-board.manifest.yaml
│   └── test-authentication.manifest.yaml
├── tests/
│   └── acceptance/
│       ├── test_authentication.py
│       ├── test_task_management.py
│       └── test_kanban_board.py
├── .maidrc.yaml
└── README.md
```

**A manifest looks like:**
```yaml
schema: "2"
goal: "Implement Task Management feature"
type: feature

files:
  create:
    - path: src/models/task.py
      artifacts:
        - kind: class
          name: Task
        - kind: attribute
          name: title
          of: Task
          type: str
        - kind: attribute
          name: status
          of: Task
          type: TaskStatus
  edit:
    - path: src/routes/tasks.py
      artifacts:
        - kind: function
          name: create_task
          args:
            - name: data
              type: TaskCreate
          returns: Task

validate:
  - pytest tests/models/test_task.py -v
  - pytest tests/routes/test_tasks.py -v
```

This is a **contract**: the code MUST define class `Task` with attribute `title: str`, and function `create_task(data: TaskCreate) -> Task`. MAID Runner will verify this at the AST level — no hand-waving.

### Step 3: AI Implements the Code

Use any AI coding tool (Claude Code, Cursor, Windsurf, or MAID Agents for full automation).

**Option A: Manual AI-assisted development**
```bash
# Install MAID Runner
pip install maid-runner

# Open your project in Claude Code / Cursor / Windsurf
# Tell the AI: "Implement the manifests in manifests/"
# The AI reads the manifest contracts and writes matching code
# Run validation after each change:
maid validate
maid test
```

**Option B: Fully automated (MAID Agents)**
```bash
# Install MAID Agents
pip install maid-agents

# Run the full pipeline automatically
ccmaid run "Implement all manifests"

# The agent:
# 1. Reads each manifest
# 2. Writes code to satisfy the contract
# 3. Runs maid validate to check
# 4. If validation fails, automatically retries (up to N attempts)
# 5. Moves to next manifest
```

**What the AI is constrained by:**
- It MUST create the exact classes, functions, and types declared in the manifest
- In strict mode (new files), it CANNOT add undeclared public APIs
- Its code MUST pass the acceptance tests from ArchSpec
- Its code MUST pass its own unit tests
- All three streams must agree: acceptance tests (WHAT) + structural validation (SKELETON) + unit tests (HOW)

### Step 4: MAID Runner Validates

After implementation, MAID Runner performs three-stream validation:

```bash
# Validate all manifests
maid validate

# Run all test commands
maid test

# Check architectural coherence
maid validate --coherence
```

**Stream 1 — Acceptance Tests (WHAT):**
From ArchSpec's Gherkin scenarios. Immutable during implementation. Tests that the system does what the spec says.

**Stream 2 — Structural Validation (SKELETON):**
MAID Runner's AST analysis. Checks that declared classes, functions, attributes, and types actually exist in the code with correct signatures.

**Stream 3 — Unit Tests (HOW):**
Written during implementation by the AI or developer. Tests that internal logic is correct.

**Why three streams?** A single test stream is gameable — the AI can write tests that pass by testing the wrong thing. Two+ independent streams constrain the AI from multiple angles. The acceptance tests can't be modified during implementation, so the AI can't "cheat."

### Step 5: Ship

Your code is:
- Structurally verified against the spec
- Passing acceptance tests from ArchSpec
- Passing unit tests from implementation
- Architecturally coherent (no duplicate artifacts, naming violations, boundary issues)
- Fully auditable (every manifest is a timestamped contract)

---

## Tooling Overview

### Open Source (Free)

| Tool | What It Does | Install |
|------|-------------|---------|
| **MAID Runner** | Validates code against manifests | `pip install maid-runner` |
| **MAID Runner MCP** | Exposes MAID validation to AI agents via MCP protocol | `pip install maid-runner-mcp` |
| **MAID LSP** | Real-time manifest validation in editors | `pip install maid-lsp` |
| **VS Code MAID** | VS Code extension for MAID integration | VS Code Marketplace |
| **ArchSpec** (self-hosted) | Full spec generation platform | github.com/mamertofabian/arch-spec |

### SaaS

| Service | What You Get | Pricing |
|---------|-------------|---------|
| **ArchSpec** (archspec.dev) | AI-powered spec generation, MAID export | Pay-per-AI-credit or subscription |

### Premium (Coming Soon)

| Service | What You Get |
|---------|-------------|
| **Full AI Development Pipeline** | ArchSpec specs → MAID manifests → automated implementation → validated code. End-to-end, with dedicated agent orchestration and priority support. |

---

## Quick Start

### Fastest Path (5 minutes)

```bash
# 1. Create specs on archspec.dev
#    → Export as MAID project (download ZIP)

# 2. Unzip and enter project
unzip my-project-specs.zip
cd my-project

# 3. Install MAID Runner
pip install maid-runner

# 4. See what needs to be built
maid validate
# Shows: which manifests pass/fail, what's missing

# 5. Use your AI tool to implement
# (Claude Code, Cursor, Windsurf — tell it to read manifests/)

# 6. Validate as you go
maid validate            # Check structure matches contracts
maid test                # Run all test commands
maid validate --coherence  # Check architecture
```

### Developer Path (Manual)

```bash
# Write manifests yourself (no ArchSpec needed)
cat > manifests/add-auth.manifest.yaml << 'EOF'
schema: "2"
goal: "Add authentication service"
type: feature
files:
  create:
    - path: src/auth/service.py
      artifacts:
        - kind: class
          name: AuthService
        - kind: method
          name: login
          of: AuthService
          args:
            - name: username
              type: str
            - name: password
              type: str
          returns: Token
validate:
  - pytest tests/test_auth.py -v
EOF

# Implement
# ... write src/auth/service.py ...

# Validate
maid validate manifests/add-auth.manifest.yaml
```

### Library Integration (For Tool Builders)

```python
from maid_runner import validate, validate_all, ManifestChain

# Validate a single manifest
result = validate("manifests/add-auth.manifest.yaml")
print(result.success)  # True/False
print(result.errors)   # List of specific failures

# Validate all manifests
batch = validate_all("manifests/")
print(f"{batch.passed}/{batch.total_manifests} passed")

# Query the manifest chain
chain = ManifestChain("manifests/")
artifacts = chain.merged_artifacts_for("src/auth/service.py")

# Generate manifest from existing code
from maid_runner import generate_snapshot
manifest = generate_snapshot("src/auth/service.py")
```

---

## How It Compares

| | Raw AI Coding | AI + Code Review | AI Compiler (This) |
|---|---|---|---|
| Speed | Fast | Medium | Medium |
| Correctness | Unpredictable | Depends on reviewer | **Verified by contract** |
| Architecture | Drifts over time | Reviewer catches some | **Enforced by manifest** |
| Audit trail | Git history only | PR comments | **Timestamped contracts** |
| Scales with team | Poorly | OK | **Well** |
| AI can "cheat" | Yes | Reviewer might miss | **No — three streams** |

---

## FAQ

**Do I have to write manifests manually?**
No. ArchSpec generates them from your specs. For existing projects, `maid snapshot` generates manifests from your current code.

**Does this work with my language?**
Python is always supported. TypeScript/JavaScript and Svelte require optional dependencies (`pip install maid-runner[typescript]`). More languages coming.

**Can I use this without ArchSpec?**
Yes. MAID Runner is standalone. Write manifests by hand, or use `maid snapshot` to generate from existing code. ArchSpec just automates the spec → manifest step.

**Is this like Terraform for code?**
Similar concept. Terraform declares infrastructure state; MAID declares code structure state. Both validate that reality matches declaration.

**What AI tools work with this?**
Any. Claude Code, Cursor, Windsurf, Aider, or custom agents. The manifests are just YAML files — any AI that can read YAML and write code can use them. MAID Agents provides the tightest integration with automatic retry.

**What if the AI can't satisfy a manifest?**
MAID Runner reports exactly what's missing: "Artifact 'AuthService.login' not defined in src/auth/service.py." The AI (or you) can read the error and fix it. With MAID Agents, this retry loop is automatic.

**How is this different from just having good tests?**
Tests verify behavior (does it work?). Manifests verify structure (does it match the blueprint?). You need both. An AI can write code that passes tests but has a completely wrong architecture. Manifests prevent that.
