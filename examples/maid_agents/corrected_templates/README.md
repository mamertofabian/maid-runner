# Corrected Prompt Templates for maid_agents

This directory contains improved prompt templates designed to work correctly with Claude Code CLI's actual behavior.

## What's Different?

The original templates in `maid_agents/maid_agents/config/templates/` treated Claude Code as a **code generator** that outputs raw JSON/Python. This approach has several problems:

1. **Contradictory instructions** - "Do NOT create files" followed by "Use your file editing tools"
2. **Wrong assumptions** - Expecting raw code output instead of tool-based file creation
3. **Confusing tone** - Commands ("Do NOT") instead of collaborative requests
4. **Missing context** - No explanation of why or how to complete the task

## The Corrected Approach

These templates treat Claude Code as an **interactive AI coding assistant** that:
- Uses tools (Write, Edit, Read) to create/modify files
- Explains its approach before and after working
- Returns conversational responses, not raw code
- Works collaboratively rather than as a code generator

### Key Improvements

✅ **Conversational tone**: "I need you to..." instead of "You are a generator"
✅ **Clear tool instructions**: "Use your Write tool to create..."
✅ **No contradictions**: Removed "Do NOT create files" + "Create files"
✅ **Better examples**: Real code examples with proper context
✅ **Accepts explanations**: Claude can (and will) explain its approach
✅ **File tracking**: Instructions to use specific tools for traceability

## Template Files

### 1. `manifest_creation.txt`
**Purpose:** Generate MAID manifests from high-level goals

**Key Changes:**
- Removed "Do NOT create files" instruction
- Added explicit "Use your Write tool to create manifests/task-XXX.manifest.json"
- Conversational request format
- Better examples from maid_agents codebase
- File access boundaries clearly defined

**Usage:**
```python
template_manager.render(
    "manifest_creation",
    goal="Add user authentication to the API",
    task_number="042"
)
```

### 2. `implementation.txt`
**Purpose:** Generate implementation code to pass behavioral tests

**Key Changes:**
- Removed "Do NOT write explanations" instruction
- Added explicit "Use your Edit/Write tools to modify these files"
- Encourages reading tests to understand requirements
- Better error handling patterns
- More code examples with proper structure

**Usage:**
```python
template_manager.render(
    "implementation",
    manifest_path="manifests/task-042-user-auth.manifest.json",
    goal="Add user authentication to the API",
    test_output="<pytest output>",
    artifacts_summary="<formatted artifacts>",
    files_to_modify="<formatted file list>"
)
```

### 3. `test_generation.txt`
**Purpose:** Generate behavioral tests from manifest artifacts

**Key Changes:**
- Focus on testing artifact USAGE, not implementation
- Clear instructions on existence, signature, and behavior tests
- Better pytest examples with mocking
- Edge case and error handling test patterns
- Keyword argument usage to verify parameter names

**Usage:**
```python
template_manager.render(
    "test_generation",
    manifest_path="manifests/task-042-user-auth.manifest.json",
    goal="Add user authentication to the API",
    artifacts_summary="<formatted artifacts>",
    files_to_test="<formatted file list>",
    test_file_path="tests/test_task_042_user_auth.py"
)
```

### 4. `refactor.txt`
**Purpose:** Improve code quality while maintaining behavior

**Key Changes:**
- Clear refactoring patterns (Extract Method, Better Names, etc.)
- Examples of before/after code
- Explicit "Don't change public API" instructions
- Refactoring checklist
- Real examples from maid_agents codebase

**Usage:**
```python
template_manager.render(
    "refactor",
    manifest_path="manifests/task-042-user-auth.manifest.json",
    goal="Improve code quality in authentication module",
    files_to_refactor="<formatted file list>",
    test_file="tests/test_task_042_user_auth.py"
)
```

## How to Use These Templates

### Option 1: Direct Replacement

Replace the templates in `maid_agents/maid_agents/config/templates/`:

```bash
# Backup original templates
cp -r maid_agents/maid_agents/config/templates maid_agents/maid_agents/config/templates.backup

# Copy corrected templates
cp corrected_templates/*.txt maid_agents/maid_agents/config/templates/
```

### Option 2: Side-by-Side Testing

Keep both versions and test with a feature flag:

```python
# In template_manager.py
class TemplateManager:
    def __init__(self, templates_dir: Optional[Path] = None, use_v2: bool = False):
        if templates_dir is None:
            base_dir = Path(__file__).parent / "templates"
            templates_dir = base_dir if not use_v2 else base_dir.parent / "templates_v2"
        self.templates_dir = Path(templates_dir)
```

### Option 3: A/B Testing

Run the same task with both template versions and compare results:

```python
# Test with original templates
orchestrator_v1 = MAIDOrchestrator(template_version="v1")
result_v1 = orchestrator_v1.run_planning_loop("Add user auth")

# Test with corrected templates
orchestrator_v2 = MAIDOrchestrator(template_version="v2")
result_v2 = orchestrator_v2.run_planning_loop("Add user auth")

# Compare quality of generated manifests
```

## Expected Improvements

With these corrected templates, you should see:

1. **Fewer clarifying questions** - Claude understands what to do
2. **Files actually created** - No "file not found" errors
3. **Better manifest quality** - More complete and accurate
4. **Working implementations** - Code that actually passes tests
5. **Smoother workflow** - Less iteration needed

## Template Versioning

These templates are marked as **Version 2.0.0** with headers:

```
# Template: manifest_creation
# Version: 2.0.0
# MAID Spec: v1.2
```

Consider tracking template versions in manifests:

```json
{
  "goal": "...",
  "metadata": {
    "templateVersion": "2.0.0",
    "generatedBy": "maid_agents-0.2.0"
  }
}
```

## Testing Recommendations

### Unit Tests for Templates

Add tests to verify templates render correctly:

```python
def test_manifest_creation_template_renders():
    """Test manifest creation template renders without errors."""
    template_manager = get_template_manager(use_v2=True)
    prompt = template_manager.render(
        "manifest_creation",
        goal="Test goal",
        task_number="001"
    )

    # Should not contain contradictory instructions
    assert "Do NOT create files" not in prompt

    # Should contain clear tool instructions
    assert "Write tool" in prompt or "write the file" in prompt.lower()
```

### Integration Tests with Mock Responses

Test full workflow with realistic mock Claude responses:

```python
def test_planning_loop_with_v2_templates():
    """Test planning loop with v2 templates produces valid manifest."""
    # Create mock Claude that returns realistic streaming JSON
    mock_responses = load_mock_streaming_responses()
    orchestrator = MAIDOrchestrator(
        claude=mock_claude(mock_responses),
        template_version="v2"
    )

    result = orchestrator.run_planning_loop("Add user authentication")

    assert result["success"]
    assert Path(result["manifest_path"]).exists()

    # Validate manifest quality
    with open(result["manifest_path"]) as f:
        manifest = json.load(f)
        assert "goal" in manifest
        assert "expectedArtifacts" in manifest
```

### Manual Testing with Real Claude Code

Test templates with actual Claude Code CLI:

```bash
# Export prompt to file
python -c "
from maid_agents.config.template_manager import get_template_manager
tm = get_template_manager(use_v2=True)
prompt = tm.render('manifest_creation', goal='Add user auth', task_number='999')
print(prompt)
" > test_prompt.txt

# Run with Claude Code
claude --print "$(cat test_prompt.txt)" --model opus --output-format stream-json

# Verify manifest was created
ls manifests/task-999-*.manifest.json
```

## Common Issues and Solutions

### Issue: Claude still outputs JSON as text

**Cause:** Template still has contradictory instructions or unclear tool usage
**Solution:** Check template for "Do NOT create files" or missing tool instructions

### Issue: Files not created in expected location

**Cause:** Template doesn't specify exact file path
**Solution:** Add explicit path: "Use your Write tool to create `exact/path/to/file.py`"

### Issue: Claude asks clarifying questions

**Cause:** Instructions are ambiguous or contradictory
**Solution:** Review template for clarity, remove contradictions

### Issue: Generated code doesn't match manifest

**Cause:** Template doesn't emphasize matching manifest signatures exactly
**Solution:** Add more emphasis on "match EXACTLY" with examples

## Migration Guide

### Step 1: Backup Current Templates
```bash
cp -r maid_agents/maid_agents/config/templates templates.backup
```

### Step 2: Copy Corrected Templates
```bash
cp corrected_templates/*.txt maid_agents/maid_agents/config/templates/
```

### Step 3: Update Template Manager (Optional)
Add version tracking:
```python
# In template_manager.py
TEMPLATE_VERSION = "2.0.0"
```

### Step 4: Run Tests
```bash
pytest tests/ -v
```

### Step 5: Test with Real Claude Code
```bash
ccmaid --mock plan "Test task"  # Should work smoothly
```

### Step 6: Update Documentation
Update CLAUDE.md with template version information.

## Contributing

If you improve these templates further:

1. Update the version number
2. Document changes in template header comments
3. Add examples of improvements
4. Test with real Claude Code CLI
5. Submit feedback or pull request

## Questions?

See `../RECOMMENDATIONS.md` for detailed rationale and implementation guidance.

---

**Version:** 2.0.0
**Last Updated:** 2025-01-15
**Compatible with:** MAID v1.2, Claude Code CLI latest
