---
description: Initialize MAID methodology in a project (creates manifests/ directory and CLAUDE.md)
---

# MAID Init Command

Initialize MAID methodology in an existing project.

## Purpose

Sets up the MAID infrastructure in a repository:
- Creates `manifests/` directory
- Generates `CLAUDE.md` with MAID workflow instructions
- Optionally creates `.gitignore` entries
- Establishes project structure for MAID compliance

## Usage

```bash
# Initialize in current directory
uv run maid init

# Initialize in specific directory
uv run maid init --target-dir /path/to/project

# Force overwrite existing files
uv run maid init --force
```

## What Gets Created

1. **manifests/** directory
   - For storing task manifests
   - With `.gitkeep` to ensure it's tracked

2. **CLAUDE.md** file
   - Project-level MAID instructions
   - Workflow enforcement guidelines
   - Template for customization

3. **Optional: .gitignore entries**
   - Recommended entries for MAID files (if .gitignore exists)

## After Init

Once initialized:
1. Review and customize `CLAUDE.md` for your project
2. Start creating manifests with `maid manifest create`
3. Or snapshot existing code with `maid snapshot`
4. Commit the MAID infrastructure to version control

## Example Workflow

User: `/maid-runner:init`

1. Check if already initialized
2. Create manifests/ directory
3. Generate CLAUDE.md
4. Show what was created
5. Provide next steps

## Output

After initialization:
- Confirmation of created directories/files
- Path to `CLAUDE.md` for customization
- Next steps:
  - "Customize CLAUDE.md for your project"
  - "Start with: `maid snapshot` for existing code"
  - "Or: `maid manifest create` for new features"

## Notes

- Safe to run multiple times (won't overwrite without --force)
- Works with Python and TypeScript projects
- CLAUDE.md can be customized per project
