# IMPLEMENT.md Template

This is the template for the auto-generated `IMPLEMENT.md` file included in every
MAID project export. Variables in `{{CAPS}}` are replaced at export time.

---

# Implementing {{PROJECT_NAME}}

This project was generated from [ArchSpec](https://archspec.dev) specifications
with MAID (Manifest-driven AI Development) contracts.

## What's In This Project

```
specs/          → Human-readable specifications (reference)
manifests/      → Machine-checkable contracts ({{MANIFEST_COUNT}} manifests)
.maidrc.yaml    → MAID Runner configuration
```

{{#IF HAS_TESTS}}
```
tests/acceptance/  → Acceptance test scaffolds from spec test cases
```
{{/IF}}

**Manifests breakdown:** {{FEATURE_COUNT}} features, {{API_COUNT}} API endpoint groups, {{PAGE_COUNT}} pages

## Setup

```bash
# 1. Initialize project
{{INIT_CMD}}

# 2. Install dependencies
{{INSTALL_DEPS_CMD}}

# 3. Install dev dependencies (includes MAID Runner)
{{INSTALL_DEV_DEPS_CMD}}

# 4. Verify MAID Runner can read the manifests
{{VALIDATE_CMD}}
```

This will show all manifests failing — that's expected. The code doesn't exist yet.

## How to Implement

Read the manifests in `manifests/` and implement code that satisfies each contract.

### Implementation Order

Implement in this order (matching dependency chain):

1. **Models/entities first** — from `feature-*.manifest.yaml` files, `files.create` sections.
   These define data classes with typed attributes.

2. **API routes second** — from `feature-*.manifest.yaml` files, `files.edit` sections,
   and standalone `api-*.manifest.yaml` files. These define handler functions.

3. **Pages last** — from `page-*.manifest.yaml` files. These define page components.

### For Each Manifest

1. Read the manifest YAML to understand what's required
2. Check the `files` section:
   - `files.create` = **strict mode**. Code must have EXACTLY these artifacts.
   - `files.edit` = **permissive mode**. Code must have AT LEAST these artifacts
     (you can add helper classes, utilities, DTOs, etc.)
3. Implement the source files with declared classes, functions, and attributes
4. Validate: `{{VALIDATE_SINGLE_CMD}} manifests/<name>.manifest.yaml`
5. Fix any errors, re-validate until passing
6. Move to next manifest

### Reading a Manifest

```yaml
schema: "2"
goal: "Implement Budget Management feature"      # What this manifest covers
type: feature
files:
  create:                                          # Strict: EXACTLY these artifacts
    - path: src/models/budget.py
      artifacts:
        - kind: class                              # Must define this class
          name: Budget
        - kind: attribute                          # Must have this attribute
          name: title
          of: Budget                               # On class Budget
          type: str                                # With this type annotation
  edit:                                            # Permissive: AT LEAST these
    - path: src/routes/budgets.py
      artifacts:
        - kind: function                           # Must define this function
          name: create_budget
          args:
            - name: data
              type: BudgetCreate                   # With this parameter type
          returns: Budget                           # And this return type
validate:
  - {{TEST_RUNNER}} tests/models/test_budget.py -v
```

### Architecture

{{#IF IS_PYTHON}}
This is a **{{FRAMEWORK}}** backend. Use this structure:
```
src/
├── models/          # Data model classes (from feature manifests, files.create)
├── schemas/         # Pydantic request/response DTOs (BudgetCreate, UserUpdate, etc.)
├── routes/          # Route handlers (from feature/api manifests, files.edit)
├── pages/           # Page handlers (from page manifests, files.edit)
└── middleware/       # Auth and other middleware
```
{{/IF}}

{{#IF IS_TYPESCRIPT}}
This is a **{{FRAMEWORK}}** application. Use this structure:
```
src/
├── models/          # Data model types/interfaces (from feature manifests)
├── types/           # Shared TypeScript types
├── routes/          # API route handlers (from feature/api manifests)
│   └── middleware/  # Auth and other middleware
├── pages/           # Page components (from page manifests)
└── components/      # Shared UI components
```
{{/IF}}

## Validation

```bash
# Validate a single manifest
{{VALIDATE_SINGLE_CMD}} manifests/<name>.manifest.yaml

# Validate ALL manifests
{{VALIDATE_CMD}}

# Run test commands from manifests
{{TEST_CMD}}

# Check architectural coherence
{{VALIDATE_CMD}} --coherence
```

### Error Codes

| Code | Meaning | What to Do |
|------|---------|------------|
| **E300** | Artifact not defined | Add the missing class/function/attribute |
| **E301** | Unexpected public artifact | Remove it or make it private (`_name`) — only in strict mode |
| **E302** | Type mismatch | Fix the type annotation to match the manifest |
| **E304** | Missing type annotation | Add the type annotation the manifest declares |
| **E306** | File not found | Create the source file at the declared path |

## Reference Specifications

The `specs/` directory contains human-readable specifications from ArchSpec:

{{#IF HAS_SPECS}}
| File | Content |
|------|---------|
{{#EACH SPEC_FILES}}
| `specs/{{SPEC_FILE}}` | {{SPEC_DESCRIPTION}} |
{{/EACH}}
{{/IF}}

These are for **reference only** — the manifests in `manifests/` are the
machine-checkable contracts your code must satisfy.

## Completion Criteria

- [ ] `{{VALIDATE_CMD}}` — ALL manifests pass
- [ ] `{{VALIDATE_CMD}} --coherence` — no errors
- [ ] Code follows {{FRAMEWORK}} conventions
- [ ] Commit after each feature group passes validation

## Key Rules

- Every class, function, and attribute in a manifest MUST exist in the code
- Type annotations MUST match (e.g., `returns: list[Budget]` → `-> list[Budget]`)
- In strict mode (`files.create`): no undeclared public APIs allowed
- In permissive mode (`files.edit`): extra public classes/functions are fine
- Do NOT modify manifest files
- `self`/`cls` parameters are implicit — do not declare in manifests
- Private functions/classes (prefixed with `_`) are always allowed

---

*Generated by [ArchSpec](https://archspec.dev) + [MAID Runner](https://github.com/mamertofabian/maid-runner)*
