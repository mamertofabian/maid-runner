---
description: Show MAID project status including file tracking, manifest count, and compliance overview
---

# MAID Status Command

Provide a comprehensive overview of the MAID project status.

## Information to Display

1. **Project Overview:**
   - Total number of manifests
   - Active vs superseded manifests
   - Most recent task number

2. **File Tracking Status:**
   ```bash
   uv run maid validate --quiet
   ```
   Parse and display file tracking analysis:
   - 🔴 UNDECLARED files (high priority)
   - 🟡 REGISTERED files (medium priority)
   - ✅ TRACKED files

3. **Validation Status:**
   - Last validation run status
   - Any pending validation errors

4. **Next Steps:**
   - Suggest creating manifests for UNDECLARED files
   - Suggest completing REGISTERED files
   - Provide next task number for new work

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
