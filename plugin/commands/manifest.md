---
description: Create a new MAID manifest with automatic task numbering and smart supersession handling
---

# MAID Manifest Create Command

Create a new manifest for a file with automatic task numbering and supersession.

## Purpose

The CLI command for creating manifests provides:
- ✅ Auto-numbering (finds next available task number)
- ✅ Auto-detects taskType (create/edit based on file existence)
- ✅ Auto-supersedes snapshots when editing frozen code
- ✅ Auto-generates test file path
- ✅ Schema validation
- ✅ Handles deletion and rename operations

## Basic Usage

```bash
# Create manifest with artifacts
uv run maid manifest create <file-path> \
  --goal "Clear description" \
  --artifacts '[{"type":"function","name":"foo","args":[],"returns":"str"}]'

# Preview first (dry-run)
uv run maid manifest create <file-path> \
  --goal "..." \
  --artifacts '[...]' \
  --dry-run

# Output as JSON (for programmatic use)
uv run maid manifest create <file-path> \
  --goal "..." \
  --artifacts '[...]' \
  --json
```

## Common Operations

### New File (taskType: create)
```bash
uv run maid manifest create src/new_module.py \
  --goal "Add payment processing module" \
  --artifacts '[
    {"type":"function","name":"process_payment","args":[{"name":"amount","type":"Decimal"}],"returns":"PaymentResult"}
  ]'
```

### Edit Existing File (taskType: edit)
```bash
# Auto-detects "edit" and supersedes snapshot if needed
uv run maid manifest create src/existing_module.py \
  --goal "Add refund support" \
  --artifacts '[
    {"type":"function","name":"process_refund","args":[{"name":"payment_id","type":"str"}],"returns":"RefundResult"}
  ]'
```

### Delete File
```bash
uv run maid manifest create src/deprecated.py \
  --goal "Remove deprecated module" \
  --delete
```

### Rename File
```bash
uv run maid manifest create src/old_name.py \
  --goal "Rename module for clarity" \
  --rename-to src/new_name.py \
  --artifacts '[...]'  # Same artifacts, new location
```

## Additional Options

### Customize Test File
```bash
uv run maid manifest create <file-path> \
  --goal "..." \
  --artifacts '[...]' \
  --test-file tests/custom_test_name.py
```

### Add Readonly Dependencies
```bash
uv run maid manifest create <file-path> \
  --goal "..." \
  --artifacts '[...]' \
  --readonly-files "src/utils.py,src/types.py"
```

### Force Specific Task Number
```bash
uv run maid manifest create <file-path> \
  --goal "..." \
  --artifacts '[...]' \
  --task-number 100
```

### Force Supersede Specific Manifest
```bash
uv run maid manifest create <file-path> \
  --goal "..." \
  --artifacts '[...]' \
  --force-supersede manifests/task-042-old-version.manifest.json
```

## Artifact JSON Format

```json
[
  {
    "type": "function",
    "name": "my_function",
    "args": [
      {"name": "param1", "type": "str"},
      {"name": "param2", "type": "int"}
    ],
    "returns": "bool"
  },
  {
    "type": "class",
    "name": "MyClass"
  },
  {
    "type": "function",
    "name": "my_method",
    "class": "MyClass",
    "args": [{"name": "value", "type": "str"}]
  },
  {
    "type": "attribute",
    "name": "my_attr",
    "class": "MyClass"
  }
]
```

## Example Usage

User: `/maid-runner:manifest src/payments.py --goal "Add payment processing"`

1. Help construct the artifacts JSON
2. Run `maid manifest create` with proper arguments
3. Show created manifest path
4. Show auto-generated test file path
5. Explain next steps (generate stubs, write tests)

## Output

After creating manifest:
- Path to created manifest (e.g., `manifests/task-043-add-payment-processing.manifest.json`)
- Task number assigned
- Test file path
- Whether snapshot was superseded (if editing frozen code)
- Next steps:
  - Generate test stubs: `maid generate-stubs <manifest>`
  - Write behavioral tests
  - Validate: `maid validate <manifest> --validation-mode behavioral`

## Notes

- Always use --dry-run first to preview
- Artifacts must be valid JSON array
- Auto-numbering prevents conflicts
- Auto-supersession handles snapshot transitions smoothly
