# MAID Runner Plugin for Claude Code

**Manifest-driven AI Development (MAID) methodology enforcement for Claude Code.**

This plugin automatically applies the MAID workflow to all code changes, ensuring manifest-first development with behavioral tests and validation.

## What is MAID?

MAID (Manifest-driven AI Development) is a methodology that ensures:
- Every code change is explicitly documented in a manifest
- Behavioral tests are written before implementation (TDD)
- All artifacts are validated against their declarations
- Complete audit trail of all changes

## Prerequisites

**uv/uvx required**: This plugin uses the `maid-runner-mcp` MCP server, which is automatically downloaded from [PyPI](https://pypi.org/project/maid-runner-mcp/) when the plugin loads.

Ensure you have `uv` installed:
```bash
# Install uv if needed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or on macOS with Homebrew
brew install uv
```

No additional setup needed - the MCP server is fetched automatically via `uvx`!

## Features

### 🎯 Automatic MAID Workflow Enforcement (Skills)

The `maid-workflow` Skill is **automatically applied** by Claude when you:
- Create new features
- Fix bugs
- Refactor code
- Make any code modifications

Claude will guide you through the MAID workflow:
1. Phase 1: Goal definition
2. Phase 2: Manifest and test creation (with validation)
3. Phase 3: Implementation (with validation)
4. Phase 4: Integration verification

### 🔧 MAID Tools via MCP Server

Access all MAID Runner tools through the bundled MCP server:
- `maid_validate` - Validate manifests and implementations
- `maid_snapshot` - Generate manifests from existing code
- `maid_list_manifests` - Find manifests for a file
- `maid_generate_stubs` - Create test stubs from manifests
- `maid_files` - Check file tracking status
- And more...

### ⌨️ Slash Commands (9 Commands)

Explicit commands for MAID operations:

**Workflow Commands:**
- `/maid-runner:manifest <file>` - Create manifest with auto-numbering and supersession
- `/maid-runner:stubs <manifest>` - Generate test stubs from manifest
- `/maid-runner:validate [manifest]` - Validate manifests (behavioral/implementation modes)
- `/maid-runner:test [manifest]` - Run validation tests with batch mode

**Status & Analysis:**
- `/maid-runner:status` - Show project MAID compliance overview
- `/maid-runner:files` - Show file tracking status (undeclared/registered/tracked)

**Initialization & Migration:**
- `/maid-runner:init` - Initialize MAID in existing project
- `/maid-runner:snapshot <file>` - Create snapshot manifest from existing code

## Installation

### Option 1: Test Locally (Development)

Test the plugin without installing to a marketplace:

```bash
# From the maid-runner project root
cd plugin

# Start Claude Code with the plugin loaded
claude --plugin-dir .
```

### Option 2: Install from Directory

Install the plugin to your user scope:

```bash
# Install to user scope (available in all projects)
claude plugin install /path/to/maid-runner/plugin --scope user

# Install to project scope (team-shared via version control)
claude plugin install /path/to/maid-runner/plugin --scope project

# Install to local scope (project-specific, gitignored)
claude plugin install /path/to/maid-runner/plugin --scope local
```

### Option 3: Install from Marketplace (Future)

Once published to a marketplace:

```bash
claude plugin install maid-runner@official
```

## Testing the Plugin

### 1. Test MAID Skill Activation

Start Claude Code with the plugin:

```bash
cd /path/to/maid-runner/plugin
claude --plugin-dir .
```

In Claude Code, try these prompts:

```
> What Skills are available?
```

You should see `maid-workflow` in the list.

```
> I want to add a new feature to calculate tax rates
```

Claude should automatically activate the `maid-workflow` Skill and guide you through creating a manifest first.

### 2. Test MCP Server Integration

Check if MCP tools are available:

```
> /mcp
```

You should see `maid-runner` MCP server listed with its tools.

Test a tool:

```
> Can you check the file tracking status using the MAID tools?
```

Claude should use the `maid_files` MCP tool to show file tracking.

### 3. Test Slash Commands

Try the validation command:

```
> /maid-runner:status
```

This should show your MAID project status.

```
> /maid-runner:validate manifests/task-001-example.manifest.json
```

This should validate the specified manifest.

## Plugin Structure

```
plugin/
├── .claude-plugin/
│   └── plugin.json              # Plugin metadata
│
├── skills/
│   └── maid-workflow/
│       ├── SKILL.md             # Main MAID workflow Skill
│       ├── MAID_SPECS.md        # Full MAID specs (symlink)
│       ├── MANIFEST_GUIDE.md    # Manifest creation guide
│       └── VALIDATION_GUIDE.md  # Validation guide
│
├── commands/
│   ├── manifest.md              # /maid-runner:manifest command
│   ├── stubs.md                 # /maid-runner:stubs command
│   ├── validate.md              # /maid-runner:validate command
│   ├── test.md                  # /maid-runner:test command
│   ├── status.md                # /maid-runner:status command
│   ├── files.md                 # /maid-runner:files command
│   ├── init.md                  # /maid-runner:init command
│   └── snapshot.md              # /maid-runner:snapshot command
│
├── .mcp.json                    # MCP server configuration
│
└── README.md                    # This file
```

## How It Works

### Skills-Based Auto-Enforcement

When you ask Claude to make code changes, the `maid-workflow` Skill is automatically activated based on semantic matching:

**Trigger phrases:**
- "Add a new feature..."
- "Fix the bug in..."
- "Refactor this code..."
- "Create a new module..."
- "Update the implementation..."

**Claude's response (using CLI):**
1. Confirms the goal (Phase 1)
2. Creates manifest using `maid manifest create` with auto-numbering (Phase 2)
3. Generates test stubs with `maid generate-stubs` (Phase 2)
4. Guides you to enhance tests to use declared artifacts (Phase 2)
5. Validates tests with `maid validate --validation-mode behavioral` (Phase 2)
6. Implements code to pass tests (Phase 3)
7. Validates implementation with `maid validate --validation-mode implementation` (Phase 3)
8. Verifies complete integration with `maid validate` and `maid test` (Phase 4)

### MCP Tools Integration

Claude can use MAID tools directly through the MCP server:

```python
# Claude internally calls:
await mcp_tool("maid_validate", {
    "manifest_path": "manifests/task-042.manifest.json",
    "validation_mode": "implementation",
    "use_manifest_chain": True
})
```

### Slash Commands

Users can explicitly invoke MAID operations:

```
# Workflow
/maid-runner:manifest src/new.py   → Create manifest with CLI
/maid-runner:stubs task-042        → Generate test stubs
/maid-runner:validate              → Validate all manifests
/maid-runner:validate task-042     → Validate specific manifest
/maid-runner:test                  → Run all MAID tests
/maid-runner:test task-042         → Run specific manifest tests

# Status & Analysis
/maid-runner:status                → Project compliance overview
/maid-runner:files                 → File tracking status

# Initialization
/maid-runner:init                  → Initialize MAID in project
/maid-runner:snapshot old_code.py  → Snapshot existing code
```

## Progressive Disclosure

The MAID Skill uses progressive disclosure to keep context efficient:

**Main SKILL.md**: Overview and quick reference (loaded in every conversation)

**Supporting docs** (loaded only when needed):
- `MANIFEST_GUIDE.md` - Detailed manifest creation
- `VALIDATION_GUIDE.md` - Validation details and troubleshooting
- `MAID_SPECS.md` - Complete MAID methodology specification

Claude reads these files only when you ask for details or encounter issues.

## Configuration

### Environment Variables

The MCP server supports these environment variables:

- `MANIFEST_DIR` - Directory containing manifests (default: "manifests")
- `PYTHONPATH` - Python path for MCP server

### Allowed Tools

The `maid-workflow` Skill restricts Claude to these tools:
- `Read`, `Write`, `Edit` - File operations
- `Bash(uv run maid:*)` - MAID CLI commands
- `Bash(pytest:*)` - Test execution
- `Bash(python -m pytest:*)` - Alternative test execution
- `Grep`, `Glob` - File searching

This ensures Claude focuses on MAID-compliant operations.

## Troubleshooting

### Skill Not Triggering

**Symptom**: Claude doesn't apply MAID workflow automatically

**Solution**: Use more specific trigger phrases:
- Instead of: "Change this code"
- Try: "Add a new feature to handle payment processing"

### MCP Server Not Starting

**Symptom**: MCP tools not available, `/mcp` shows `maid-runner` as failed

**Debug**:
```bash
claude --debug
```

Check for MCP server initialization errors.

**Common fixes**:

1. **Ensure `uv` is installed and in PATH**:
   ```bash
   # Check if uv is available
   which uvx

   # Install uv if needed
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Test the MCP server manually**:
   ```bash
   # This should download and run maid-runner-mcp from PyPI
   uvx maid-runner-mcp
   # Press Ctrl+C to stop
   ```

3. **Check the latest version on PyPI**:
   The plugin uses the latest version from https://pypi.org/project/maid-runner-mcp/

4. **Force reinstall if needed**:
   ```bash
   # Clear uvx cache and reinstall
   uvx --force maid-runner-mcp
   ```

### Plugin Not Loading

**Symptom**: Commands or Skills don't appear

**Debug**:
```bash
claude --debug --plugin-dir /path/to/plugin
```

**Common issues**:
- Ensure `.claude-plugin/plugin.json` exists
- Check JSON syntax in plugin.json
- Verify directory structure (skills/, commands/ at root, not in .claude-plugin/)

## Development Workflow

### Adding New Skills

1. Create new directory in `skills/`
2. Add `SKILL.md` with frontmatter
3. Test with `claude --plugin-dir .`

### Adding New Commands

1. Create new `.md` file in `commands/`
2. Add frontmatter with description
3. Test with `/maid-runner:command-name`

### Updating the Plugin

After making changes:

```bash
# Restart Claude Code to reload plugin
# If installed, reinstall to update
claude plugin update maid-runner --scope user
```

## Distributing the Plugin

### Create a Marketplace

See [Claude Code Plugin Marketplaces](https://docs.anthropic.com/en/docs/claude-code/plugin-marketplaces) for details.

**Quick start:**

1. Create marketplace directory:
```bash
mkdir maid-marketplace
cd maid-marketplace
```

2. Create marketplace manifest:
```json
{
  "name": "maid-official",
  "plugins": [
    {
      "name": "maid-runner",
      "source": "../plugin",
      "strict": false
    }
  ]
}
```

3. Distribute via Git repository or file share

4. Users install:
```bash
claude plugin marketplace add maid-official /path/to/marketplace
claude plugin install maid-runner@maid-official
```

## Integration Scopes

### User Scope (Default)
```bash
claude plugin install maid-runner --scope user
```
- Available across all your projects
- Stored in `~/.claude/settings.json`
- Personal MAID enforcement

### Project Scope (Team)
```bash
claude plugin install maid-runner --scope project
```
- Shared with team via `.claude/settings.json` in repo
- Everyone on the team gets MAID automatically
- Enforces team-wide MAID compliance

### Managed Scope (Enterprise)
Administrators can deploy MAID organization-wide via `managed-settings.json`.

## Benefits

### For Individual Developers
- ✅ Automatic MAID workflow guidance
- ✅ No need to remember methodology steps
- ✅ Real-time validation feedback
- ✅ Consistent across all projects

### For Teams
- ✅ Shared MAID enforcement
- ✅ One-command installation
- ✅ Complete audit trail
- ✅ Standardized development process

### For Organizations
- ✅ Enterprise-wide deployment
- ✅ Centralized methodology control
- ✅ Compliance verification
- ✅ Quality assurance

## Next Steps

1. **Test locally**: `claude --plugin-dir .`
2. **Try the Skills**: Ask Claude to create a feature
3. **Use slash commands**: `/maid-runner:status`
4. **Install for team**: `--scope project`
5. **Create marketplace**: Distribute to organization

## Support

For issues, questions, or contributions:
- GitHub: [your-org/maid-runner](https://github.com/your-org/maid-runner)
- Documentation: See `docs/maid_specs.md` in the main repository

## License

MIT License - See LICENSE file in main repository
