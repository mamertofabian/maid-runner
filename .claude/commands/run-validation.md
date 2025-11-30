---
description: Run validation tests for a manifest or task number
argument-hint: [manifest-path | task-number]
---

Run validation tests for: $1

If task number (e.g., "001"), run `pytest tests/test_task_$1_*.py -v`

If manifest path, extract and run the validationCommand from the manifest.
