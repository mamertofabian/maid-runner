---
description: Enhance existing manifest with additional details
argument-hint: [manifest-path] [enhancement instructions]
---

Enhance manifest: $1

Instructions: $2

Tasks:
1. Read current manifest
2. Apply enhancements (add artifacts, refine goal, etc.)
3. Validate: `maid validate $1 --use-manifest-chain`
4. If tests exist, ensure behavioral validation still passes

Keep changes focused and maintain manifest validity.
