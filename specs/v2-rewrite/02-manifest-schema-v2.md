# MAID Runner v2 - Manifest Schema v2

**References:** [00-overview.md](00-overview.md), [03-data-types.md](03-data-types.md), [13-backward-compatibility.md](13-backward-compatibility.md)

## Design Goals

1. **Multi-file support** - One manifest can declare artifacts across multiple files
2. **YAML-native** - Comments, readability, less visual noise than JSON
3. **No legacy fields** - One way to express each concept
4. **Machine-validatable** - JSON Schema for structural validation
5. **Human-scannable** - Readable at a glance when needed

## Complete Schema

### Top-Level Fields

```yaml
# Required fields
schema: "2"                    # Schema version (string, always "2")
goal: string                   # What this manifest achieves (1-2 sentences)

# Required - at least one of files.create, files.edit must be present
# (unless type is "snapshot" which uses files.snapshot)
files:
  create: [FileSpec]           # New files (strict validation)
  edit: [FileSpec]             # Existing files (permissive validation)
  read: [string]              # Read-only dependencies (paths only)
  delete: [DeleteSpec]         # Files to be removed
  snapshot: [FileSpec]         # Snapshot-mode files (exact-match, used by snapshot type only)

# Required - at least one validation command
validate: [string] | [[string]]  # Single command or list of commands

# Optional fields
type: string                   # "feature" | "fix" | "refactor" | "snapshot" | "system-snapshot"
description: string            # Detailed context beyond the goal
supersedes: [string]           # List of manifest slugs this replaces
created: string                # ISO 8601 timestamp (auto-set on creation)
metadata:
  author: string
  tags: [string]
  priority: string             # "low" | "medium" | "high" | "critical"
```

### FileSpec Object

```yaml
# FileSpec - declares artifacts expected in a single file
path: string                   # Relative file path from project root (REQUIRED)
status: string                 # "present" (default) | "absent" (for deletion tracking)
artifacts:                     # List of expected artifacts (REQUIRED, at least one)
  - <ArtifactSpec>
```

### DeleteSpec Object

```yaml
# DeleteSpec - declares a file that should be removed
path: string                   # File to delete (REQUIRED)
reason: string                 # Why this file is being deleted (optional)
```

### ArtifactSpec Object

Artifacts come in several forms. The `kind` field determines which additional fields are relevant.

```yaml
# Common fields (all artifact kinds)
kind: string                   # REQUIRED: "class" | "function" | "method" | "attribute" |
                               #           "interface" | "type" | "enum" | "namespace"
name: string                   # REQUIRED: artifact name
description: string            # Optional: what this artifact does

# Function/Method-specific fields
args: [ArgSpec]                # Function arguments
returns: string                # Return type annotation
raises: [string]               # Exception types that may be raised
async: bool                    # Whether the function is async (default: false)

# Class-specific fields
bases: [string]                # Base classes

# Method-specific fields (kind: "method")
# The parent class is determined by the `of` field:
of: string                     # Parent class name (REQUIRED for methods and class attributes)

# Attribute-specific fields
type: string                   # Type annotation for attributes
```

### ArgSpec Object

```yaml
name: string                   # REQUIRED: argument name
type: string                   # Type annotation (optional)
default: string                # Default value (optional)
```

## Artifact Kind Reference

| Kind | Description | Required Fields | Optional Fields |
|------|-------------|-----------------|-----------------|
| `class` | Class definition | name | bases, description |
| `function` | Module-level function | name | args, returns, raises, async, description |
| `method` | Class method | name, of | args, returns, raises, async, description |
| `attribute` | Module or class attribute | name | type, of, description |
| `interface` | TypeScript interface | name | bases, description |
| `type` | Type alias | name | description |
| `enum` | Enum definition | name | description |
| `namespace` | TypeScript namespace | name | description |

### Mapping from v1 Schema

| v1 Field | v2 Equivalent | Notes |
|----------|---------------|-------|
| `type: "function"` + `class: "Foo"` | `kind: "method"` + `of: "Foo"` | Methods are explicit |
| `type: "attribute"` + `class: "Foo"` | `kind: "attribute"` + `of: "Foo"` | Class attrs use `of` |
| `type: "function"` (no class) | `kind: "function"` | Module-level function |
| `parameters: [{name: "x"}]` | `args: [{name: "x"}]` | Unified as `args` |
| `args: [{name: "x", type: "str"}]` | `args: [{name: "x", type: "str"}]` | Same |
| `returns: "int"` | `returns: "int"` | Same |
| `returns: {type: "int"}` | `returns: "int"` | Simplified to string always |

## Complete Examples

### Example 1: Feature (Multi-File)

```yaml
schema: "2"
goal: "Add JWT authentication service with token model"
type: feature

files:
  create:
    - path: src/auth/service.py
      artifacts:
        - kind: class
          name: AuthService
          description: "Handles JWT authentication"

        - kind: method
          name: login
          of: AuthService
          args:
            - name: username
              type: str
            - name: password
              type: str
          returns: Token

        - kind: method
          name: verify
          of: AuthService
          args:
            - name: token
              type: str
          returns: bool

    - path: src/auth/models.py
      artifacts:
        - kind: class
          name: Token

        - kind: attribute
          name: value
          of: Token
          type: str

        - kind: attribute
          name: expires_at
          of: Token
          type: datetime

  edit:
    - path: src/config.py
      artifacts:
        - kind: attribute
          name: AUTH_SECRET
          type: str

  read:
    - src/database.py
    - tests/test_auth.py

validate:
  - pytest tests/test_auth.py -v

created: "2025-06-15T10:30:00Z"
metadata:
  author: claude
  tags: [auth, security]
  priority: high
```

### Example 2: Bug Fix (Single File)

```yaml
schema: "2"
goal: "Fix cls parameter being included in method signature validation"
type: fix

files:
  edit:
    - path: maid_runner/validators/python.py
      artifacts:
        - kind: method
          name: _filter_parameters
          of: PythonValidator
          args:
            - name: params
              type: "list[ast.arg]"
            - name: is_method
              type: bool
          returns: "list[ast.arg]"

  read:
    - tests/test_python_validator.py

validate:
  - pytest tests/validators/test_python.py -v
```

### Example 3: Refactor (Rename)

```yaml
schema: "2"
goal: "Rename utils.py to helpers.py"
type: refactor
supersedes: [snapshot-utils]

files:
  create:
    - path: src/helpers.py
      artifacts:
        - kind: function
          name: parse_manifest_path
          args:
            - name: raw_path
              type: str
          returns: Path

  delete:
    - path: src/utils.py
      reason: "Renamed to helpers.py for clarity"

  read:
    - tests/test_helpers.py

validate:
  - pytest tests/test_helpers.py -v
```

### Example 4: File Deletion

```yaml
schema: "2"
goal: "Remove deprecated legacy adapter"
type: refactor
supersedes: [create-legacy-adapter]

files:
  delete:
    - path: src/legacy_adapter.py
      reason: "All consumers migrated to new API"

validate:
  - pytest tests/ -v --ignore=tests/test_legacy_adapter.py
```

### Example 5: Snapshot

```yaml
schema: "2"
goal: "Snapshot current state of validation engine"
type: snapshot
created: "2025-06-15T10:30:00Z"

files:
  snapshot:
    - path: maid_runner/core/validate.py
      artifacts:
        - kind: class
          name: ValidationEngine
        - kind: method
          name: validate
          of: ValidationEngine
          args:
            - name: manifest
              type: Manifest
            - name: chain
              type: ManifestChain
              default: "None"
          returns: ValidationResult
        # ... all public artifacts at this point in time

validate:
  - pytest tests/core/test_validate.py -v
```

### Example 6: TypeScript Artifacts

```yaml
schema: "2"
goal: "Add React authentication components"
type: feature

files:
  create:
    - path: src/components/AuthProvider.tsx
      artifacts:
        - kind: interface
          name: AuthContextType
          description: "Type for authentication context"

        - kind: function
          name: AuthProvider
          args:
            - name: children
              type: ReactNode
          returns: JSX.Element

        - kind: function
          name: useAuth
          returns: AuthContextType

    - path: src/types/auth.ts
      artifacts:
        - kind: interface
          name: User

        - kind: type
          name: AuthState

        - kind: enum
          name: AuthStatus

  read:
    - src/api/client.ts
    - tests/components/AuthProvider.test.tsx

validate:
  - vitest run tests/components/AuthProvider.test.tsx
```

## Validation Mode Semantics

### Strict Mode (files.create and files.snapshot)

Files listed under `files.create` or `files.snapshot` use **strict validation**:
- Implementation MUST contain EXACTLY the declared artifacts (public API)
- Additional public artifacts NOT in the manifest are **errors**
- Private artifacts (prefixed with `_`) are allowed and ignored
- Used for: new files where the manifest is the complete specification

### Permissive Mode (files.edit)

Files listed under `files.edit` use **permissive validation**:
- Implementation MUST contain AT LEAST the declared artifacts
- Additional public artifacts are allowed (they existed before)
- Used for: modifying existing files where only new/changed artifacts are declared

### Absent Status

Files with `status: absent` (or files under `files.delete`) use **absence validation**:
- The file MUST NOT exist at the declared path
- Used for: file deletion tracking

## Manifest Naming Convention

Manifests use **semantic slug names** instead of sequential task numbers:

```
manifests/
  add-jwt-auth.manifest.yaml
  fix-cls-parameter.manifest.yaml
  refactor-rename-utils.manifest.yaml
  snapshot-validate-engine.manifest.yaml
```

**Rules:**
- Lowercase, hyphen-separated words
- Descriptive of the change (not a number)
- Extension: `.manifest.yaml` (or `.manifest.json` for v1 compat)
- No sequential numbering requirement
- Chronological ordering determined by `created` timestamp inside the manifest

## JSON Schema for V2

The JSON Schema for v2 manifests lives at `maid_runner/schemas/manifest.v2.schema.json`. It is used for structural validation when loading manifests. The schema MUST enforce:

1. `schema: "2"` is required
2. `goal` is required (non-empty string)
3. At least one of `files.create`, `files.edit`, `files.snapshot`, or `files.delete` MUST be present
4. `validate` is required (array of strings, or array of arrays of strings)
5. Each FileSpec MUST have `path` and non-empty `artifacts`
6. Each ArtifactSpec MUST have `kind` and `name`
7. `kind` MUST be one of the allowed values
8. `of` is REQUIRED when `kind` is `"method"` and the artifact belongs to a class
9. `type` field MUST be one of the allowed values if present
10. `supersedes` items MUST be strings (manifest slugs, not full paths)

## Schema Evolution

The `schema` field enables future evolution:
- `"2"` = this spec
- `"3"` (future) = hypothetical next version
- Loaders check `schema` field and dispatch to appropriate parser
- V1 manifests have no `schema` field (or `version: "1"`)

## Multi-File vs Single-File: When to Use Each

| Scenario | Approach |
|----------|----------|
| Adding a new feature (service + model + config) | Single multi-file manifest |
| Bug fix in one file | Single-file manifest |
| Refactoring across files | Single multi-file manifest |
| Snapshot of one file | Single-file manifest |
| System snapshot | One manifest with many files under `files.snapshot` |

**Rule of thumb:** If the changes are part of one coherent goal, they go in one manifest regardless of how many files are touched.
