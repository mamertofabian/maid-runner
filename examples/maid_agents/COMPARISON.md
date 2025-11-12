# Template Comparison: Original vs Corrected

This document shows side-by-side comparisons of the original and corrected templates to highlight the key improvements.

## Manifest Creation Template

### Original Opening (Lines 1-16)

```text
You are a JSON generator. Your ONLY job is to output valid JSON.
Do NOT write explanations, do NOT use markdown, do NOT create files.

TASK: Generate a MAID v1.2 manifest JSON for task-${task_number}

GOAL: ${goal}

REQUIREMENTS:
1. Determine task type (create/edit/refactor)
2. List files to touch (creatableFiles vs editableFiles)
...

CRITICAL: Your response must be ONLY the raw JSON object.
No markdown, no explanation, no code fences.
```

**Problems:**
- ❌ Commands Claude to "Do NOT create files"
- ❌ Demands "ONLY raw JSON output"
- ❌ Forbids explanations
- ❌ Treats Claude as a dumb code generator

### Corrected Opening

```text
# Template: manifest_creation
# Version: 2.0.0
# MAID Spec: v1.2

I need you to create a MAID v1.2 manifest for the following task:

**Task Number:** task-${task_number}
**Goal:** ${goal}

## Your Task

Create a complete MAID manifest file that defines this task.
Use your **Write tool** to create the manifest at:
`manifests/task-${task_number}-[slug].manifest.json`

(Generate an appropriate slug from the goal for the filename)
```

**Improvements:**
- ✅ Conversational request: "I need you to..."
- ✅ Clear tool instruction: "Use your Write tool"
- ✅ Specific file path with explanation
- ✅ Treats Claude as an AI assistant

---

### Original Closing (Lines 108-118)

```text
OUTPUT INSTRUCTIONS:
Return ONLY the JSON object. No markdown code fences,
no explanation text, no commentary.
Start your response with { and end with }

CRITICAL: Use your file editing tools to directly create this manifest file:
- {manifest_path}

- Write the complete JSON manifest to the file listed above
- Make all changes directly using your file editing capabilities
- Do not just show the JSON - actually write the file
```

**Problems:**
- ❌ **Contradictory!** First says "Return ONLY JSON", then says "Use file editing tools"
- ❌ Confusing: What should Claude actually do?
- ❌ The file path variable isn't even defined here

### Corrected Closing

```text
## File Access Boundaries

For this task, you should:
- **Create:** The manifest file at `manifests/task-${task_number}-[slug].manifest.json`
- **Read (optional):** Existing manifests for reference if needed
- **Do NOT modify:** Any other files in this phase

This ensures proper isolation and traceability in the MAID methodology.

## Next Steps

1. Analyze the goal and determine the appropriate task type
2. Identify which files need to be created or modified
3. List all public artifacts that will be created
4. Use your Write tool to create the manifest JSON file
5. Confirm the file was created successfully

Please proceed with creating the manifest!
```

**Improvements:**
- ✅ Clear boundaries for file access
- ✅ Step-by-step guidance
- ✅ No contradiction - consistently expects file creation
- ✅ Polite request to proceed

---

## Implementation Template

### Original Opening (Lines 1-21)

```text
You are a Python code generator. Your ONLY job is to output valid Python implementation code.
Do NOT write explanations outside of code comments.

TASK: Implement code to make failing tests pass

MANIFEST: ${manifest_path}
GOAL: ${goal}

TEST FAILURES:
${test_output}

EXPECTED ARTIFACTS (must match manifest exactly):
${artifacts_summary}

FILES TO MODIFY:
${files_to_modify}

REQUIREMENTS:
1. Make ALL tests pass
...

CRITICAL: Your response must be ONLY Python code.
```

**Problems:**
- ❌ "Do NOT write explanations"
- ❌ "Your response must be ONLY Python code"
- ❌ Commands rather than requests
- ❌ Doesn't mention using tools

### Corrected Opening

```text
# Template: implementation
# Version: 2.0.0
# MAID Spec: v1.2

I need you to implement code to make the failing tests pass for this task.

## Task Context

**Manifest:** ${manifest_path}
**Goal:** ${goal}

## Test Failures

The current test output is:
```
${test_output}
```

## Expected Artifacts

According to the manifest, you need to implement these artifacts
with **exact signatures**:

${artifacts_summary}

## Files to Modify

You should use your file editing tools to modify these files:

${files_to_modify}
```

**Improvements:**
- ✅ "I need you to..." - conversational
- ✅ Mentions "file editing tools"
- ✅ Structured with clear sections
- ✅ Expects Claude to explain approach

---

### Original Closing (Lines 211-220)

```text
OUTPUT INSTRUCTIONS:
Return ONLY Python code for the file being created/modified.
Include complete file content with:
1. Module docstring
2. All necessary imports
3. All class/function implementations
4. Proper docstrings and type hints

No markdown code fences in your response, no explanation text before or after code.

CRITICAL: Use your file editing tools to directly write/update these files:
{files_list}
```

**Problems:**
- ❌ Again contradictory: "Return ONLY Python code" then "Use file editing tools"
- ❌ Confusion about whether to output code or use tools
- ❌ Commands tone

### Corrected Closing

```text
## File Access Boundaries

For this implementation phase, you should:
- **Read:** Test files, manifest, and any readonly files listed
- **Write/Edit:** Only files listed in `creatableFiles` or `editableFiles`
- **Do NOT modify:** Test files or files not listed in the manifest

This ensures proper isolation and traceability in the MAID methodology.

## Next Steps

1. Review the test failures to understand what's expected
2. Read the test file if you need more context
3. Implement the code to match manifest signatures exactly
4. Use your Write or Edit tools to create/modify the necessary files
5. Ensure all type hints and docstrings are included

Please proceed with the implementation!
```

**Improvements:**
- ✅ Clear file access boundaries
- ✅ Explicit tool usage instructions
- ✅ Step-by-step guidance
- ✅ No contradiction about output vs tools

---

## Test Generation Template

### Original Opening (Lines 1-14)

```text
You are a pytest test code generator. Your ONLY job is to output valid pytest test code.
Do NOT write explanations outside of code comments.

TASK: Generate behavioral tests that verify manifest artifacts

MANIFEST: ${manifest_path}
GOAL: ${goal}

EXPECTED ARTIFACTS TO TEST:
${artifacts_summary}

CRITICAL: Your response must be ONLY pytest test code.
No markdown, no explanation, just Python test functions.
```

**Problems:**
- ❌ "Do NOT write explanations"
- ❌ "Your response must be ONLY pytest test code"
- ❌ Doesn't mention Write tool
- ❌ Generator mindset instead of assistant

### Corrected Opening

```text
# Template: test_generation
# Version: 2.0.0
# MAID Spec: v1.2

I need you to create behavioral tests that verify the artifacts
defined in a MAID manifest.

## Task Context

**Manifest Path:** ${manifest_path}
**Goal:** ${goal}

## Expected Artifacts to Test

The manifest declares these artifacts that your tests must verify:

${artifacts_summary}

## Files Context

**Files being tested:** ${files_to_test}
**Test file to create:** ${test_file_path}

## Your Task

Create comprehensive behavioral tests that verify:
1. **Artifact existence** - Classes, functions, methods exist
2. **Artifact signatures** - Parameters and return types match manifest
3. **Artifact behavior** - Implementation works correctly

Use your **Write tool** to create the test file at: `${test_file_path}`
```

**Improvements:**
- ✅ Collaborative request
- ✅ Clear tool instruction
- ✅ Structured explanation
- ✅ Three-part testing approach (existence, signatures, behavior)

---

## Key Differences Summary

| Aspect | Original Templates | Corrected Templates |
|--------|-------------------|---------------------|
| **Tone** | Commands ("Do NOT") | Requests ("I need you to") |
| **Tool Usage** | Contradictory or absent | Clear and consistent |
| **Output Expectations** | Raw code/JSON | Files created via tools |
| **Explanations** | Forbidden | Accepted and encouraged |
| **Structure** | Walls of text | Clear sections with headers |
| **Examples** | Generic patterns | Real code from maid_agents |
| **Boundaries** | Unclear | Explicit file access rules |
| **Claude's Role** | Dumb generator | AI coding assistant |
| **Versioning** | None | Version headers |

---

## Why These Changes Matter

### 1. Claude Code Uses Tools

Claude Code doesn't output raw code - it uses Write, Edit, and Read tools to work with files. The original templates fight against this behavior.

**Original:** "Do NOT create files" → Confuses Claude
**Corrected:** "Use your Write tool to create..." → Aligns with Claude's behavior

### 2. Claude Explains Its Approach

Claude Code naturally explains what it's doing. Forbidding explanations creates confusion and may cause Claude to:
- Ask clarifying questions
- Ignore the instruction
- Produce lower quality work (no reasoning process)

**Original:** "Do NOT write explanations"
**Corrected:** Accepts that Claude will explain (response text is separate from file content)

### 3. Contradictions Cause Failures

When templates say "output raw JSON" AND "use file editing tools", Claude must choose one. Different Claude versions may choose differently, causing inconsistent behavior.

**Original:** Two contradictory instructions
**Corrected:** Single clear instruction

### 4. Examples Ground Expectations

Generic examples don't show Claude what "good" looks like in this specific codebase.

**Original:** Generic examples
**Corrected:** Real examples from maid_agents with actual patterns used

### 5. Structure Improves Understanding

Wall-of-text prompts are hard to parse. Clear sections with headers help Claude understand what's important.

**Original:** Dense paragraphs
**Corrected:** Markdown sections with headers

---

## Migration Impact

### Expected Behavior Changes

**Before (Original Templates):**
- 🔴 Claude often confused by contradictory instructions
- 🔴 Frequently outputs JSON/code as text instead of using tools
- 🔴 May ask clarifying questions or refuse to proceed
- 🔴 Files not created as expected
- 🔴 Need multiple iterations to get correct behavior

**After (Corrected Templates):**
- ✅ Claude understands task clearly
- ✅ Uses Write/Edit tools to create files
- ✅ Files created in expected locations
- ✅ Fewer iterations needed
- ✅ Better quality output

### Validation Changes

Original agent code expects files to exist (correct), but templates don't align with this expectation. With corrected templates:

```python
# This check should now work reliably
try:
    with open(manifest_path) as f:
        manifest_data = json.load(f)
except FileNotFoundError:
    # This should rarely happen now
    return error_response(...)
```

---

## Testing the Difference

### Test Script

```python
#!/usr/bin/env python3
"""Compare original vs corrected templates."""

from maid_agents.config.template_manager import get_template_manager

# Test with original template
tm_old = get_template_manager()  # Uses original templates
prompt_old = tm_old.render("manifest_creation", goal="Test", task_number="001")

# Test with corrected template
tm_new = get_template_manager(templates_dir="corrected_templates")
prompt_new = tm_new.render("manifest_creation", goal="Test", task_number="001")

# Compare
print("=== ORIGINAL TEMPLATE ===")
print(prompt_old[:500])
print("\n=== CORRECTED TEMPLATE ===")
print(prompt_new[:500])

# Check for contradictions
has_contradiction_old = (
    "Do NOT create files" in prompt_old and
    "file editing tools" in prompt_old
)
has_contradiction_new = (
    "Do NOT create files" in prompt_new and
    "file editing tools" in prompt_new
)

print(f"\nOriginal has contradiction: {has_contradiction_old}")
print(f"Corrected has contradiction: {has_contradiction_new}")
```

### Expected Output

```
=== ORIGINAL TEMPLATE ===
You are a JSON generator. Your ONLY job is to output valid JSON.
Do NOT write explanations, do NOT use markdown, do NOT create files.
...

=== CORRECTED TEMPLATE ===
# Template: manifest_creation
# Version: 2.0.0

I need you to create a MAID v1.2 manifest for the following task:
...

Original has contradiction: True
Corrected has contradiction: False
```

---

## Conclusion

The corrected templates fundamentally change how agents interact with Claude Code:

| Original | Corrected |
|----------|-----------|
| Fight Claude's nature | Work with Claude's nature |
| Contradictory instructions | Clear, consistent instructions |
| Commands and demands | Collaborative requests |
| Hope for raw output | Expect tool usage |
| Generic examples | Domain-specific examples |

**Result:** More reliable agent behavior, fewer iterations, better output quality.

---

**See also:**
- `RECOMMENDATIONS.md` - Detailed recommendations for maid_agents improvements
- `corrected_templates/README.md` - How to use the corrected templates
