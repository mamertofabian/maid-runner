# MAID Runner Plugin - Quick Start Guide

Get started with the MAID Runner plugin in under 5 minutes.

## Step 1: Test the Plugin Locally

```bash
# Navigate to the plugin directory
cd /path/to/maid-runner/plugin

# Start Claude Code with the plugin loaded
claude --plugin-dir .
```

## Step 2: Verify Installation

In Claude Code, check that the plugin loaded successfully:

```
> What Skills are available?
```

**Expected**: You should see `maid-workflow` in the Skills list.

```
> /mcp
```

**Expected**: You should see `maid-runner` MCP server with tools like `maid_validate`, `maid_snapshot`, etc.

```
> /help
```

**Expected**: You should see `/maid-runner:validate`, `/maid-runner:status`, `/maid-runner:test` commands.

## Step 3: Test Automatic MAID Enforcement

Try asking Claude to create a new feature:

```
> I want to add a new function to calculate shipping costs based on weight and distance
```

**Expected behavior**:
1. Claude activates the `maid-workflow` Skill
2. Claude asks you to confirm the goal
3. Claude guides you to create a manifest first
4. Claude helps write behavioral tests
5. Claude validates tests use the declared artifacts
6. Claude implements the code
7. Claude validates the implementation

## Step 4: Try Slash Commands

### Check Project Status

```
> /maid-runner:status
```

This shows:
- Total manifests (active vs superseded)
- File tracking status (UNDECLARED, REGISTERED, TRACKED)
- Next task number
- Recommendations

### Validate a Manifest

```
> /maid-runner:validate manifests/task-001-example.manifest.json
```

This runs:
- Behavioral validation (tests use artifacts)
- Implementation validation (code defines artifacts)
- Reports any errors

### Run Tests

```
> /maid-runner:test
```

Runs all validation commands from all active manifests.

## Step 5: Test MCP Tools

Ask Claude to use MAID tools directly:

```
> Can you check which files are tracked by MAID manifests?
```

Claude should use the `maid_files` MCP tool and show you the file tracking status.

```
> Generate a snapshot manifest for src/utils.py
```

Claude should use the `maid_snapshot` MCP tool to create a manifest from the existing file.

## Step 6: Install for Regular Use

Once you've verified the plugin works, install it to your user scope:

```bash
# Exit Claude Code
exit

# Install to user scope (available in all projects)
cd /path/to/maid-runner
claude plugin install ./plugin --scope user

# Restart Claude Code
claude
```

Now the MAID workflow will be automatically available in all your projects!

## Common Test Scenarios

### Test 1: New Feature Creation

**Prompt**: "Create a new module for user authentication with login and logout functions"

**Expected flow**:
1. Confirm goal
2. Create manifest: `manifests/task-XXX-user-authentication.manifest.json`
3. Create tests: `tests/test_task_XXX_authentication.py`
4. Validate tests (behavioral mode)
5. Implement code
6. Validate implementation
7. Run tests

### Test 2: Editing Existing File

**Prompt**: "Add a new method to calculate discounts in the existing ShoppingCart class"

**Expected flow**:
1. Confirm goal
2. Create manifest with `editableFiles` and `--use-manifest-chain`
3. Create tests
4. Validate with manifest chain
5. Implement
6. Validate with chain
7. Run tests

### Test 3: Validation Check

**Prompt**: "/maid-runner:status"

**Expected output**:
```
MAID Project Status
==================

Manifests: X active, Y superseded
Latest task: task-XXX-description

File Tracking:
  ✅ TRACKED: N files
  🟡 REGISTERED: M files
  🔴 UNDECLARED: K files

Next task number: XXX

Recommendations:
  - [Any specific actions needed]
```

## Troubleshooting Quick Fixes

### Plugin Not Loading
```bash
# Check debug output
claude --debug --plugin-dir .
```

Look for errors in plugin initialization.

### Skill Not Activating

Try more specific trigger phrases:
- ❌ "Change this code"
- ✅ "Add a new feature to process payments"
- ✅ "Refactor the authentication module"
- ✅ "Fix the bug in the discount calculation"

### MCP Server Not Working

```bash
# Verify uv and maid-runner are accessible
which uv
cd /path/to/maid-runner && uv run maid --help
```

Ensure the MCP server can find the MAID Runner installation.

## Next Steps

Once you've verified the plugin works:

1. **Read the full README**: `plugin/README.md`
2. **Explore MAID specs**: `docs/maid_specs.md`
3. **Install for team**: Use `--scope project` to share with your team
4. **Create marketplace**: Distribute to your organization

## Quick Reference

```bash
# Test locally
cd plugin && claude --plugin-dir .

# Install to user scope
claude plugin install ./plugin --scope user

# Install to project scope (team)
claude plugin install ./plugin --scope project

# Update plugin
claude plugin update maid-runner --scope user

# Remove plugin
claude plugin uninstall maid-runner --scope user
```

## Support

- See `plugin/README.md` for detailed documentation
- See `docs/maid_specs.md` for MAID methodology
- Check Claude Code docs: https://docs.anthropic.com/en/docs/claude-code/plugins

Happy MAID development! 🎯
