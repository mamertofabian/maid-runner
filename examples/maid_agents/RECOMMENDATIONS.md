# Recommendations for maid_agents Improvements

## Executive Summary

The maid_agents project has excellent architecture and MAID compliance but needs significant improvements to its prompt templates to properly work with Claude Code CLI's actual behavior. This document provides specific, actionable recommendations.

---

## Critical Issues to Fix

### 1. Prompt Templates Treat Claude Code as a Code Generator

**Current Problem:**
Templates instruct Claude NOT to explain or use tools, then contradict themselves by asking Claude to use file editing tools.

**Example from `manifest_creation.txt`:**
```
You are a JSON generator. Your ONLY job is to output valid JSON.
Do NOT write explanations, do NOT use markdown, do NOT create files.
...
CRITICAL: Use your file editing tools to directly create this manifest file
```

**Impact:** This confuses Claude Code and may cause it to:
- Ask clarifying questions instead of proceeding
- Output JSON as text instead of writing files
- Ignore the contradictory instructions

**Fix:** Rewrite templates to treat Claude Code as an interactive AI coding assistant that naturally uses tools.

---

### 2. Agent Response Parsing Doesn't Match Streaming JSON Format

**Current Problem:**
Agents expect Claude to have written files (correct), but the prompts tell Claude not to create files (incorrect).

**Example from `developer.py:77-80`:**
```python
# Read the primary file that Claude Code should have written
try:
    with open(primary_file, "r") as f:
        generated_code = f.read()
except FileNotFoundError:
    return self._create_error_response(...)
```

**Fix:** This part is actually correct! The issue is the prompts need to align with this expectation.

---

### 3. Missing Tool Call Tracking

**Current Problem:**
The `ClaudeWrapper` parses streaming JSON and logs tool calls (`_log_tool_calls`), but agents don't use this information to track what files were actually modified.

**Impact:**
- No verification that Claude actually wrote the expected files
- Can't detect if Claude edited unexpected files
- Harder to implement agent visibility boundaries

**Fix:** Add file tracking to ClaudeWrapper and return list of modified files.

---

## Detailed Recommendations

### Recommendation 1: Rewrite All Prompt Templates

**Priority:** 🚨 CRITICAL

**Changes Needed:**

1. **Remove anti-tool instructions:**
   - ❌ "Do NOT create files"
   - ❌ "Do NOT write explanations"
   - ❌ "Your ONLY job is to output valid X"

2. **Add natural, conversational instructions:**
   - ✅ "I need you to create..."
   - ✅ "Please use your Write tool..."
   - ✅ "Make sure to follow these requirements..."

3. **Accept that Claude will explain:**
   - ✅ Allow Claude to think out loud
   - ✅ Claude's explanations help with debugging
   - ✅ The final result is in the files, not the text response

4. **Be explicit about which tools to use:**
   - ✅ "Use the Write tool to create `manifests/task-XXX.manifest.json`"
   - ✅ "Use the Edit tool if you need to modify existing files"
   - ✅ "Use the Read tool to check existing code before editing"

**See:** `corrected_templates/` directory for full implementations.

---

### Recommendation 2: Add File Tracking to ClaudeWrapper

**Priority:** 🟡 HIGH

**Implementation:**

```python
@dataclass
class ClaudeResponse:
    """Response from Claude Code CLI."""
    success: bool
    result: str
    error: str
    session_id: Optional[str] = None
    files_modified: List[str] = None  # NEW: Track modified files

class ClaudeWrapper:
    def _parse_streaming_json_response(self, output: str, elapsed_time: float) -> ClaudeResponse:
        """Parse streaming JSON and track file modifications."""
        lines = output.strip().split("\n")
        result_data = None
        session_id = None
        files_modified = []  # NEW

        for line in lines:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                msg_type = data.get("type", "")

                # NEW: Track tool uses that modify files
                if msg_type == "assistant":
                    content = data.get("message", {}).get("content", [])
                    for item in content:
                        if item.get("type") == "tool_use":
                            tool_name = item.get("name")
                            tool_input = item.get("input", {})

                            # Track Write/Edit/MultiEdit tools
                            if tool_name == "Write" and "file_path" in tool_input:
                                files_modified.append(tool_input["file_path"])
                            elif tool_name == "Edit" and "file_path" in tool_input:
                                if tool_input["file_path"] not in files_modified:
                                    files_modified.append(tool_input["file_path"])
                            elif tool_name == "MultiEdit" and "file_paths" in tool_input:
                                for fp in tool_input["file_paths"]:
                                    if fp not in files_modified:
                                        files_modified.append(fp)

                # ... rest of parsing logic
```

**Benefits:**
- Agents can verify expected files were written
- Enables agent visibility enforcement
- Better error messages when files aren't created

---

### Recommendation 3: Update Agent Response Handling

**Priority:** 🟡 HIGH

**Changes Needed:**

1. **ManifestArchitect.create_manifest():**

```python
def create_manifest(self, goal: str, task_number: int) -> dict:
    """Create manifest from goal description."""
    # Generate manifest using Claude Code
    response = self._generate_manifest_with_claude(goal, task_number)
    if not response.success:
        return self._build_error_response(response.error)

    # Create manifest path
    manifest_path = self._build_manifest_path(goal, task_number)

    # NEW: Verify Claude actually wrote the file
    if response.files_modified and manifest_path not in response.files_modified:
        self.logger.warning(
            f"Claude Code did not write expected file {manifest_path}. "
            f"Files modified: {response.files_modified}"
        )

    # Read the generated manifest from disk
    try:
        with open(manifest_path) as f:
            manifest_data = json.load(f)
    except FileNotFoundError:
        return self._build_error_response(
            f"Manifest file {manifest_path} was not created. "
            f"Claude Code modified: {response.files_modified}. "
            f"Check prompt template and Claude Code's response."
        )
    # ... rest of logic
```

2. **Similar updates for Developer, TestDesigner, etc.**

---

### Recommendation 4: Add Integration Tests

**Priority:** 🟢 MEDIUM

**What to Test:**

1. **End-to-end workflow with mock Claude responses:**
   ```python
   def test_full_workflow_with_mock_responses():
       """Test complete workflow with realistic mock Claude responses."""
       # Mock streaming JSON responses that include tool_use blocks
       mock_responses = {
           "manifest": load_mock_response("manifests/mock_manifest_response.json"),
           "tests": load_mock_response("manifests/mock_test_response.json"),
           "implementation": load_mock_response("manifests/mock_impl_response.json"),
       }

       orchestrator = MAIDOrchestrator(mock_claude_with_responses(mock_responses))
       result = orchestrator.run_full_workflow("Add user authentication")

       assert result.success
       assert Path(result.manifest_path).exists()
   ```

2. **Test prompt template rendering:**
   ```python
   def test_manifest_creation_prompt_has_clear_instructions():
       """Ensure prompt templates are clear and non-contradictory."""
       template_manager = get_template_manager()
       prompt = template_manager.render(
           "manifest_creation",
           goal="Add user authentication",
           task_number="042"
       )

       # Should NOT contain contradictory instructions
       assert "Do NOT create files" not in prompt

       # SHOULD contain clear tool usage instructions
       assert "Write tool" in prompt or "write the file" in prompt.lower()
   ```

---

### Recommendation 5: Improve Agent Visibility Enforcement

**Priority:** 🟢 MEDIUM

**Current State:**
- `--allowedTools` restricts Bash commands (good!)
- No restriction on Read/Write/Edit tools to enforce manifest boundaries

**Proposed Enhancement:**

Add a custom prompt injection that reminds Claude of manifest boundaries:

```python
def _build_manifest_prompt(self, goal: str, task_number: int) -> str:
    """Build prompt with manifest boundary enforcement."""
    template_manager = get_template_manager()
    prompt = template_manager.render(
        "manifest_creation",
        goal=goal,
        task_number=f"{task_number:03d}"
    )

    # Add manifest boundary reminder
    manifest_path = self._build_manifest_path(goal, task_number)
    prompt += f"""

IMPORTANT - File Access Boundaries:
You should ONLY create/read/edit files that are part of this task's scope:
- Create: {manifest_path}
- You may read existing manifests for reference
- Do NOT modify any other files in this phase

This ensures proper isolation and traceability in the MAID methodology.
"""
    return prompt
```

**Note:** This is a soft boundary (relies on Claude following instructions). For hard enforcement, you'd need to:
- Intercept tool calls before execution (requires Claude Code support)
- Or validate files modified after execution and rollback if violations detected

---

### Recommendation 6: Template Versioning

**Priority:** 🟢 LOW

**Issue:** Templates are critical to agent behavior but have no version tracking.

**Proposed Solution:**

1. **Add version headers to templates:**
   ```
   # Template: manifest_creation
   # Version: 2.0.0
   # Last Updated: 2025-01-15
   # MAID Spec: v1.2
   ```

2. **Track template version in manifest:**
   ```json
   {
     "goal": "...",
     "metadata": {
       "templateVersion": "2.0.0",
       "generatedBy": "maid_agents-0.1.0"
     }
   }
   ```

3. **Log warnings when templates are updated:**
   ```python
   CURRENT_TEMPLATE_VERSION = "2.0.0"

   if manifest.get("metadata", {}).get("templateVersion") != CURRENT_TEMPLATE_VERSION:
       logger.warning(
           f"Manifest was generated with template v{old_version}, "
           f"current version is v{CURRENT_TEMPLATE_VERSION}. "
           f"Behavior may differ."
       )
   ```

---

## Implementation Plan

### Phase 1: Fix Critical Issues (Week 1)
1. ✅ Rewrite all prompt templates (see `corrected_templates/`)
2. ✅ Test templates with real Claude Code CLI
3. ✅ Add file tracking to ClaudeWrapper
4. ✅ Update agent response handling

### Phase 2: Testing & Validation (Week 2)
1. Add integration tests with mock responses
2. Test full workflow end-to-end
3. Validate with real Claude Code (manual testing)
4. Update documentation with findings

### Phase 3: Enhancements (Week 3)
1. Agent visibility enforcement
2. Template versioning
3. Better error messages
4. Performance optimizations

---

## Success Criteria

After implementing these recommendations:

1. ✅ Claude Code successfully generates manifests without confusion
2. ✅ Tests are generated that properly USE artifacts
3. ✅ Implementation code is written to correct files
4. ✅ All validations pass (structural + behavioral)
5. ✅ No contradictory instructions in prompts
6. ✅ File tracking shows which files were modified
7. ✅ Integration tests pass with mock responses

---

## Questions for Discussion

1. **Mock vs Real Testing:** Should CI run integration tests with mock Claude responses, or skip them entirely?

2. **Template Migration:** Should old templates be kept for backward compatibility, or is a breaking change acceptable?

3. **Agent Visibility:** Is soft enforcement (instructions) sufficient, or is hard enforcement (validation + rollback) needed?

4. **Error Recovery:** When Claude doesn't create expected files, should agents:
   - Retry with modified prompt?
   - Create files directly as fallback?
   - Fail fast and report to user?

---

## Conclusion

The maid_agents project has a **solid foundation** but needs **prompt engineering improvements** to work reliably with Claude Code CLI. The corrected templates in this directory demonstrate the recommended approach. With these changes, the agents should operate smoothly and predictably.

**Key Principle:** Treat Claude Code as a helpful AI coding assistant that uses tools, not as a code generator that outputs raw text.
