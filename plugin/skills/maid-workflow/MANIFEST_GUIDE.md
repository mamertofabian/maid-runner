# Manifest Creation Guide

## Recommended: Use CLI for Manifest Creation

**The `maid manifest create` CLI command is the recommended way to create manifests.**

### Quick Start with CLI

```bash
# Create manifest (auto-numbers, auto-supersedes, validates)
uv run maid manifest create <file-path> \
  --goal "Clear description" \
  --artifacts '[{"type":"function","name":"my_func","args":[],"returns":"str"}]'

# Preview first with --dry-run
uv run maid manifest create <file-path> \
  --goal "..." \
  --artifacts '[...]' \
  --dry-run
```

### CLI Benefits

- ✅ **Auto-numbering**: Finds next available task number
- ✅ **Auto-detection**: Detects taskType (create/edit) based on file existence
- ✅ **Auto-supersession**: Supersedes snapshots when editing frozen code
- ✅ **Auto-generation**: Generates test file path
- ✅ **Schema validation**: Validates against schema automatically
- ✅ **Special operations**: Handles delete and rename with flags

### See Also

For CLI details, use:
```bash
uv run maid manifest create --help
```

Or see [SKILL.md](SKILL.md) for common CLI patterns.

---

## Manifest Structure (Manual Creation)

Every manifest must follow this JSON schema:

```json
{
  "goal": "string - What this task accomplishes",
  "taskType": "create|edit|refactor",
  "supersedes": ["array of manifest paths that this replaces"],
  "creatableFiles": ["new files this task creates"],
  "editableFiles": ["existing files this task modifies"],
  "readonlyFiles": ["dependencies and test files"],
  "expectedArtifacts": {
    "file": "single/file/path.py",
    "contains": [
      {
        "type": "function|class|attribute",
        "name": "artifact_name",
        "class": "ParentClass (if method/attribute)",
        "args": [{"name": "arg1", "type": "str"}],
        "returns": "ReturnType (optional)"
      }
    ]
  },
  "validationCommand": ["pytest", "tests/test_file.py", "-v"]
}
```

## Critical Rules

### 1. expectedArtifacts is an OBJECT
**WRONG:**
```json
"expectedArtifacts": [
  {"file": "utils.py", "contains": [...]},
  {"file": "handlers.py", "contains": [...]}
]
```

**RIGHT:**
```json
"expectedArtifacts": {
  "file": "utils.py",
  "contains": [...]
}
```

For multiple files, create separate manifests.

### 2. Task Types

- **create**: New files (strict validation - exact match)
  - Use `creatableFiles`
  - Implementation must exactly match `expectedArtifacts`

- **edit**: Modifying existing files (permissive validation - contains at least)
  - Use `editableFiles`
  - Implementation must contain `expectedArtifacts` (can have more)

- **refactor**: Restructuring without API changes
  - Can supersede previous manifests
  - Maintains public API

### 3. File Lists

- **creatableFiles**: New files being created
- **editableFiles**: Existing files being modified
- **readonlyFiles**: Dependencies, tests, docs (not modified but needed for context)

### 4. Artifact Specification

**Function:**
```json
{
  "type": "function",
  "name": "calculate_total",
  "args": [
    {"name": "items", "type": "List[Item]"},
    {"name": "tax_rate", "type": "float"}
  ],
  "returns": "Decimal"
}
```

**Class:**
```json
{
  "type": "class",
  "name": "ShoppingCart"
}
```

**Method:**
```json
{
  "type": "function",
  "name": "add_item",
  "class": "ShoppingCart",
  "args": [{"name": "item", "type": "Item"}],
  "returns": "None"
}
```

**Class Attribute:**
```json
{
  "type": "attribute",
  "name": "max_items",
  "class": "ShoppingCart"
}
```

**Module-level Constant:**
```json
{
  "type": "attribute",
  "name": "DEFAULT_TAX_RATE"
}
```

## Naming Convention

```bash
manifests/task-XXX-brief-description.manifest.json
tests/test_task_XXX_description.py
```

Example:
```bash
manifests/task-042-add-payment-processing.manifest.json
tests/test_task_042_payment_processing.py
```

## Superseding Manifests

When replacing a previous manifest:

```json
{
  "goal": "Update payment processing with refund support",
  "taskType": "edit",
  "supersedes": ["manifests/task-042-add-payment-processing.manifest.json"],
  "editableFiles": ["src/payments.py"],
  ...
}
```

Superseded manifests are excluded from:
- `uv run maid validate` (chain merging)
- `uv run maid test` (validation command execution)

## Validation Commands

**Single test file:**
```json
"validationCommand": ["pytest", "tests/test_task_042_payment.py", "-v"]
```

**Multiple test files:**
```json
"validationCommand": ["pytest", "tests/test_task_042_*.py", "-v"]
```

**Custom commands:**
```json
"validationCommand": ["make", "test-task-042"]
```

## Common Mistakes

### ❌ Multiple files in expectedArtifacts
```json
"expectedArtifacts": {
  "file": "utils.py",
  "contains": [...],
  "file": "handlers.py",  // WRONG! Can't have two "file" keys
  "contains": [...]
}
```

**Fix**: Create separate manifests

### ❌ Forgetting readonlyFiles
```json
{
  "editableFiles": ["src/utils.py"],
  "readonlyFiles": []  // WRONG! Forgot to list test file
}
```

**Fix**: Add test files to readonlyFiles
```json
{
  "editableFiles": ["src/utils.py"],
  "readonlyFiles": ["tests/test_task_042_utils.py"]
}
```

### ❌ Missing artifact details
```json
{
  "type": "function",
  "name": "process_payment"
  // WRONG! Missing args and returns
}
```

**Fix**: Include complete signature
```json
{
  "type": "function",
  "name": "process_payment",
  "args": [
    {"name": "amount", "type": "Decimal"},
    {"name": "method", "type": "PaymentMethod"}
  ],
  "returns": "PaymentResult"
}
```

## Quick Start Template

```json
{
  "goal": "",
  "taskType": "edit",
  "supersedes": [],
  "creatableFiles": [],
  "editableFiles": [],
  "readonlyFiles": [],
  "expectedArtifacts": {
    "file": "",
    "contains": []
  },
  "validationCommand": ["pytest", "tests/test_task_XXX_*.py", "-v"]
}
```

Fill in each field based on your task requirements.
