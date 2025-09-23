# MAID Development TODOs and Notes

## Immediate Priority: Type Validation

### Critical Gap Identified
We are NOT validating Python type hints against manifest type declarations. This is a fundamental contract validation that must be implemented BEFORE the systemic validation infrastructure.

### NEW Task-005: Type Validation
**This will shift existing roadmap tasks 005-010 to become 006-011**

#### Why This Is Critical
1. **Contract Completeness**: Types are explicit in manifests but not validated
2. **Agent Reliability**: Developer agents need exact type information
3. **Static Analysis**: Enables mypy/pyright integration
4. **Documentation as Code**: Type hints ARE the documentation
5. **Prevents Silent Failures**: Wrong types can pass current validation

#### What Needs Validation
```python
# Manifest declares:
"parameters": [{"name": "user_id", "type": "int"}],
"returns": "User"

# Should validate:
def get_user_by_id(self, user_id: int) -> User:  # ✅ Matches manifest

# Should fail:
def get_user_by_id(self, user_id):               # ❌ Missing type hint
def get_user_by_id(self, user_id: str) -> User:  # ❌ Wrong type
def get_user_by_id(self, user_id: int) -> None:  # ❌ Wrong return type
```

#### Implementation Strategy
1. Enhance `_ArtifactCollector` to extract type annotations from AST
2. Add type comparison logic (handle complex types: List, Optional, Union)
3. Validate parameter types AND return types
4. Support both function and method signatures
5. Handle class type hints (for class attributes)

#### Manifest Structure for Task-005
```json
{
  "goal": "Add Python type hint validation to ensure implementation types match manifest type declarations",
  "taskType": "edit",
  "editableFiles": ["validators/manifest_validator.py"],
  "readonlyFiles": [
    "tests/test_task_005_type_validation.py",
    "validators/schemas/manifest.schema.json"
  ],
  "expectedArtifacts": {
    "file": "validators/manifest_validator.py",
    "contains": [
      {
        "type": "function",
        "name": "validate_type_hints",
        "parameters": [
          {"name": "manifest_data", "type": "dict"},
          {"name": "implementation_file", "type": "str"}
        ],
        "returns": "bool"
      },
      {
        "type": "function",
        "name": "extract_type_annotation",
        "parameters": [{"name": "node", "type": "ast.AST"}],
        "returns": "str"
      },
      {
        "type": "function",
        "name": "compare_types",
        "parameters": [
          {"name": "manifest_type", "type": "str"},
          {"name": "implementation_type", "type": "str"}
        ],
        "returns": "bool"
      }
    ]
  }
}
```

---

## Development Resources

### Sub-Agent Architecture
**3 Claude Code sub-agents have been created for parallel development:**

1. **Manifest Agent**: Specializes in creating and validating manifests
2. **Test Agent**: Focuses on behavioral test development
3. **Implementation Agent**: Handles code implementation

These agents can work in parallel on different tasks once manifests are created, following the MAID workflow phases.

---

## Task Ordering (Updated)

### Original Roadmap:
- Task-005: Systemic Validator
- Task-006: Command Executor
- Task-007: Coverage Analyzer
- Task-008: Validation Reporter
- Task-009: CI/CD Integration
- Task-010: MAID Runner CLI

### NEW Ordering (with Type Validation):
- **Task-005: Type Validation** ← INSERT
- Task-006: Systemic Validator (was 005)
- Task-007: Command Executor (was 006)
- Task-008: Coverage Analyzer (was 007)
- Task-009: Validation Reporter (was 008)
- Task-010: CI/CD Integration (was 009)
- Task-011: MAID Runner CLI (was 010)

---

## Review Items for Existing Code

### Check Type Declarations in Existing Manifests:
- [ ] task-001: Does `validate_schema` declare parameter/return types?
- [ ] task-002: Does `validate_with_ast` have complete type info?
- [ ] task-003: Are behavioral validation functions typed?
- [ ] task-004: Are integration functions typed?

### Check Implementation Type Hints:
- [ ] validators/manifest_validator.py: Are functions properly typed?
- [ ] validate_manifest.py: Do functions have type hints?

---

## Validation Layers (Final Architecture)

1. **Structural**: Manifest conforms to schema
2. **Type Contract**: Implementation types match manifest declarations ← NEW
3. **Behavioral**: Tests reference declared artifacts
4. **Implementation**: Code contains declared artifacts
5. **Execution**: Tests actually run and pass (future)
6. **Coverage**: Tests execute artifact code paths (future)

---

## Notes on Sub-Agent Workflow

With 3 sub-agents available, we can parallelize:

**Sequential Phase (must be in order):**
1. Human creates manifest (or Manifest Agent assists)
2. Test Agent creates behavioral tests
3. Implementation Agent writes code

**Parallel Validation Phase (can run simultaneously):**
- Agent 1: Run structural validation
- Agent 2: Run type validation
- Agent 3: Run behavioral validation

This parallelization can significantly speed up the development cycle while maintaining MAID compliance.

---

## Next Actions

1. **Implement Task-005 (Type Validation)** before proceeding with roadmap
2. **Update MAID_RUNNER_COMPLETION_ROADMAP.md** with new task ordering
3. **Review and update existing manifests** to ensure type declarations are complete
4. **Test sub-agent coordination** on Task-005 as proof of concept

---

*Note: Type validation is foundational and should be implemented immediately to strengthen the entire MAID validation infrastructure.*