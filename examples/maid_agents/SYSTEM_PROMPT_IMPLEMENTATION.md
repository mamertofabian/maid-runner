# System Prompt Implementation Plan

## Overview

This document provides a detailed plan for implementing system prompt support in maid_agents to make it significantly more effective at working with Claude Code CLI.

## The Core Improvement

**Current State:**
- Entire template (3000+ tokens) sent as user message
- Mixes behavioral instructions with task details
- Fights Claude Code's natural behavior

**Proposed State:**
- Behavioral instructions in system prompt (~500 tokens)
- Task details in user message (~500 tokens)
- Leverages `--append-system-prompt` flag
- 67% reduction in prompt tokens
- **Much more effective guidance**

## Why This Matters

From Claude Code documentation:
> `--append-system-prompt`: Add specific instructions while keeping Claude Code's default capabilities intact. **This is the safest option for most use cases.**

System-level instructions are processed differently than user messages:
- **System prompt**: Guides HOW Claude behaves (persistent, foundational)
- **User message**: Specifies WHAT Claude should do (task-specific, variable)

## Implementation Phases

### Phase 1: Core Infrastructure (Week 1)

#### 1.1: Update ClaudeWrapper

**File:** `maid_agents/claude/cli_wrapper.py`

**Changes:**
```python
# Add system_prompt parameter to __init__
def __init__(
    self,
    mock_mode: bool = True,
    model: str = DEFAULT_MODEL,
    timeout: int = DEFAULT_TIMEOUT,
    temperature: float = DEFAULT_TEMPERATURE,
    system_prompt: Optional[str] = None,  # NEW
) -> None:
    """Initialize Claude wrapper.

    Args:
        mock_mode: If True, returns mock responses without calling Claude
        model: Claude model to use (e.g., "opus")
        timeout: Request timeout in seconds (default: 300)
        temperature: Sampling temperature 0.0-1.0 (default: 0.0)
        system_prompt: Additional system prompt to append (NEW)
    """
    self.mock_mode = mock_mode
    self.model = model
    self.timeout = timeout
    self.temperature = temperature
    self.system_prompt = system_prompt  # NEW
    self.logger = logger
```

```python
# Update _build_claude_command to include system prompt
def _build_claude_command(self, prompt: str) -> List[str]:
    """Build the Claude CLI command with all necessary flags.

    Args:
        prompt: The user message to send to Claude

    Returns:
        List of command arguments
    """
    command = [
        "claude",
        "--print",
        prompt,
        "--model",
        self.model,
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        "acceptEdits",
        "--allowedTools",
        ",".join(self.ALLOWED_TOOLS),
    ]

    # NEW: Add system prompt if provided
    if self.system_prompt:
        command.extend(["--append-system-prompt", self.system_prompt])
        self.logger.debug(f"Using custom system prompt ({len(self.system_prompt)} chars)")

    return command
```

**Testing:**
```python
# tests/test_task_004_claude_cli_wrapper.py
def test_claude_wrapper_with_system_prompt():
    """Test ClaudeWrapper includes system prompt in command."""
    wrapper = ClaudeWrapper(
        mock_mode=True,
        system_prompt="You are a MAID expert."
    )

    command = wrapper._build_claude_command("Create manifest")

    assert "--append-system-prompt" in command
    assert "You are a MAID expert." in command
```

#### 1.2: Update TemplateManager

**File:** `maid_agents/config/template_manager.py`

**Changes:**
```python
from typing import Optional, Dict, Any, Tuple

class TemplateManager:
    """Manages loading and rendering of prompt templates."""

    def __init__(self, templates_dir: Optional[Path] = None):
        """Initialize template manager.

        Args:
            templates_dir: Directory containing template files
        """
        if templates_dir is None:
            templates_dir = Path(__file__).parent / "templates"
        self.templates_dir = Path(templates_dir)

    def load_template(self, template_name: str) -> Template:
        """Load template from file.

        Args:
            template_name: Name of template (without .txt)

        Returns:
            Template object

        Raises:
            FileNotFoundError: If template doesn't exist
        """
        template_path = self.templates_dir / f"{template_name}.txt"
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        content = template_path.read_text(encoding="utf-8")
        return Template(content)

    def render(self, template_name: str, **kwargs: Any) -> str:
        """Render a single template (backward compatible).

        Args:
            template_name: Name of template to render
            **kwargs: Variables to substitute

        Returns:
            Rendered template string
        """
        template = self.load_template(template_name)
        return template.substitute(**kwargs)

    # NEW: Method for split rendering
    def render_split(
        self,
        template_name: str,
        **kwargs: Any
    ) -> Tuple[str, str]:
        """Render template split into system and user prompts.

        This method loads two templates:
        - system/{template_name}_system.txt - Behavioral instructions
        - user/{template_name}_user.txt - Task-specific details

        Args:
            template_name: Base name of template to render
            **kwargs: Variables to substitute in both templates

        Returns:
            Tuple of (system_prompt, user_message)

        Raises:
            FileNotFoundError: If either template doesn't exist

        Example:
            >>> tm = TemplateManager()
            >>> system, user = tm.render_split(
            ...     "manifest_creation",
            ...     goal="Add auth",
            ...     task_number="042"
            ... )
            >>> wrapper = ClaudeWrapper(system_prompt=system)
            >>> response = wrapper.generate(user)
        """
        # Load system prompt template (behavior/constraints)
        system_template = self.load_template(f"system/{template_name}_system")
        system_prompt = system_template.substitute(**kwargs)

        # Load user message template (task-specific)
        user_template = self.load_template(f"user/{template_name}_user")
        user_message = user_template.substitute(**kwargs)

        return system_prompt, user_message

    # NEW: Convenience method for agents
    def render_for_agent(
        self,
        template_name: str,
        use_split: bool = True,
        **kwargs: Any
    ) -> Dict[str, str]:
        """Render template for agent use.

        Args:
            template_name: Name of template to render
            use_split: If True, use split system/user prompts (recommended)
            **kwargs: Variables to substitute

        Returns:
            Dict with 'system_prompt' and 'user_message' keys.
            If use_split=False, 'system_prompt' will be None.

        Example:
            >>> tm = TemplateManager()
            >>> prompts = tm.render_for_agent(
            ...     "manifest_creation",
            ...     goal="Add auth",
            ...     task_number="042"
            ... )
            >>> wrapper = ClaudeWrapper(system_prompt=prompts['system_prompt'])
            >>> response = wrapper.generate(prompts['user_message'])
        """
        if use_split:
            system_prompt, user_message = self.render_split(template_name, **kwargs)
            return {
                "system_prompt": system_prompt,
                "user_message": user_message
            }
        else:
            # Backward compatible: single template
            user_message = self.render(template_name, **kwargs)
            return {
                "system_prompt": None,
                "user_message": user_message
            }


def get_template_manager() -> TemplateManager:
    """Get default template manager instance.

    Returns:
        TemplateManager with default templates directory
    """
    return TemplateManager()
```

**Testing:**
```python
# tests/test_task_014_prompt_templates.py
def test_render_split():
    """Test split rendering of system and user templates."""
    tm = get_template_manager()

    system, user = tm.render_split(
        "manifest_creation",
        goal="Test goal",
        task_number="001"
    )

    # System prompt should have behavioral instructions
    assert "MAID methodology" in system or "CRITICAL CONSTRAINTS" in system
    assert "Write tool" in system

    # User message should have task details
    assert "Test goal" in user
    assert "task-001" in user

    # System prompt should NOT have task details
    assert "Test goal" not in system
```

#### 1.3: Create Template Directory Structure

**New directory layout:**
```
maid_agents/config/templates/
├── system/                          # NEW: System prompts (behavior)
│   ├── manifest_creation_system.txt
│   ├── implementation_system.txt
│   ├── test_generation_system.txt
│   ├── refactor_system.txt
│   └── refine_system.txt
├── user/                            # NEW: User messages (tasks)
│   ├── manifest_creation_user.txt
│   ├── implementation_user.txt
│   ├── test_generation_user.txt
│   ├── refactor_user.txt
│   └── refine_user.txt
└── [legacy templates for backward compat]
    ├── manifest_creation.txt
    ├── implementation.txt
    └── ...
```

### Phase 2: Agent Updates (Week 2)

#### 2.1: Update ManifestArchitect

**File:** `maid_agents/agents/manifest_architect.py`

**Changes:**
```python
def _generate_manifest_with_claude(self, goal: str, task_number: int):
    """Generate manifest using Claude API.

    Args:
        goal: High-level goal description
        task_number: Task number for manifest

    Returns:
        ClaudeResponse object with generation result
    """
    # Get split prompts
    template_manager = get_template_manager()
    prompts = template_manager.render_for_agent(
        "manifest_creation",
        goal=goal,
        task_number=f"{task_number:03d}"
    )

    # Create Claude wrapper with system prompt
    claude_with_system = ClaudeWrapper(
        mock_mode=self.claude.mock_mode,
        model=self.claude.model,
        timeout=self.claude.timeout,
        system_prompt=prompts["system_prompt"]
    )

    self.logger.debug("Calling Claude to generate manifest with MAID system prompt...")
    return claude_with_system.generate(prompts["user_message"])
```

#### 2.2: Update Developer

**File:** `maid_agents/agents/developer.py`

**Changes:**
```python
def _generate_implementation_with_claude(
    self,
    manifest_data: Dict[str, Any],
    test_errors: str
):
    """Generate implementation using Claude API.

    Args:
        manifest_data: Parsed manifest data
        test_errors: Test error output from previous attempts

    Returns:
        ClaudeResponse object with generation result
    """
    template_manager = get_template_manager()

    # Build context for template
    goal = self._get_manifest_goal(manifest_data)
    artifacts_summary = self._build_artifacts_summary(
        manifest_data.get("expectedArtifacts", {})
    )
    files_to_modify_str = self._format_modifiable_files(manifest_data)
    test_output = self._format_test_output(test_errors)
    manifest_filename = self._generate_manifest_filename(goal)

    # Get split prompts
    prompts = template_manager.render_for_agent(
        "implementation",
        manifest_path=manifest_filename,
        goal=goal,
        test_output=test_output,
        artifacts_summary=artifacts_summary,
        files_to_modify=files_to_modify_str
    )

    # Create Claude wrapper with system prompt
    claude_with_system = ClaudeWrapper(
        mock_mode=self.claude.mock_mode,
        model=self.claude.model,
        timeout=self.claude.timeout,
        system_prompt=prompts["system_prompt"]
    )

    return claude_with_system.generate(prompts["user_message"])
```

#### 2.3: Update TestDesigner

**File:** `maid_agents/agents/test_designer.py`

Similar pattern to Developer.

#### 2.4: Update Refactorer

**File:** `maid_agents/agents/refactorer.py`

Similar pattern to Developer.

### Phase 3: Template Creation (Week 2-3)

Create all split templates (see separate files in `split_templates/` directory).

Each template pair should follow this pattern:

**System Prompt** (`system/{name}_system.txt`):
- MAID methodology principles
- Tool usage requirements
- File access boundaries
- Code quality standards
- Error handling approaches
- Validation rules

**User Message** (`user/{name}_user.txt`):
- Specific task goal
- Task number/identifier
- Files to modify
- Current state (e.g., test failures)
- Expected artifacts for THIS task
- Focused examples

### Phase 4: Testing & Validation (Week 3)

#### 4.1: Unit Tests

**New tests:**
```python
# tests/test_system_prompt_integration.py
def test_manifest_architect_uses_system_prompt():
    """Test ManifestArchitect uses system prompt correctly."""
    mock_claude = ClaudeWrapper(mock_mode=True)
    architect = ManifestArchitect(mock_claude)

    # Spy on ClaudeWrapper creation
    with patch('maid_agents.agents.manifest_architect.ClaudeWrapper') as mock_wrapper:
        architect.create_manifest("Test goal", 1)

        # Verify system prompt was passed
        call_args = mock_wrapper.call_args
        assert call_args[1]['system_prompt'] is not None
        assert "MAID" in call_args[1]['system_prompt']

def test_split_templates_exist():
    """Test all split templates exist."""
    tm = get_template_manager()
    agents = ["manifest_creation", "implementation", "test_generation", "refactor"]

    for agent in agents:
        # Should not raise FileNotFoundError
        system, user = tm.render_split(agent, goal="Test", task_number="001")
        assert len(system) > 100
        assert len(user) > 100
```

#### 4.2: Integration Tests

```python
def test_full_workflow_with_system_prompts():
    """Test complete workflow uses system prompts."""
    orchestrator = MAIDOrchestrator(dry_run=True)

    # Mock Claude responses
    with patch('maid_agents.claude.cli_wrapper.ClaudeWrapper.generate') as mock_gen:
        mock_gen.return_value = ClaudeResponse(
            success=True,
            result="Success",
            error="",
            session_id="test-123"
        )

        result = orchestrator.run_planning_loop("Test goal")

        # Verify system prompts were used
        calls = mock_gen.call_args_list
        # Check that ClaudeWrapper instances had system_prompt set
        # (implementation details depend on how we track this)
```

#### 4.3: Manual Testing with Real Claude Code

```bash
# Test with actual Claude Code CLI
cd /path/to/maid_agents

# Enable verbose logging to see system prompt being used
export MAID_LOG_LEVEL=DEBUG

# Test manifest creation
ccmaid plan "Create a simple calculator module" --max-iterations 2

# Check logs for system prompt usage
# Should see: "Using custom system prompt (XXX chars)"
```

### Phase 5: Documentation & Migration (Week 4)

#### 5.1: Update Documentation

**Files to update:**
- `README.md` - Mention system prompt feature
- `CLAUDE.md` - Document template structure
- `docs/architecture.md` - Explain system/user split
- `IMPLEMENTATION_SUMMARY.md` - Add to feature list

#### 5.2: Migration Guide

**For users:**
```markdown
# Migrating to System Prompt Templates

## What Changed
Templates are now split into:
- System prompts (behavior) in `templates/system/`
- User messages (tasks) in `templates/user/`

## Benefits
- 67% fewer tokens per request
- More effective behavioral guidance
- Better Claude Code integration

## Backward Compatibility
Old single-file templates still work via `render()` method.
New split templates use `render_split()` or `render_for_agent()`.

## Migration Steps
1. Update to v0.2.0+
2. Templates automatically use split mode
3. No code changes needed (handled internally)
```

#### 5.3: Template Versioning

Add version tracking:
```python
# In template files
# Template: manifest_creation_system
# Version: 3.0.0
# Type: system
# MAID Spec: v1.2

# Template: manifest_creation_user
# Version: 3.0.0
# Type: user
# MAID Spec: v1.2
```

## Success Criteria

### Must Have (Phase 1-2)
- ✅ ClaudeWrapper accepts `system_prompt` parameter
- ✅ `--append-system-prompt` included in commands
- ✅ TemplateManager has `render_split()` method
- ✅ All agents updated to use split prompts
- ✅ Unit tests pass

### Should Have (Phase 3)
- ✅ All split templates created
- ✅ System prompts are ~500 tokens each
- ✅ User messages are ~500 tokens each
- ✅ Integration tests pass
- ✅ Manual testing with real Claude Code succeeds

### Nice to Have (Phase 4)
- ✅ Template versioning system
- ✅ Migration guide for users
- ✅ Performance benchmarks (token usage)
- ✅ A/B testing results (v2 vs v3 templates)

## Expected Impact

### Token Efficiency
- **Before:** 3000 tokens average per prompt
- **After:** 1000 tokens average (system + user)
- **Savings:** 67% reduction

### Cost Reduction
- **Before:** ~$0.015 per manifest creation (3K tokens × $5/M)
- **After:** ~$0.005 per manifest creation (1K tokens × $5/M)
- **Savings:** 67% cost reduction

### Quality Improvement
- **Before:** Variable quality, frequent iterations
- **After:** More consistent, fewer iterations needed
- **Expected:** 30-50% reduction in iteration count

### User Experience
- **Before:** 3-5 iterations average to get valid manifest
- **After:** 1-2 iterations average
- **Expected:** 50% faster workflow

## Rollout Strategy

### Week 1: Infrastructure
- Implement ClaudeWrapper changes
- Implement TemplateManager changes
- Create directory structure
- Write unit tests

### Week 2: Agent Integration
- Update all 5 agents (ManifestArchitect, Developer, TestDesigner, Refactorer, Refiner)
- Write integration tests
- Test with mock mode

### Week 3: Template Creation & Testing
- Create all split templates
- Manual testing with real Claude Code
- Gather metrics (tokens, cost, iterations)
- A/B testing if possible

### Week 4: Documentation & Release
- Update all documentation
- Create migration guide
- Release as v0.2.0 with changelog
- Announce improvements

## Rollback Plan

If issues arise:

1. **Immediate rollback:**
   ```python
   # In agents, temporarily disable split mode
   prompts = template_manager.render_for_agent(
       "manifest_creation",
       use_split=False,  # Use old templates
       goal=goal,
       task_number=task_number
   )
   ```

2. **Feature flag:**
   ```python
   USE_SPLIT_TEMPLATES = os.getenv("MAID_USE_SPLIT_TEMPLATES", "true") == "true"

   if USE_SPLIT_TEMPLATES:
       prompts = template_manager.render_for_agent(...)
   else:
       # Use old approach
       prompt = template_manager.render(...)
   ```

3. **Full rollback:**
   - Keep old templates in place
   - Agents fall back to single-template mode
   - No breaking changes

## Risks & Mitigations

### Risk: System prompt doesn't work as expected
**Mitigation:** Test extensively with real Claude Code before release. Collect metrics on iteration count and success rate.

### Risk: Split templates are harder to maintain
**Mitigation:** Clear documentation, template versioning, automated tests to ensure both parts stay in sync.

### Risk: Backward compatibility breaks
**Mitigation:** Keep old templates, use feature flag, gradual rollout with opt-in period.

### Risk: Users don't see the benefit
**Mitigation:** Document improvements with metrics, provide before/after examples, highlight cost savings.

## Next Steps

1. **Review this plan** - Get feedback from team
2. **Create manifest** - Follow MAID methodology for this change
3. **Create tests** - Write tests before implementation
4. **Implement Phase 1** - Start with core infrastructure
5. **Iterate** - Test, refine, improve

---

**Plan Version:** 1.0.0
**Author:** Claude Code Review
**Date:** 2025-01-15
**Status:** PROPOSED
