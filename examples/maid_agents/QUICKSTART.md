# Quick Start: Applying Template Improvements

This guide helps you quickly apply the corrected templates to the maid_agents project.

## 5-Minute Quick Fix

### Step 1: Copy Templates (2 minutes)

```bash
# From maid-runner repository
cd /path/to/maid-runner

# Copy corrected templates to maid_agents repository
cp examples/maid_agents/corrected_templates/*.txt \
   /path/to/maid_agents/maid_agents/config/templates/
```

### Step 2: Verify Installation (1 minute)

```bash
# Check templates were copied
ls /path/to/maid_agents/maid_agents/config/templates/

# Should show:
# manifest_creation.txt
# implementation.txt
# test_generation.txt
# refactor.txt
# (and possibly others like refine.txt, test_generation_from_implementation.txt)
```

### Step 3: Test with Mock Mode (2 minutes)

```bash
cd /path/to/maid_agents

# Test planning with mock mode (no real API calls)
ccmaid --mock plan "Add user authentication feature"

# Should complete without errors
# Check if manifest was "created" (in mock mode it won't actually write)
```

### Step 4: Test with Real Claude Code (Optional)

```bash
# Test with actual Claude Code CLI
ccmaid plan "Create a simple calculator module" --max-iterations 5

# Verify manifest was created
ls manifests/
```

---

## Conservative Approach (Side-by-Side Testing)

If you want to test both versions before committing:

### Step 1: Create Templates V2 Directory

```bash
cd /path/to/maid_agents

# Create backup and v2 directory
cp -r maid_agents/config/templates maid_agents/config/templates_v1
mkdir maid_agents/config/templates_v2
```

### Step 2: Copy Corrected Templates to V2

```bash
cp /path/to/maid-runner/examples/maid_agents/corrected_templates/*.txt \
   maid_agents/config/templates_v2/
```

### Step 3: Update TemplateManager for A/B Testing

Edit `maid_agents/config/template_manager.py`:

```python
from pathlib import Path
from string import Template
from typing import Optional
import os

class TemplateManager:
    """Manages loading and rendering of prompt templates."""

    def __init__(self, templates_dir: Optional[Path] = None, version: str = "v1"):
        """Initialize template manager.

        Args:
            templates_dir: Directory containing template files
            version: Template version to use ("v1" or "v2")
        """
        if templates_dir is None:
            base_dir = Path(__file__).parent
            # Check environment variable for version override
            version = os.getenv("MAID_TEMPLATE_VERSION", version)
            templates_dir = base_dir / f"templates_{version}"

            # Fallback to original templates if v2 doesn't exist
            if not templates_dir.exists():
                templates_dir = base_dir / "templates"

        self.templates_dir = Path(templates_dir)
        self.version = version

    # ... rest of class
```

### Step 4: Test Both Versions

```bash
# Test with original templates (v1)
MAID_TEMPLATE_VERSION=v1 ccmaid --mock plan "Add authentication"

# Test with corrected templates (v2)
MAID_TEMPLATE_VERSION=v2 ccmaid --mock plan "Add authentication"

# Compare results
diff manifests/task-*-v1.manifest.json manifests/task-*-v2.manifest.json
```

---

## Validation Checklist

After applying templates, verify:

- [ ] Templates are in correct directory
- [ ] No syntax errors in template files
- [ ] Mock mode works: `ccmaid --mock plan "Test task"`
- [ ] Templates render without errors
- [ ] No contradictory instructions in rendered prompts
- [ ] File paths are clearly specified
- [ ] Tool usage instructions are present

### Quick Validation Script

```python
#!/usr/bin/env python3
"""Validate corrected templates."""

from pathlib import Path
from maid_agents.config.template_manager import get_template_manager

def validate_templates():
    """Check templates for common issues."""
    tm = get_template_manager()
    templates = ["manifest_creation", "implementation", "test_generation", "refactor"]

    issues = []

    for template_name in templates:
        try:
            prompt = tm.render(
                template_name,
                goal="Test goal",
                task_number="001",
                manifest_path="test.json",
                test_output="test output",
                artifacts_summary="test artifacts",
                files_to_modify="test files",
                files_to_test="test files",
                test_file_path="test.py",
                files_to_refactor="test files",
                test_file="test.py"
            )

            # Check for contradictions
            if "Do NOT create files" in prompt and "file editing tools" in prompt:
                issues.append(f"{template_name}: Contradictory file creation instructions")

            # Check for tool instructions
            if "Write tool" not in prompt and "Edit tool" not in prompt:
                issues.append(f"{template_name}: Missing tool usage instructions")

            # Check for code generator language
            if "You are a" in prompt and "generator" in prompt.lower():
                issues.append(f"{template_name}: Still uses 'generator' language")

            print(f"✓ {template_name}: Renders successfully")

        except Exception as e:
            issues.append(f"{template_name}: Failed to render - {e}")

    if issues:
        print("\n⚠️  Issues found:")
        for issue in issues:
            print(f"  - {issue}")
        return False
    else:
        print("\n✅ All templates validated successfully!")
        return True

if __name__ == "__main__":
    import sys
    success = validate_templates()
    sys.exit(0 if success else 1)
```

Run validation:
```bash
cd /path/to/maid_agents
python scripts/validate_templates.py
```

---

## Troubleshooting

### Issue: Templates not found

**Symptom:** `FileNotFoundError: Template not found`

**Solution:**
```bash
# Check templates directory exists
ls maid_agents/config/templates/

# Verify template files are there
ls maid_agents/config/templates/*.txt

# If missing, copy again from corrected_templates/
```

### Issue: Import errors

**Symptom:** `ModuleNotFoundError: No module named 'maid_agents'`

**Solution:**
```bash
# Reinstall package
cd /path/to/maid_agents
uv pip install -e .

# Or use make command
make install
```

### Issue: Templates render but Claude still confused

**Symptom:** Claude asks clarifying questions or doesn't create files

**Solution:**
```bash
# 1. Verify you're using corrected templates
grep "Template: manifest_creation" maid_agents/config/templates/manifest_creation.txt

# Should show "# Template: manifest_creation" at top

# 2. Check rendered prompt
python -c "
from maid_agents.config.template_manager import get_template_manager
tm = get_template_manager()
print(tm.render('manifest_creation', goal='Test', task_number='001'))
" | head -20

# Should NOT contain "Do NOT create files"
```

### Issue: Tests failing after template update

**Symptom:** Tests that expect specific prompt content fail

**Solution:**
```bash
# Update test expectations to match new template format
# Example:
# Old: assert "You are a JSON generator" in prompt
# New: assert "I need you to create" in prompt

# Run tests to find failures
pytest tests/ -v --tb=short

# Update affected tests
```

---

## Rollback Plan

If you need to revert to original templates:

### Quick Rollback

```bash
cd /path/to/maid_agents

# If you made backup
cp maid_agents/config/templates_v1/*.txt maid_agents/config/templates/

# Or restore from git
git checkout maid_agents/config/templates/
```

### Verify Rollback

```bash
# Check original templates are restored
grep "You are a JSON generator" maid_agents/config/templates/manifest_creation.txt

# Should find the line (it's in original but not in corrected)
```

---

## Next Steps

After applying templates:

1. **Test with Mock Mode**
   ```bash
   ccmaid --mock plan "Simple test task"
   ```

2. **Test with Real Claude Code**
   ```bash
   ccmaid plan "Create a simple utility module"
   ```

3. **Monitor First Few Tasks**
   - Check if manifests are created correctly
   - Verify tests are generated properly
   - Watch for any errors or unexpected behavior

4. **Provide Feedback**
   - Document any issues encountered
   - Note improvements in agent behavior
   - Share findings with the team

5. **Update Documentation**
   - Add template version to CLAUDE.md
   - Update README with template information
   - Note any behavior changes

---

## Success Criteria

You'll know the templates are working well when:

- ✅ Manifests are created without errors
- ✅ Claude uses Write/Edit tools as expected
- ✅ Files are created in correct locations
- ✅ No "file not found" errors
- ✅ Fewer iterations needed to get valid output
- ✅ Claude doesn't ask unnecessary clarifying questions
- ✅ Generated code matches manifest specifications

---

## Getting Help

If you encounter issues:

1. **Check the comparison**: Read `COMPARISON.md` to understand what changed
2. **Review recommendations**: See `RECOMMENDATIONS.md` for implementation details
3. **Validate templates**: Run validation script to check for issues
4. **Test in isolation**: Test each template individually with mock mode
5. **Check examples**: Review `corrected_templates/README.md` for usage examples

---

**Quick Reference:**

- **Templates location**: `maid_agents/config/templates/`
- **Source**: `maid-runner/examples/maid_agents/corrected_templates/`
- **Documentation**: `maid-runner/examples/maid_agents/RECOMMENDATIONS.md`
- **Version**: 2.0.0
- **Compatible with**: MAID v1.2

**Ready to apply?** Start with the 5-Minute Quick Fix above!
