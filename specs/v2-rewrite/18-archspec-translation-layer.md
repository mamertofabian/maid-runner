# arch-spec → MAID Manifest Translation Layer

**References:** [00-overview.md](00-overview.md), [02-manifest-schema-v2.md](02-manifest-schema-v2.md), [project_ai_compiler_reframe.md](../../.claude/projects/-home-atomrem-projects-codefrost-dev-maid-runner/memory/project_ai_compiler_reframe.md)

## Purpose

This document specifies how arch-spec's structured specifications translate into MAID v2 manifests. This is the "IR generation" step in the AI compiler pipeline — converting high-level specs into machine-verifiable contracts.

## Scope

**Phase 1 (this spec): Greenfield export.** Generate manifests for a new project from scratch. Handles the 80% case where arch-spec describes a new application and the exporter scaffolds the complete manifest set.

**Phase 2 (future): Incremental translation.** Import into existing projects — diff against current manifest chain, emit only deltas (new entities, modified endpoints). This requires reading the existing codebase/manifests and is substantially more complex.

## Where This Lives

The translation layer should live in **arch-spec's codebase** (not maid-runner) because:
- arch-spec has the Pydantic models and data
- It's an export feature, like the existing markdown/ZIP export
- maid-runner stays tool-agnostic (doesn't know about arch-spec)

**Location:** `arch-spec/backend/app/services/maid_exporter.py` (~600-800 lines)

The alternative `maid import arch-spec` CLI command would live in maid-runner and read arch-spec's exported JSON/markdown. Both approaches can coexist.

## Rigor Levels

The exporter supports different rigor levels, matching the compiler optimization model:

| Level | What's Generated | When to Use |
|-------|-----------------|-------------|
| **O0** (minimal) | One manifest per feature, function names only, no types | Prototypes, experiments |
| **O1** (standard) | Per-entity/endpoint manifests with typed artifacts | Normal features |
| **O2** (full) | All of O1 + acceptance test scaffolds + coherence config | Production features |
| **O3** (strict) | All of O2 + three-stream validation fields + constraint config | Critical systems |

Default: O1 for most projects, O2 when test cases are present in arch-spec.

## Translation Rules

### 1. DataModel Entities → Class + Attribute Manifests

Each entity becomes a manifest declaring a class with typed attributes.

**arch-spec input:**
```python
Entity(
    name="User",
    description="Application user",
    fields=[
        EntityField(name="id", type="string", primaryKey=True, generated=True),
        EntityField(name="email", type="string", unique=True, required=True),
        EntityField(name="displayName", type="string", required=True),
        EntityField(name="passwordHash", type="string", required=True),
        EntityField(name="createdAt", type="number", default="Date.now()"),
    ]
)
```

**MAID manifest output:**
```yaml
schema: "2"
goal: "Implement User entity"
type: feature

files:
  create:
    - path: src/models/user.py    # or .ts, based on tech stack
      artifacts:
        - kind: class
          name: User
          description: "Application user"

        - kind: attribute
          name: id
          of: User
          type: str

        - kind: attribute
          name: email
          of: User
          type: str

        - kind: attribute
          name: display_name
          of: User
          type: str

        - kind: attribute
          name: password_hash
          of: User
          type: str

        - kind: attribute
          name: created_at
          of: User
          type: float

validate:
  - pytest tests/models/test_user.py -v
```

**Type mapping** (arch-spec types → language types):

| arch-spec type | Python | TypeScript |
|---------------|--------|-----------|
| `string` | `str` | `string` |
| `number` | `float` | `number` |
| `integer` | `int` | `number` |
| `boolean` | `bool` | `boolean` |
| `date` | `datetime` | `Date` |
| `array` | `list` | `Array` |
| `object` | `dict` | `Record<string, unknown>` |

**Name mapping** (camelCase → snake_case for Python):

```python
def to_snake_case(name: str) -> str:
    """Convert camelCase to snake_case for Python."""
    # displayName -> display_name
    # createdAt -> created_at
```

For TypeScript projects, names stay camelCase.

### 2. Relationships → Relationship Attributes

**arch-spec input:**
```python
Relationship(type="one-to-many", from_entity="User", to_entity="Order", field="userId")
```

**MAID manifest output (added to User entity manifest):**
```yaml
- kind: attribute
  name: orders
  of: User
  type: "list[Order]"       # Python
  # type: "Order[]"         # TypeScript
```

**And to Order entity manifest:**
```yaml
- kind: attribute
  name: user_id
  of: Order
  type: str                  # FK reference
```

| Relationship type | From entity gets | To entity gets |
|-------------------|-----------------|----------------|
| `one-to-many` | `list[To]` attribute | FK attribute |
| `many-to-one` | FK attribute | `list[From]` attribute |
| `one-to-one` | `Optional[To]` attribute | FK attribute |
| `many-to-many` | `list[To]` attribute | `list[From]` attribute |

### 3. API Endpoints → Route Handler Manifests

Each endpoint becomes a manifest declaring handler functions.

**arch-spec input:**
```python
ApiEndpoint(
    path="/users",
    description="Manage users",
    methods=["GET", "POST"],
    auth=True,
    roles=["admin", "manager"],
)
```

**MAID manifest output:**
```yaml
schema: "2"
goal: "Implement /users API endpoints"
type: feature

files:
  create:
    - path: src/routes/users.py    # or .ts
      artifacts:
        - kind: function
          name: get_users           # list_users / getUsers
          returns: "list[User]"
          description: "GET /users - Manage users"

        - kind: function
          name: create_user         # createUser
          args:
            - name: data
              type: UserCreate
          returns: User
          description: "POST /users - Manage users"

  read:
    - src/models/user.py

validate:
  - pytest tests/routes/test_users.py -v
```

**Method → function name mapping:**

| HTTP Method | Python name | TypeScript name |
|-------------|------------|-----------------|
| `GET /users` | `get_users` / `list_users` | `getUsers` / `listUsers` |
| `GET /users/{id}` | `get_user` | `getUser` |
| `POST /users` | `create_user` | `createUser` |
| `PUT /users/{id}` | `update_user` | `updateUser` |
| `DELETE /users/{id}` | `delete_user` | `deleteUser` |
| `PATCH /users/{id}` | `patch_user` | `patchUser` |

### 4. Pages → Component Manifests

Each page becomes a manifest declaring a component function.

**arch-spec input:**
```python
PageComponent(
    name="Dashboard",
    path="/dashboard",
    components=["StatsGrid", "RecentActivity", "QuickActions"],
    enabled=True,
)
```

**MAID manifest output (TypeScript/React):**
```yaml
schema: "2"
goal: "Implement Dashboard page"
type: feature

files:
  create:
    - path: src/pages/Dashboard.tsx
      artifacts:
        - kind: function
          name: Dashboard
          returns: JSX.Element
          description: "Dashboard page component"

  read:
    - src/components/StatsGrid.tsx
    - src/components/RecentActivity.tsx
    - src/components/QuickActions.tsx

validate:
  - vitest run tests/pages/Dashboard.test.tsx
```

### 5. Features → Manifest Groups

Each feature module becomes a **group** of manifests covering its entities, endpoints, and pages.

**arch-spec input:**
```python
FeatureModule(name="Authentication", description="User authentication with OAuth", enabled=True)
```

**MAID output:** One multi-file manifest per feature:
```yaml
schema: "2"
goal: "Implement Authentication feature"
type: feature
metadata:
  tags: [auth, security]

files:
  create:
    - path: src/auth/service.py
      artifacts: [...]        # From DataModel entities related to auth
    - path: src/routes/auth.py
      artifacts: [...]        # From API endpoints related to auth
    - path: src/pages/Login.tsx
      artifacts: [...]        # From Pages related to auth

  read:
    - src/models/user.py

validate:
  - pytest tests/auth/ -v
  - vitest run tests/pages/Login.test.tsx
```

The grouping heuristic:
- Match entity names to feature keywords (User, Session → Authentication)
- Match endpoint paths to feature keywords (/auth/, /login/ → Authentication)
- Match page names to feature keywords (Login, Register → Authentication)

### 6. Test Cases (Gherkin) → Acceptance Test Scaffolds

**arch-spec input:**
```python
GherkinTestCase(
    feature="User Authentication",
    title="User registration with valid email",
    scenarios=[{
        "given": "a new user with valid email",
        "when": "they submit the registration form",
        "then": "account is created and confirmation email sent"
    }]
)
```

**MAID manifest output:**
```yaml
# Added to the feature's manifest:
validate:
  - pytest tests/acceptance/test_auth.py -v

# Generated test scaffold (separate file):
# tests/acceptance/test_auth.py
```

**Generated test scaffold:**
```python
"""Acceptance tests for User Authentication.

Auto-generated from arch-spec test cases.
These tests define WHAT the system should do.
Implementation tests (unit/integration) define HOW.
"""
import pytest


class TestUserRegistrationWithValidEmail:
    """User registration with valid email"""

    def test_scenario(self):
        """
        Given a new user with valid email
        When they submit the registration form
        Then account is created and confirmation email sent
        """
        # TODO: Implement acceptance test
        raise NotImplementedError("Acceptance test not yet implemented")
```

### 7. TechStack → Path and Language Configuration

The tech stack determines:
- File extensions (`.py` vs `.ts`/`.tsx`)
- Import paths and conventions
- Test runner commands (`pytest` vs `vitest`)
- Name conventions (snake_case vs camelCase)
- Framework-specific patterns (Django models vs SQLAlchemy vs Prisma)

**Tech stack → config mapping:**

```python
@dataclass
class TranslationConfig:
    """Configuration derived from arch-spec tech stack."""
    language: str                    # "python" | "typescript"
    file_extension: str              # ".py" | ".ts" | ".tsx"
    name_convention: str             # "snake_case" | "camelCase"
    test_runner: str                 # "pytest" | "vitest"
    test_extension: str              # ".py" | ".test.ts" | ".test.tsx"

    # Path patterns
    models_dir: str                  # "src/models" | "src/entities"
    routes_dir: str                  # "src/routes" | "src/api"
    pages_dir: str                   # "src/pages"
    tests_dir: str                   # "tests" | "tests"
    components_dir: str              # "src/components"

    # Framework-specific
    model_base_class: str | None     # "BaseModel" (Pydantic) | None (dataclass) | "Model" (Django)
    route_decorator: str | None      # "@app.get" (FastAPI) | "@router.get" (Express) | None


def config_from_tech_stack(tech_stack: ProjectTechStack) -> TranslationConfig:
    """Derive translation config from arch-spec tech stack."""

    if tech_stack.backend and hasattr(tech_stack.backend, 'language'):
        lang = tech_stack.backend.language.lower()
    elif tech_stack.frontend:
        lang = tech_stack.frontend.language.lower()
    else:
        lang = "python"  # default

    is_python = lang in ("python", "python3")
    is_typescript = lang in ("typescript", "javascript")

    return TranslationConfig(
        language="python" if is_python else "typescript",
        file_extension=".py" if is_python else ".ts",
        name_convention="snake_case" if is_python else "camelCase",
        test_runner="pytest" if is_python else "vitest",
        test_extension=".py" if is_python else ".test.ts",
        models_dir="src/models",
        routes_dir="src/routes" if is_python else "src/api",
        pages_dir="src/pages",
        tests_dir="tests",
        components_dir="src/components",
        model_base_class=_infer_model_base(tech_stack),
        route_decorator=_infer_route_decorator(tech_stack),
    )
```

## Dependency Ordering

Manifests MUST be emitted in dependency order. An AI agent executing manifests sequentially cannot implement `Order` before `User` exists if Order has a `userId` FK.

### Phase 0: Build Dependency Graph

Before generating any manifests, build a dependency DAG:

```python
def build_dependency_graph(
    data_model: DataModel,
    api: Api,
    pages: Pages,
) -> dict[str, set[str]]:
    """Build dependency graph from arch-spec sections.

    Returns:
        Dict of node_id -> set of dependency node_ids.

    Node naming:
        "entity:User", "entity:Order"
        "api:/users", "api:/orders"
        "page:Dashboard", "page:Login"
    """
```

**Entity dependencies** (from relationships):
```
Relationship(type="one-to-many", from_entity="User", to_entity="Order")
→ "entity:Order" depends on "entity:User"
```

**Endpoint dependencies** (from entity references):
```
GET /orders returns list[Order] which has userId FK to User
→ "api:/orders" depends on "entity:Order" AND "entity:User"
```

**Page dependencies** (from components list):
```
Page "Dashboard" uses components ["StatsGrid", "RecentActivity"]
→ "page:Dashboard" depends on its component files
```

### Topological Sort

```python
from graphlib import TopologicalSorter

def sort_manifests(dep_graph: dict[str, set[str]]) -> list[str]:
    """Topologically sort nodes so dependencies come first.

    Raises CycleError if circular dependencies exist.
    """
    ts = TopologicalSorter(dep_graph)
    return list(ts.static_order())
```

**Example output order for an e-commerce app:**
```
1. entity:User              (no deps — leaf entity)
2. entity:Product           (no deps — leaf entity)
3. entity:Order             (depends on User)
4. entity:OrderItem         (depends on Order, Product)
5. api:/users               (depends on User)
6. api:/products            (depends on Product)
7. api:/orders              (depends on Order, User)
8. page:Login               (depends on auth API)
9. page:ProductList         (depends on Product API)
10. page:Dashboard          (depends on multiple APIs)
```

Each manifest gets a `created` timestamp reflecting this order, so the manifest chain processes them sequentially.

### Circular Dependency Handling

If the dependency graph has cycles (e.g., User references Organization, Organization references User):
1. Break the cycle by choosing the entity with fewer incoming edges
2. Emit that entity first with a forward-reference comment
3. Log a warning about the circular dependency

## Translation Pipeline

```
arch-spec project JSON/API
    │
    ├─ Load all spec sections (DataModel, Api, Pages, Features, TestCases, TechStack)
    │
    ├─ Derive TranslationConfig from TechStack
    │
    ├─ Phase 0: Dependency ordering
    │   Build dependency graph from relationships + endpoint refs
    │   Topologically sort all nodes
    │   Assign creation order timestamps
    │
    ├─ Phase 1: Entity manifests (in dependency order)
    │   For each Entity in DataModel (sorted):
    │       Generate class + attribute artifacts
    │       Add relationship attributes
    │       Add read dependencies on upstream entities
    │       Generate validation command
    │       → entity-{name}.manifest.yaml
    │
    ├─ Phase 2: API manifests (in dependency order)
    │   For each ApiEndpoint (sorted):
    │       Generate handler function artifacts
    │       Link to entity read dependencies
    │       → api-{path-slug}.manifest.yaml
    │
    ├─ Phase 3: Page manifests (in dependency order)
    │   For each PageComponent (sorted):
    │       Generate component function artifact
    │       Link component dependencies as read files
    │       → page-{name}.manifest.yaml
    │
    ├─ Phase 4: Feature grouping (optional, rigor >= O1)
    │   Group entities + endpoints + pages by feature
    │   Merge into multi-file feature manifests
    │   Preserve dependency order within groups
    │   → feature-{name}.manifest.yaml
    │
    ├─ Phase 5: Acceptance test scaffolds (rigor >= O2)
    │   For each GherkinTestCase:
    │       Generate test class with TODO stubs
    │       → tests/acceptance/test_{feature}.py
    │
    └─ Output: manifests/ directory + test scaffolds (ordered)
```

## Output Structure

```
project/
├── manifests/
│   ├── entity-user.manifest.yaml
│   ├── entity-order.manifest.yaml
│   ├── api-users.manifest.yaml
│   ├── api-orders.manifest.yaml
│   ├── page-dashboard.manifest.yaml
│   ├── page-login.manifest.yaml
│   └── feature-auth.manifest.yaml      # (optional grouped)
├── tests/
│   └── acceptance/
│       ├── test_auth.py
│       └── test_shopping.py
└── .maidrc.yaml                         # Generated config
```

## API (in arch-spec)

```python
# arch-spec/backend/app/services/maid_exporter.py

def export_maid_manifests(
    project_specs: dict[str, ProjectSpec],
    *,
    output_dir: Path = Path("manifests"),
    group_by_feature: bool = True,
    generate_tests: bool = True,
    rigor: int = 1,
) -> list[Path]:
    """Export all project specs as MAID v2 manifests.

    Args:
        project_specs: Dict of spec_type -> ProjectSpec (DataModelSpec, ApiSpec, etc.)
        output_dir: Where to write manifest YAML files.
        group_by_feature: If True, group related manifests by feature module.
        rigor: Rigor level 0-3 (O0=minimal, O1=standard, O2=full, O3=strict).
        generate_tests: If True, also generate acceptance test scaffolds.

    Returns:
        List of generated file paths.
    """
```

## Alternative: maid import arch-spec

For projects where arch-spec exports a ZIP with markdown specs:

```bash
# Import from arch-spec export ZIP
maid import arch-spec project-specs.zip --output-dir manifests/

# Import from arch-spec API (if running locally)
maid import arch-spec --url http://localhost:8000 --project-id abc123
```

This would live in `maid_runner/cli/commands/import_cmd.py` and parse the structured markdown or JSON export.

## Estimation

| Component | Lines | Where |
|-----------|-------|-------|
| Dependency graph builder | ~80 | arch-spec maid_exporter.py |
| Topological sort + cycle handling | ~40 | arch-spec maid_exporter.py |
| Entity translator | ~100 | arch-spec maid_exporter.py |
| Relationship translator | ~60 | arch-spec maid_exporter.py |
| API translator | ~80 | arch-spec maid_exporter.py |
| Page translator | ~50 | arch-spec maid_exporter.py |
| Feature grouper | ~80 | arch-spec maid_exporter.py |
| Test scaffold generator | ~60 | arch-spec maid_exporter.py |
| Config from tech stack | ~80 | arch-spec maid_exporter.py |
| Rigor level filtering | ~30 | arch-spec maid_exporter.py |
| YAML writer | ~40 | Uses maid_runner.save_manifest() |
| **Total** | **~700** | |

## Future: Phase 2 — Incremental Translation

Not in scope for Phase 1 (greenfield), but the compiler vision requires:

1. **Diffing mode:** Read existing manifest chain, compare against arch-spec output, emit only deltas (new entities, modified endpoints). New manifests use `files.edit` instead of `files.create` and include `supersedes` for replaced contracts.

2. **Codebase awareness:** Before emitting `files.create`, check if the file already exists. If so, emit `files.edit` instead and only declare new/changed artifacts.

3. **Manifest chain integration:** Use `maid_runner.ManifestChain` (library API) to read existing state and compute the minimal manifest set needed.

This is substantially more complex (~400 additional lines) and should be built after Phase 1 proves the greenfield pipeline works end-to-end.
