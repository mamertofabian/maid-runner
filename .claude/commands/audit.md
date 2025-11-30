---
description: Audit MAID compliance (cross-cutting)
argument-hint: [optional: manifest-path or scope]
---

Audit compliance: $ARGUMENTS

Use the maid-auditor subagent to:

1. **CRITICAL - Validate ALL (no arguments)**:
   ```
   maid validate
   maid test
   ```
2. Check for violations:
   - Public APIs not in manifest
   - Tests don't USE artifacts
   - TODO/FIXME in code
   - Files outside manifest
3. Categorize issues (CRITICAL/HIGH/MEDIUM/LOW)
4. Provide remediation recommendations

See CLAUDE.md for compliance standards.
