---
description: Run manifest validation tests directly
argument-hint: [manifest-file-path | task-number]
allowed-tools: Bash(uv run python -m pytest*)
---

## Task: Run Validation Tests for Manifest

Execute validation tests for: $1

### Process:

1. Determine which tests to run based on input:
   - If a manifest file path is provided, extract the validation command
   - If a task number is provided, find the corresponding test file

2. Run the appropriate test command

3. Report results clearly

### Execution:

```bash
# If input looks like a task number (e.g., "001", "002")
if [[ "$1" =~ ^[0-9]+$ ]]; then
    TEST_FILE="tests/test_task_${1}_integration.py"
    if [ -f "$TEST_FILE" ]; then
        echo "🧪 Running integration tests for Task $1"
        uv run python -m pytest "$TEST_FILE" -v
    else
        echo "❌ Test file not found: $TEST_FILE"
        echo "🔍 Available tests:"
        ls tests/test_task_*_integration.py 2>/dev/null || echo "No integration tests found"
    fi
else
    # Assume it's a manifest file path
    MANIFEST="$1"
    if [ -f "$MANIFEST" ]; then
        echo "📋 Reading validation command from manifest..."
        # Extract validation command from JSON
        VALIDATION_CMD=$(python -c "import json; print(json.load(open('$MANIFEST'))['validationCommand'])" 2>/dev/null)
        if [ -n "$VALIDATION_CMD" ]; then
            echo "🧪 Running: uv run python -m $VALIDATION_CMD"
            uv run python -m $VALIDATION_CMD
        else
            echo "❌ No validation command found in manifest"
        fi
    else
        echo "❌ Manifest file not found: $MANIFEST"
    fi
fi
```

### Quick Usage:

```bash
# Run tests for task 001
/run-validation 001

# Run tests for task 002
/run-validation 002

# Run tests from specific manifest
/run-validation manifests/task-001.manifest.json
```

This provides a quick way to run validation tests during development!