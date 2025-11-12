# Split Templates Usage Examples

This document shows concrete code examples for implementing system prompt support in maid_agents.

## Table of Contents

1. [ClaudeWrapper Updates](#claudewrapper-updates)
2. [TemplateManager Updates](#templatemanager-updates)
3. [Agent Updates](#agent-updates)
4. [Testing Examples](#testing-examples)
5. [Command Line Examples](#command-line-examples)

---

## ClaudeWrapper Updates

### Before (v2.0.0)

```python
# maid_agents/claude/cli_wrapper.py
class ClaudeWrapper:
    def __init__(
        self,
        mock_mode: bool = True,
        model: str = DEFAULT_MODEL,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.mock_mode = mock_mode
        self.model = model
        self.timeout = timeout

    def _build_claude_command(self, prompt: str) -> List[str]:
        return [
            "claude",
            "--print",
            prompt,
            "--model", self.model,
            "--output-format", "stream-json",
            "--verbose",
        ]
```

### After (v3.0.0)

```python
# maid_agents/claude/cli_wrapper.py
class ClaudeWrapper:
    def __init__(
        self,
        mock_mode: bool = True,
        model: str = DEFAULT_MODEL,
        timeout: int = DEFAULT_TIMEOUT,
        system_prompt: Optional[str] = None,  # NEW
    ) -> None:
        self.mock_mode = mock_mode
        self.model = model
        self.timeout = timeout
        self.system_prompt = system_prompt  # NEW
        self.logger = logger

    def _build_claude_command(self, prompt: str) -> List[str]:
        """Build Claude CLI command with system prompt support."""
        command = [
            "claude",
            "--print",
            prompt,
            "--model", self.model,
            "--output-format", "stream-json",
            "--verbose",
            "--permission-mode", "acceptEdits",
            "--allowedTools", ",".join(self.ALLOWED_TOOLS),
        ]

        # NEW: Add system prompt if provided
        if self.system_prompt:
            command.extend(["--append-system-prompt", self.system_prompt])
            self.logger.debug(
                f"Using custom system prompt ({len(self.system_prompt)} chars)"
            )

        return command
```

**Key Changes:**
- Added `system_prompt` parameter to `__init__`
- Check if `system_prompt` is set
- Append `--append-system-prompt` flag with value
- Log system prompt usage for debugging

---

## TemplateManager Updates

### Before (v2.0.0)

```python
# maid_agents/config/template_manager.py
class TemplateManager:
    def render(self, template_name: str, **kwargs: Any) -> str:
        """Render a single template."""
        template = self.load_template(template_name)
        return template.substitute(**kwargs)
```

### After (v3.0.0)

```python
# maid_agents/config/template_manager.py
from typing import Dict, Any, Tuple, Optional

class TemplateManager:
    def render(self, template_name: str, **kwargs: Any) -> str:
        """Render a single template (backward compatible)."""
        template = self.load_template(template_name)
        return template.substitute(**kwargs)

    def render_split(
        self, template_name: str, **kwargs: Any
    ) -> Tuple[str, str]:
        """Render template split into system and user prompts.

        Args:
            template_name: Base name of template
            **kwargs: Variables to substitute

        Returns:
            Tuple of (system_prompt, user_message)

        Example:
            >>> tm = TemplateManager()
            >>> system, user = tm.render_split(
            ...     "manifest_creation",
            ...     goal="Add auth",
            ...     task_number="042"
            ... )
        """
        # Load system prompt (behavioral instructions)
        system_template = self.load_template(f"system/{template_name}_system")
        system_prompt = system_template.substitute(**kwargs)

        # Load user message (task-specific details)
        user_template = self.load_template(f"user/{template_name}_user")
        user_message = user_template.substitute(**kwargs)

        return system_prompt, user_message

    def render_for_agent(
        self,
        template_name: str,
        use_split: bool = True,
        **kwargs: Any
    ) -> Dict[str, str]:
        """Render template for agent use.

        Args:
            template_name: Name of template
            use_split: If True, use split system/user prompts
            **kwargs: Variables to substitute

        Returns:
            Dict with 'system_prompt' and 'user_message' keys

        Example:
            >>> tm = TemplateManager()
            >>> prompts = tm.render_for_agent(
            ...     "implementation",
            ...     goal="Add auth",
            ...     manifest_path="manifests/task-042.json"
            ... )
            >>> wrapper = ClaudeWrapper(system_prompt=prompts['system_prompt'])
            >>> response = wrapper.generate(prompts['user_message'])
        """
        if use_split:
            system_prompt, user_message = self.render_split(
                template_name, **kwargs
            )
            return {
                "system_prompt": system_prompt,
                "user_message": user_message
            }
        else:
            # Backward compatible
            user_message = self.render(template_name, **kwargs)
            return {
                "system_prompt": None,
                "user_message": user_message
            }
```

**Key Changes:**
- Added `render_split()` for split templates
- Added `render_for_agent()` convenience method
- Backward compatible with old `render()` method
- Returns dict with clear keys

---

## Agent Updates

### ManifestArchitect

#### Before (v2.0.0)

```python
# maid_agents/agents/manifest_architect.py
class ManifestArchitect(BaseAgent):
    def _generate_manifest_with_claude(self, goal: str, task_number: int):
        """Generate manifest using Claude."""
        # Build single large prompt
        prompt = self._build_manifest_prompt(goal, task_number)

        # Call Claude with entire prompt as user message
        return self.claude.generate(prompt)

    def _build_manifest_prompt(self, goal: str, task_number: int) -> str:
        """Build prompt from template."""
        template_manager = get_template_manager()
        return template_manager.render(
            "manifest_creation",
            goal=goal,
            task_number=f"{task_number:03d}"
        )
```

#### After (v3.0.0)

```python
# maid_agents/agents/manifest_architect.py
class ManifestArchitect(BaseAgent):
    def _generate_manifest_with_claude(self, goal: str, task_number: int):
        """Generate manifest using split prompts."""
        template_manager = get_template_manager()

        # Get split prompts
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
            system_prompt=prompts["system_prompt"]  # Behavioral guidance
        )

        self.logger.debug("Calling Claude with MAID system prompt...")
        return claude_with_system.generate(prompts["user_message"])
```

**Key Changes:**
- Use `render_for_agent()` to get split prompts
- Create new `ClaudeWrapper` with `system_prompt`
- Pass only user message to `generate()`
- System prompt goes through CLI flag

### Developer

#### Before (v2.0.0)

```python
# maid_agents/agents/developer.py
class Developer(BaseAgent):
    def implement(self, manifest_path: str, test_errors: str = "") -> dict:
        """Implement code to pass tests."""
        manifest_data = self._load_manifest(manifest_path)

        # Build large prompt
        prompt = self._build_implementation_prompt(manifest_data, test_errors)

        # Call Claude
        response = self.claude.generate(prompt)

        if not response.success:
            return self._create_error_response(response.error)

        # ... rest of implementation
```

#### After (v3.0.0)

```python
# maid_agents/agents/developer.py
class Developer(BaseAgent):
    def implement(self, manifest_path: str, test_errors: str = "") -> dict:
        """Implement code to pass tests using split prompts."""
        manifest_data = self._load_manifest(manifest_path)

        # Build context for templates
        goal = self._get_manifest_goal(manifest_data)
        artifacts = self._build_artifacts_summary(
            manifest_data.get("expectedArtifacts", {})
        )
        files = self._format_modifiable_files(manifest_data)

        # Get split prompts
        template_manager = get_template_manager()
        prompts = template_manager.render_for_agent(
            "implementation",
            manifest_path=manifest_path,
            goal=goal,
            test_output=test_errors,
            artifacts_summary=artifacts,
            files_to_modify=files
        )

        # Create wrapper with system prompt
        claude_with_system = ClaudeWrapper(
            mock_mode=self.claude.mock_mode,
            model=self.claude.model,
            timeout=self.claude.timeout,
            system_prompt=prompts["system_prompt"]
        )

        # Generate with user message
        response = claude_with_system.generate(prompts["user_message"])

        if not response.success:
            return self._create_error_response(response.error)

        # ... rest of implementation
```

**Key Changes:**
- Build all context variables
- Use `render_for_agent()` with all variables
- Create new wrapper with system prompt
- Generate with user message only

### TestDesigner

```python
# maid_agents/agents/test_designer.py
class TestDesigner(BaseAgent):
    def generate_tests(self, manifest_path: str) -> dict:
        """Generate behavioral tests using split prompts."""
        manifest_data = self._load_manifest(manifest_path)

        # Extract variables
        goal = manifest_data.get("goal", "")
        artifacts = self._build_artifacts_summary(
            manifest_data.get("expectedArtifacts", {})
        )
        files_to_test = self._get_files_to_test(manifest_data)
        test_file_path = self._generate_test_file_path(manifest_data)

        # Get split prompts
        template_manager = get_template_manager()
        prompts = template_manager.render_for_agent(
            "test_generation",
            manifest_path=manifest_path,
            goal=goal,
            artifacts_summary=artifacts,
            files_to_test=files_to_test,
            test_file_path=test_file_path
        )

        # Create wrapper with system prompt
        claude_with_system = ClaudeWrapper(
            mock_mode=self.claude.mock_mode,
            model=self.claude.model,
            timeout=self.claude.timeout,
            system_prompt=prompts["system_prompt"]
        )

        return claude_with_system.generate(prompts["user_message"])
```

---

## Testing Examples

### Unit Tests

```python
# tests/test_claude_wrapper.py
def test_claude_wrapper_with_system_prompt():
    """Test ClaudeWrapper includes system prompt in command."""
    wrapper = ClaudeWrapper(
        mock_mode=True,
        system_prompt="You are a MAID expert."
    )

    command = wrapper._build_claude_command("Create manifest")

    assert "--append-system-prompt" in command
    idx = command.index("--append-system-prompt")
    assert command[idx + 1] == "You are a MAID expert."


def test_claude_wrapper_without_system_prompt():
    """Test ClaudeWrapper works without system prompt."""
    wrapper = ClaudeWrapper(mock_mode=True)

    command = wrapper._build_claude_command("Create manifest")

    assert "--append-system-prompt" not in command


# tests/test_template_manager.py
def test_render_split():
    """Test split rendering of system and user templates."""
    tm = get_template_manager()

    system, user = tm.render_split(
        "manifest_creation",
        goal="Test goal",
        task_number="001"
    )

    # System prompt has behavioral instructions
    assert "CRITICAL CONSTRAINTS" in system
    assert "Write tool" in system
    assert len(system) > 100

    # User message has task details
    assert "Test goal" in user
    assert "task-001" in user
    assert len(user) > 100

    # No overlap of concerns
    assert "Test goal" not in system


def test_render_for_agent():
    """Test render_for_agent convenience method."""
    tm = get_template_manager()

    prompts = tm.render_for_agent(
        "manifest_creation",
        goal="Test",
        task_number="001"
    )

    assert "system_prompt" in prompts
    assert "user_message" in prompts
    assert prompts["system_prompt"] is not None
    assert prompts["user_message"] is not None


def test_render_for_agent_backward_compat():
    """Test render_for_agent with use_split=False."""
    tm = get_template_manager()

    prompts = tm.render_for_agent(
        "manifest_creation",
        use_split=False,
        goal="Test",
        task_number="001"
    )

    assert prompts["system_prompt"] is None
    assert prompts["user_message"] is not None
```

### Integration Tests

```python
# tests/test_system_prompt_integration.py
from unittest.mock import patch, MagicMock

def test_manifest_architect_uses_system_prompt():
    """Test ManifestArchitect passes system prompt to Claude."""
    mock_claude = MagicMock()
    architect = ManifestArchitect(mock_claude)

    # Spy on ClaudeWrapper creation
    with patch('maid_agents.agents.manifest_architect.ClaudeWrapper') as MockWrapper:
        mock_instance = MagicMock()
        mock_instance.generate.return_value = ClaudeResponse(
            success=True,
            result="Success",
            error=""
        )
        MockWrapper.return_value = mock_instance

        architect.create_manifest("Test goal", 1)

        # Verify ClaudeWrapper was created with system_prompt
        MockWrapper.assert_called_once()
        call_kwargs = MockWrapper.call_args[1]

        assert 'system_prompt' in call_kwargs
        assert call_kwargs['system_prompt'] is not None
        assert "MAID" in call_kwargs['system_prompt']


def test_developer_uses_system_prompt():
    """Test Developer passes system prompt to Claude."""
    mock_claude = MagicMock()
    developer = Developer(mock_claude)

    # Create minimal manifest
    manifest = {
        "goal": "Test",
        "creatableFiles": ["test.py"],
        "expectedArtifacts": {"file": "test.py", "contains": []}
    }

    with patch('maid_agents.agents.developer.ClaudeWrapper') as MockWrapper:
        mock_instance = MagicMock()
        mock_instance.generate.return_value = ClaudeResponse(
            success=True,
            result="Success",
            error=""
        )
        MockWrapper.return_value = mock_instance

        with patch.object(developer, '_load_manifest', return_value=manifest):
            developer.implement("manifests/test.json", "Test errors")

        # Verify system prompt was used
        call_kwargs = MockWrapper.call_args[1]
        assert 'system_prompt' in call_kwargs
        assert call_kwargs['system_prompt'] is not None
```

---

## Command Line Examples

### With System Prompt (v3.0.0)

```bash
# The ClaudeWrapper will build this command:
claude --print "Create MAID manifest for: Add user authentication" \
  --model opus \
  --output-format stream-json \
  --verbose \
  --permission-mode acceptEdits \
  --allowedTools "Bash(pytest:*),Bash(maid validate:*)" \
  --append-system-prompt "You are helping with MAID methodology.

CRITICAL CONSTRAINTS:
- ALWAYS use your Write tool to create files
- Match manifest signatures EXACTLY
- Only access files within boundaries
[... 500 more chars of behavioral guidance ...]"
```

**Result:**
- System prompt: ~500 tokens (behavioral guidance)
- User message: ~500 tokens (task details)
- Total: ~1000 tokens

### Without System Prompt (v2.0.0)

```bash
# Old approach - all in user message
claude --print "You are a JSON generator. Do NOT create files.
[... 2500 more chars of mixed instructions and task details ...]
CRITICAL: Use your file editing tools to create files.
Goal: Add user authentication
[... more details ...]" \
  --model opus \
  --output-format stream-json
```

**Result:**
- User message: ~3000 tokens (everything mixed)
- Total: ~3000 tokens

---

## Quick Migration Checklist

### Phase 1: Core Infrastructure

- [ ] Update `ClaudeWrapper.__init__` to accept `system_prompt`
- [ ] Update `_build_claude_command` to use `--append-system-prompt`
- [ ] Add `render_split()` to `TemplateManager`
- [ ] Add `render_for_agent()` to `TemplateManager`
- [ ] Write unit tests for both

### Phase 2: Templates

- [ ] Copy split templates to `templates/system/` and `templates/user/`
- [ ] Verify all templates render without errors
- [ ] Test variable substitution works

### Phase 3: Agents

- [ ] Update `ManifestArchitect._generate_manifest_with_claude`
- [ ] Update `Developer.implement`
- [ ] Update `TestDesigner.generate_tests`
- [ ] Update `Refactorer.refactor`
- [ ] Write integration tests

### Phase 4: Testing

- [ ] Run all unit tests
- [ ] Run all integration tests
- [ ] Test with real Claude Code CLI
- [ ] Measure token usage and cost
- [ ] Compare iteration counts (v2 vs v3)

### Phase 5: Documentation

- [ ] Update README.md
- [ ] Update CLAUDE.md
- [ ] Create migration guide
- [ ] Update examples

---

## Troubleshooting Examples

### Debug Logging

```python
# Enable debug logging to see system prompts
import logging
logging.basicConfig(level=logging.DEBUG)

# Run agent
architect = ManifestArchitect(ClaudeWrapper(mock_mode=False))
result = architect.create_manifest("Test goal", 1)

# You should see in logs:
# DEBUG: Using custom system prompt (523 chars)
# DEBUG: Calling Claude with MAID system prompt...
```

### Verify Command Building

```python
# Check the command that will be executed
wrapper = ClaudeWrapper(
    mock_mode=False,
    system_prompt="MAID constraints..."
)

command = wrapper._build_claude_command("Create manifest")
print(" ".join(command))

# Should output:
# claude --print Create manifest --model opus --output-format stream-json
# --verbose --permission-mode acceptEdits --allowedTools Bash(pytest:*),...
# --append-system-prompt MAID constraints...
```

### Template Rendering Debug

```python
# Debug template rendering
tm = get_template_manager()

try:
    system, user = tm.render_split(
        "manifest_creation",
        goal="Test",
        task_number="001"
    )
    print(f"System prompt: {len(system)} chars")
    print(f"User message: {len(user)} chars")
    print(f"\nSystem preview:\n{system[:200]}...")
    print(f"\nUser preview:\n{user[:200]}...")
except Exception as e:
    print(f"Error: {e}")
    # Check if templates exist
    import os
    print(f"System template exists: {os.path.exists('templates/system/manifest_creation_system.txt')}")
    print(f"User template exists: {os.path.exists('templates/user/manifest_creation_user.txt')}")
```

---

## Performance Comparison

### Token Usage

```python
# Measure token usage (approximate)
from maid_agents.config.template_manager import get_template_manager

tm = get_template_manager()

# Old way (v2.0.0)
old_prompt = tm.render(
    "manifest_creation",
    use_split=False,
    goal="Add user authentication",
    task_number="042"
)
old_tokens = len(old_prompt) // 4  # Rough estimate

# New way (v3.0.0)
system, user = tm.render_split(
    "manifest_creation",
    goal="Add user authentication",
    task_number="042"
)
new_tokens = (len(system) + len(user)) // 4

print(f"Old approach: ~{old_tokens} tokens")
print(f"New approach: ~{new_tokens} tokens")
print(f"Savings: {100 * (1 - new_tokens/old_tokens):.1f}%")

# Expected output:
# Old approach: ~750 tokens
# New approach: ~250 tokens
# Savings: 66.7%
```

### Cost Comparison

```python
# Calculate cost savings
COST_PER_MILLION_TOKENS = 5.00  # $5 per 1M tokens (example)

old_cost = (old_tokens / 1_000_000) * COST_PER_MILLION_TOKENS
new_cost = (new_tokens / 1_000_000) * COST_PER_MILLION_TOKENS

print(f"Old cost per request: ${old_cost:.4f}")
print(f"New cost per request: ${new_cost:.4f}")
print(f"Savings: ${old_cost - new_cost:.4f} per request")

# For 1000 requests:
print(f"\nFor 1000 requests:")
print(f"Old total: ${old_cost * 1000:.2f}")
print(f"New total: ${new_cost * 1000:.2f}")
print(f"Savings: ${(old_cost - new_cost) * 1000:.2f}")
```

---

## See Also

- `SYSTEM_PROMPT_IMPLEMENTATION.md` - Full implementation plan
- `README.md` - Template structure and usage
- `../RECOMMENDATIONS.md` - Original recommendations
- `../COMPARISON.md` - v1 vs v2 comparison

---

**Version:** 1.0.0
**Last Updated:** 2025-01-15
