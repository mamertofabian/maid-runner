---
description: Explore and spike an idea before creating manifest
argument-hint: [idea description]
---

Explore the idea: $ARGUMENTS

Quick exploratory spike (no manifest yet):

1. Research codebase for related patterns
2. Identify affected files and components
3. Outline potential approach
4. Estimate complexity and scope
5. Suggest whether this should be one task or multiple

**⚠️ CRITICAL REMINDER for Manifest Creation:**
- `expectedArtifacts` is an **OBJECT** (not an array) that defines artifacts for **ONE file only**
- Structure: `{"file": "path/to/file.py", "contains": [...]}`
- For multi-file features: Create **separate manifests** for each file

Output: Brief summary and recommended next steps for manifest creation.
