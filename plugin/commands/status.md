---
description: Show MAID project status including file tracking, manifest count, and compliance overview
---

# MAID Status Command

Provide a comprehensive overview of the MAID project status using CLI commands.

## Commands to Run

1. **File Tracking Status (Primary):**
   ```bash
   uv run maid files --issues-only
   ```
   This shows:
   - 🔴 UNDECLARED files (not in any manifest)
   - 🟡 REGISTERED files (incomplete MAID compliance)
   - 🔵 UNTRACKED TEST files (tests not referenced)

2. **Manifest Count:**
   ```bash
   # Count total manifests
   ls manifests/task-*.manifest.json | wc -l

   # Find latest task number
   ls manifests/task-*.manifest.json | tail -1
   ```

3. **Full Validation (Optional):**
   ```bash
   # Run full validation to check compliance
   uv run maid validate --quiet
   ```

## Information to Display

Parse the `maid files` output and present:

1. **File Tracking Summary:**
   - Total UNDECLARED files (with list)
   - Total REGISTERED files (with list)
   - Total TRACKED files (count only)
   - Untracked test files (count)

2. **Manifest Overview:**
   - Total manifests
   - Latest task number
   - Next available task number

3. **Actionable Recommendations:**
   - Which UNDECLARED files need manifests
   - Which REGISTERED files need completion
   - Suggested next steps

## Example Output Format

```
MAID Project Status
==================

Manifests: 42 active, 3 superseded
Latest task: task-042-add-payment-processing

File Tracking:
  ✅ TRACKED: 38 files
  🟡 REGISTERED: 2 files
  🔴 UNDECLARED: 1 file

Next task number: 043

Recommendations:
  - Address UNDECLARED file: src/helpers.py
  - Complete expectedArtifacts for REGISTERED files
```

Present the information in a clear, actionable format.
