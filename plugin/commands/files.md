---
description: Show file-level MAID tracking status (undeclared, registered, tracked files) without full validation
---

# MAID Files Command

Show which files are tracked by MAID manifests and their compliance status.

## Purpose

Quick file tracking analysis without running full validation:
- 🔴 **UNDECLARED**: Files exist but not in any manifest
- 🟡 **REGISTERED**: Files in manifests but incomplete compliance
- ✅ **TRACKED**: Files with full MAID compliance
- 🔵 **UNTRACKED TESTS**: Test files not referenced in manifests

## Usage

```bash
# Show all file tracking status
uv run maid files

# Show only issues (undeclared and registered)
uv run maid files --issues-only

# Filter by specific status
uv run maid files --status undeclared
uv run maid files --status registered
uv run maid files --status tracked

# Machine-readable output
uv run maid files --quiet

# JSON output (for programmatic use)
uv run maid files --json

# Hide private implementation files
uv run maid files --hide-private
```

## Status Levels Explained

### 🔴 UNDECLARED (High Priority)
Files exist in codebase but not in any manifest:
- No audit trail of when/why created
- **Action**: Create manifest with `maid manifest create` or `maid snapshot`

### 🟡 REGISTERED (Medium Priority)
Files are tracked but not fully MAID-compliant:
- Missing `expectedArtifacts`
- No `validationCommand`
- Only in `readonlyFiles`
- **Action**: Add `expectedArtifacts` and tests

### ✅ TRACKED (Clean)
Files with full MAID compliance:
- Proper `expectedArtifacts` declaration
- Behavioral tests with `validationCommand`
- Complete audit trail

### 🔵 UNTRACKED TESTS
Test files not referenced in any manifest:
- Consider adding to `readonlyFiles` for tracking

## Example Usage

User: `/maid-runner:files --issues-only`

1. Run `maid files --issues-only`
2. Parse and format output
3. Show:
   - UNDECLARED files with suggested actions
   - REGISTERED files with what's missing
   - Summary counts
4. Provide actionable recommendations

## Output Example

```
File Tracking Status
===================

🔴 UNDECLARED FILES (3 files)
  - src/helpers.py
    → Action: uv run maid snapshot src/helpers.py

  - src/utils/format.py
    → Action: uv run maid manifest create src/utils/format.py --goal "..."

  - scripts/deploy.py
    → Action: uv run maid snapshot scripts/deploy.py

🟡 REGISTERED FILES (2 files)
  - src/config.py
    ⚠️  In creatableFiles but missing expectedArtifacts
    → Action: Add artifacts and tests to manifest

  - src/validators/__init__.py
    ⚠️  Only in readonlyFiles (no creation record)
    → Action: Create proper manifest with artifacts

✅ TRACKED (107 files)

📊 Summary:
  - 3 undeclared (need manifests)
  - 2 registered (need completion)
  - 107 tracked (compliant)

Next Steps:
  1. Address UNDECLARED files first (create manifests)
  2. Complete REGISTERED files (add artifacts and tests)
  3. Run 'maid validate' for full compliance check
```

## Integration with Status Command

The `/maid-runner:status` command uses `maid files --issues-only` as its primary data source for file tracking information.

## Notes

- Much faster than full validation (no AST parsing)
- Shows file-level view without artifact details
- Use before committing to catch untracked files
- Integrates with git to find all project files
- Respects .gitignore patterns
