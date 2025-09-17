# MAID Stop Hooks

This directory contains Claude Code stop hooks that automatically validate MAID projects when Claude finishes responding.

## Hooks Overview

### 1. AST Validator Hook (`ast-validator.py`)
**Purpose**: Validates that manifests are properly aligned with their implementations using AST analysis.

**What it does**:
- Scans all manifest files in `manifests/` directory
- For each manifest with an `expectedArtifacts.file`, checks if implementation exists
- Runs `validate_with_ast()` with manifest chaining to verify alignment
- Reports validation results
- **Blocks Claude from stopping** if AST validation fails

**When it runs**: Every time Claude stops responding (Stop event)

### 2. Test Runner Hook (`test-runner.py`)
**Purpose**: Runs all tests to ensure implementations work correctly.

**What it does**:
- Runs validation commands from each manifest file
- Runs integration tests (`test_*_integration.py`)
- Runs comprehensive test suite (`pytest tests/`)
- Reports test results
- **Blocks Claude from stopping** if any tests fail

**When it runs**: Every time Claude stops responding (Stop event)

## Hook Configuration

The hooks are configured in `.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/ast-validator.py",
            "timeout": 30
          },
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/test-runner.py",
            "timeout": 300
          }
        ]
      }
    ]
  }
}
```

## Execution Flow

1. **Claude finishes responding**
2. **AST Validator runs** (30 second timeout)
   - If validation fails → Claude is blocked from stopping with error message
   - If validation passes → Continue to next hook
3. **Test Runner runs** (5 minute timeout)
   - If tests fail → Claude is blocked from stopping with error message
   - If tests pass → Claude can stop normally

## Hook Behavior

### When Hooks Block Claude

If either hook fails, Claude receives a `"decision": "block"` response with a specific reason:

- **AST Validation Failure**: "AST validation failed for X manifest(s). Please fix the implementation-manifest alignment issues before proceeding."
- **Test Failure**: "Tests failed for X test suite(s). Please fix the failing tests before proceeding."

### When Hooks Pass

When all validations pass, Claude sees success messages:
- "✨ All manifests are properly aligned with their implementations!"
- "✨ All tests passed! MAID validation complete."

## Loop Prevention

Both hooks check for `stop_hook_active: true` in the input to prevent infinite loops when Claude is continuing due to a previous stop hook.

## Environment

- **Working Directory**: Set to `$CLAUDE_PROJECT_DIR`
- **Python Path**: Set to `.` for local imports
- **Timeout**: AST validator (30s), Test runner (5 minutes)

## Benefits

1. **Automatic Quality Assurance**: Every response is validated
2. **Prevents Drift**: Catches misalignment between specs and code immediately
3. **Continuous Testing**: Ensures all tests pass before Claude stops
4. **MAID Compliance**: Enforces the MAID methodology automatically

## Troubleshooting

If hooks aren't working:
1. Check hook configuration with `/hooks` command in Claude
2. Verify scripts are executable: `chmod +x .claude/hooks/*.py`
3. Test hooks manually: `echo '{"session_id":"test","hook_event_name":"Stop","stop_hook_active":false}' | .claude/hooks/ast-validator.py`
4. Check logs with `claude --debug`

These hooks ensure that your MAID project maintains integrity automatically!