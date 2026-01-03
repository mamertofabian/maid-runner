# MAID Runner Plugin Architecture

## Overview

The MAID Runner plugin integrates the Manifest-driven AI Development (MAID) methodology directly into Claude Code, providing automatic workflow enforcement, validation tools, and slash commands.

## Plugin Components

### 1. Plugin Manifest (`.claude-plugin/plugin.json`)

**Purpose**: Defines plugin metadata and identity

**Key fields**:
- `name`: "maid-runner" (becomes namespace for commands)
- `version`: Semantic versioning
- `description`: What the plugin does
- `keywords`: Discovery tags

**Location**: `.claude-plugin/plugin.json`

### 2. MAID Workflow Skill (`skills/maid-workflow/`)

**Purpose**: Automatically enforces MAID methodology when Claude detects code changes

**How it works**:
- **Model-invoked**: Claude automatically applies when user requests code changes
- **Trigger description**: "Enforces Manifest-driven AI Development (MAID) methodology for all code changes. Use when creating features, fixing bugs, refactoring code..."
- **Allowed tools**: Read, Write, Edit, Bash (maid/pytest), Grep, Glob
- **Progressive disclosure**: Main SKILL.md + supporting docs loaded on-demand

**Files**:
```
skills/maid-workflow/
├── SKILL.md              # Main Skill (always loaded)
├── MAID_SPECS.md         # Full specs (symlink, loaded on-demand)
├── MANIFEST_GUIDE.md     # Manifest creation details
└── VALIDATION_GUIDE.md   # Validation workflow details
```

**Content structure**:
```yaml
---
name: maid-workflow
description: [Semantic trigger description]
allowed-tools: [Restricted tool list]
---

# Quick reference
[Essential MAID workflow steps]

# Progressive disclosure
Links to detailed guides
```

### 3. MCP Server Integration (`.mcp.json`)

**Purpose**: Automatically runs MAID Runner MCP server from PyPI to expose tools

**Configuration**:
```json
{
  "mcpServers": {
    "maid-runner": {
      "command": "uvx",
      "args": ["maid-runner-mcp"],
      "env": {}
    }
  }
}
```

**How it works**:
- Uses `uvx` to automatically download and run from https://pypi.org/project/maid-runner-mcp/
- No local installation needed
- Always uses the latest published version
- Portable across all installations

**Exposed tools**:
- `maid_validate` - Manifest/implementation validation
- `maid_snapshot` - Generate manifests from code
- `maid_list_manifests` - Find manifests for files
- `maid_generate_stubs` - Create test stubs
- `maid_files` - File tracking status
- `maid_get_schema` - Manifest JSON schema

**Environment variables**:
- `${CLAUDE_PLUGIN_ROOT}`: Plugin installation directory
- `PYTHONPATH`: Points to maid-runner source

### 4. Slash Commands (`commands/`)

**Purpose**: Explicit user invocation of MAID operations

**Commands**:

| Command | File | Purpose |
|---------|------|---------|
| `/maid-runner:validate` | `validate.md` | Validate manifests |
| `/maid-runner:status` | `status.md` | Show project status |
| `/maid-runner:test` | `test.md` | Run MAID tests |

**Command structure**:
```markdown
---
description: Brief command description
---

# Command Title

Instructions for Claude on what to do when command is invoked.
Uses $ARGUMENTS for user input.
```

**Namespace**: All commands prefixed with `maid-runner:` to avoid conflicts

## Integration Flow

### Automatic Workflow (Skills)

```mermaid
User Request
    ↓
"Add a new feature..."
    ↓
Claude matches description
    ↓
Activates maid-workflow Skill
    ↓
Loads SKILL.md into context
    ↓
Guides user through MAID phases
    ↓
Loads supporting docs as needed
```

### Explicit Commands (Slash)

```mermaid
User Types
    ↓
/maid-runner:validate
    ↓
Claude loads validate.md
    ↓
Executes validation logic
    ↓
Reports results
```

### Tool Access (MCP)

```mermaid
Claude needs to validate
    ↓
Calls maid_validate MCP tool
    ↓
MCP server executes
    ↓
Returns validation results
    ↓
Claude processes and presents
```

## Directory Structure

```
plugin/
├── .claude-plugin/
│   └── plugin.json           # Required: Plugin manifest
│
├── skills/
│   └── maid-workflow/
│       ├── SKILL.md          # Main Skill (auto-invoked)
│       ├── MAID_SPECS.md     # Full specs (symlink)
│       ├── MANIFEST_GUIDE.md # Detailed manifest guide
│       └── VALIDATION_GUIDE.md # Validation workflow
│
├── commands/
│   ├── validate.md           # /maid-runner:validate
│   ├── status.md             # /maid-runner:status
│   └── test.md               # /maid-runner:test
│
├── .mcp.json                 # MCP server configuration
│
├── README.md                 # Full documentation
├── QUICKSTART.md             # Getting started guide
└── PLUGIN_ARCHITECTURE.md    # This file
```

## Key Design Decisions

### 1. Skills Over Commands for Core Workflow

**Why**: Skills are model-invoked, matching MAID's philosophy of automatic methodology enforcement.

**Benefit**: Users don't need to remember to invoke MAID - Claude applies it contextually.

### 2. Progressive Disclosure in Skill

**Why**: MAID specs are comprehensive (~2000+ lines). Loading everything upfront wastes context.

**Solution**:
- SKILL.md: Quick reference (~500 lines)
- Supporting docs: Loaded only when needed

### 3. MCP Server for Tool Access

**Why**: Provides programmatic access to MAID validation tools.

**Benefit**: Claude can check validation status, generate snapshots, etc. without shell commands.

### 4. Slash Commands for Explicit Operations

**Why**: Some operations (like status checks) are better as explicit invocations.

**Benefit**: Users can quickly check status or validate without a full conversation.

### 5. PyPI-Based MCP Server

**Decision**: Use `uvx` to run maid-runner-mcp from PyPI

**Why**:
- Zero local installation required
- Reuses existing, tested MCP implementation published at https://pypi.org/project/maid-runner-mcp/
- Single source of truth for MAID tools
- No code duplication
- Portable across all systems
- Automatic version updates

**Benefits**:
- Plugin works out-of-the-box on any system with `uv` installed
- No path configuration needed
- Always gets the latest published MCP server version
- Easy distribution and installation

## Installation Scopes

### User Scope (Default)
```bash
claude plugin install ./plugin --scope user
```

**Location**: `~/.claude/settings.json`
**Visibility**: All projects for this user
**Use case**: Personal MAID enforcement

### Project Scope (Team)
```bash
claude plugin install ./plugin --scope project
```

**Location**: `.claude/settings.json` (checked into repo)
**Visibility**: All team members in this project
**Use case**: Team-wide MAID enforcement

### Local Scope (Per-Project Personal)
```bash
claude plugin install ./plugin --scope local
```

**Location**: `.claude/settings.local.json` (gitignored)
**Visibility**: Just this user in this project
**Use case**: Project-specific MAID customization

## Future Enhancements

### Phase 2: Additional Skills
- `maid-validator` - Deep artifact validation expertise
- `maid-refactor-guide` - Refactoring guidance

### Phase 3: Hooks Integration
- Auto-validate on file save
- Pre-commit manifest checks

### Phase 4: LSP Integration
- Real-time manifest syntax validation
- Manifest schema completion
- Inline artifact validation

### Phase 5: Advanced Agents
- `maid-manifest-architect` - Specialized manifest creation
- `maid-test-designer` - Test design expert
- `maid-developer` - TDD implementation
- `maid-refactorer` - Code quality improvement

## Testing Strategy

### Local Testing
```bash
cd plugin
claude --plugin-dir .
```

### Verification Checklist
- [ ] Skills appear in `/help`
- [ ] MCP server listed in `/mcp`
- [ ] Commands work: `/maid-runner:validate`
- [ ] Skill auto-activates on code change requests
- [ ] MCP tools accessible
- [ ] Progressive disclosure works

### Integration Testing
1. Test new feature creation (full MAID workflow)
2. Test editing existing file (manifest chain)
3. Test validation commands
4. Test status reporting
5. Test MCP tool invocation

## Deployment

### Development
```bash
claude --plugin-dir ./plugin
```

### Personal Use
```bash
claude plugin install ./plugin --scope user
```

### Team Distribution
```bash
# In project root
claude plugin install ./plugin --scope project

# Commit .claude/settings.json
git add .claude/settings.json
git commit -m "Add MAID Runner plugin for team"
```

### Marketplace Distribution
1. Create marketplace manifest
2. Publish to Git repository
3. Team adds marketplace
4. Team installs plugin

See `README.md` for detailed distribution instructions.

## Troubleshooting

### Plugin Not Loading
```bash
claude --debug --plugin-dir ./plugin
```

Check for:
- Invalid JSON in plugin.json
- Missing .claude-plugin directory
- Incorrect directory structure

### MCP Server Not Starting
Check:
- `uv` is installed
- maid-runner accessible from parent directory
- PYTHONPATH points to correct location

### Skill Not Activating
Improve trigger phrases:
- Use specific language: "Add a feature", "Fix a bug", "Refactor code"
- Avoid vague: "Change this", "Update that"

## Summary

The MAID Runner plugin provides:

✅ **Automatic enforcement**: Skills-based MAID workflow
✅ **Tool access**: MCP server integration
✅ **Explicit commands**: Slash commands for validation
✅ **Progressive disclosure**: Efficient context usage
✅ **Team-ready**: Multi-scope installation

**Design principle**: Make MAID the default, not the exception.
