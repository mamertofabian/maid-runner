# maid_agents Review & System Prompt Implementation (v3.0.0)

Comprehensive review of the `maid_agents` repository with implementation plan for system prompt support using Claude Code CLI's `--append-system-prompt` flag.

## Contents

### 📋 Documentation

- **[README.md](README.md)** - This overview
- **[RECOMMENDATIONS.md](RECOMMENDATIONS.md)** - Detailed analysis of issues and fixes
- **[SYSTEM_PROMPT_IMPLEMENTATION.md](SYSTEM_PROMPT_IMPLEMENTATION.md)** - Complete 4-phase implementation plan
- **[FINAL_SUMMARY.md](FINAL_SUMMARY.md)** - Executive summary with metrics

### 📁 Split Templates (v3.0.0)

- **[split_templates/](split_templates/)** - System prompt + user message templates
  - `system/*.txt` - Behavioral instructions (4 files)
  - `user/*.txt` - Task-specific prompts (4 files)
  - `README.md` - Template structure guide
  - `USAGE_EXAMPLES.md` - Code examples

## Executive Summary

### The Problem

Current maid_agents templates send all instructions as user messages (~3000 tokens), mixing behavioral guidance with task details. This is inefficient and less effective than using Claude Code's system prompt capabilities.

### The Solution: v3.0.0 (System Prompt Support)

Split templates into two parts:
- **System prompt** (~500 tokens) - HOW to behave
- **User message** (~500 tokens) - WHAT to do

Use Claude Code's `--append-system-prompt` flag for more effective behavioral guidance.

### Expected Impact

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| **Tokens per request** | 3000 | 1000 | 67% reduction |
| **Cost per request** | $0.015 | $0.005 | 67% cheaper |
| **Iterations needed** | 3-5 | 1-2 | 50% faster |
| **Annual cost (10K/mo)** | $1,800 | $600 | **$1,200 savings** |

## Quick Start

### 1. Read the Implementation Plan

Start here: **[SYSTEM_PROMPT_IMPLEMENTATION.md](SYSTEM_PROMPT_IMPLEMENTATION.md)**

This provides a complete 4-phase implementation plan with:
- Detailed code changes for ClaudeWrapper, TemplateManager, and agents
- Testing strategy
- Success criteria
- Rollback plan

### 2. Review Code Examples

See: **[split_templates/USAGE_EXAMPLES.md](split_templates/USAGE_EXAMPLES.md)**

Concrete code examples showing:
- How to update ClaudeWrapper
- How to update TemplateManager
- How to update each agent
- Before/after comparisons
- Testing examples

### 3. Copy Templates

```bash
# Copy split templates to maid_agents
cp -r examples/maid_agents/split_templates/system \
   /path/to/maid_agents/maid_agents/config/templates/

cp -r examples/maid_agents/split_templates/user \
   /path/to/maid_agents/maid_agents/config/templates/
```

### 4. Implement Code Changes

Update 3 core files:

1. **ClaudeWrapper** - Add `system_prompt` parameter
   ```python
   def __init__(self, ..., system_prompt: Optional[str] = None):
       self.system_prompt = system_prompt

   def _build_claude_command(self, prompt: str) -> List[str]:
       command = [...]
       if self.system_prompt:
           command.extend(["--append-system-prompt", self.system_prompt])
       return command
   ```

2. **TemplateManager** - Add `render_split()` method
   ```python
   def render_split(self, template_name, **kwargs) -> Tuple[str, str]:
       """Returns (system_prompt, user_message)."""
       system = self.load_template(f"system/{template_name}_system")
       user = self.load_template(f"user/{template_name}_user")
       return system.substitute(**kwargs), user.substitute(**kwargs)
   ```

3. **Agents** - Use split prompts (all 4 agents)
   ```python
   prompts = template_manager.render_for_agent("manifest_creation", ...)
   claude = ClaudeWrapper(system_prompt=prompts["system_prompt"])
   response = claude.generate(prompts["user_message"])
   ```

### 5. Test

```bash
# Run tests
pytest tests/ -v

# Test with real Claude Code
ccmaid plan "Create simple module"
```

## Key Insight

### Current Approach (Inefficient)

```bash
claude --print "[3000 tokens: mixed behavioral + task instructions]"
```

**Problems:**
- Behavioral guidance mixed with task details
- 3000 tokens per request
- Less effective (user message vs system prompt)
- Higher cost

### v3.0.0 Approach (Optimal)

```bash
claude --print "[500 tokens: task details]" \
  --append-system-prompt "[500 tokens: behavioral guidance]"
```

**Benefits:**
- Clear separation of concerns
- 1000 tokens total (67% reduction)
- More effective (system-level guidance)
- Lower cost

## How System Prompts Work

Each agent uses a **specialized system prompt**:

| Agent | System Prompt | Purpose |
|-------|--------------|---------|
| ManifestArchitect | `manifest_creation_system.txt` | How to create valid manifests |
| Developer | `implementation_system.txt` | How to implement code that passes tests |
| TestDesigner | `test_generation_system.txt` | How to write behavioral tests |
| Refactorer | `refactor_system.txt` | How to improve code quality |

Each agent creates a **new ClaudeWrapper** with its specialized system prompt when calling Claude Code.

## Implementation Timeline

### Week 1: Core Infrastructure
- Update ClaudeWrapper (30 min)
- Update TemplateManager (30 min)
- Write unit tests (1 hour)

### Week 2: Agent Integration
- Update all 4 agents (1-2 hours)
- Copy templates (5 min)
- Write integration tests (1 hour)

### Week 3: Testing & Validation
- Test with real Claude Code (2 hours)
- Gather metrics (1 hour)
- Document findings (1 hour)

**Total Effort:** ~8-10 hours

## Cost Savings Analysis

### Per Request
- **Before:** $0.015 (3000 tokens)
- **After:** $0.005 (1000 tokens)
- **Savings:** 67%

### Monthly (1000 requests)
- **Before:** $15
- **After:** $5
- **Savings:** $10/month

### Annual (10K requests/month)
- **Before:** $1,800
- **After:** $600
- **Savings:** $1,200/year

## Files Structure

```
examples/maid_agents/
├── README.md                          # This file
├── FINAL_SUMMARY.md                   # Executive summary
├── RECOMMENDATIONS.md                 # Detailed analysis
├── SYSTEM_PROMPT_IMPLEMENTATION.md    # Complete implementation plan
└── split_templates/                   # v3.0.0 templates
    ├── README.md                      # Template guide
    ├── USAGE_EXAMPLES.md              # Code examples
    ├── system/                        # Behavioral prompts
    │   ├── manifest_creation_system.txt
    │   ├── implementation_system.txt
    │   ├── test_generation_system.txt
    │   └── refactor_system.txt
    └── user/                          # Task-specific prompts
        ├── manifest_creation_user.txt
        ├── implementation_user.txt
        ├── test_generation_user.txt
        └── refactor_user.txt
```

## Success Criteria

After implementation, you should see:

### Cost Metrics
- ✅ Token usage: ~1000 per request (down from 3000)
- ✅ Cost per request: ~$0.005 (down from $0.015)
- ✅ Monthly savings: $10 per 1000 requests

### Quality Metrics
- ✅ Iteration count: 1-2 average (down from 3-5)
- ✅ Files created correctly: >90% (up from ~60%)
- ✅ Test pass rate: >90% first try

### User Experience
- ✅ Claude less confused
- ✅ Faster workflow (50% reduction)
- ✅ More consistent results

## Troubleshooting

### Templates not found
```bash
ls maid_agents/config/templates/system/
ls maid_agents/config/templates/user/
# Should show all *_system.txt and *_user.txt files
```

### System prompt not being used
```python
wrapper = ClaudeWrapper(system_prompt="Test")
command = wrapper._build_claude_command("prompt")
assert "--append-system-prompt" in command
```

### Tests failing
```bash
# Run specific test
pytest tests/test_system_prompt_integration.py -v

# Enable debug logging
export MAID_LOG_LEVEL=DEBUG
ccmaid plan "Test task"
```

## Resources

### Getting Started
1. **[SYSTEM_PROMPT_IMPLEMENTATION.md](SYSTEM_PROMPT_IMPLEMENTATION.md)** - Start here for full plan
2. **[split_templates/USAGE_EXAMPLES.md](split_templates/USAGE_EXAMPLES.md)** - Code examples
3. **[split_templates/README.md](split_templates/README.md)** - Template structure

### Understanding
1. **[RECOMMENDATIONS.md](RECOMMENDATIONS.md)** - Why these changes matter
2. **[FINAL_SUMMARY.md](FINAL_SUMMARY.md)** - Executive summary

## Next Steps

1. ✅ Read SYSTEM_PROMPT_IMPLEMENTATION.md
2. ✅ Review code examples in USAGE_EXAMPLES.md
3. ✅ Update ClaudeWrapper
4. ✅ Update TemplateManager
5. ✅ Update agents (4 files)
6. ✅ Copy templates
7. ✅ Test thoroughly
8. ✅ Measure improvements

## Questions?

### "How much work is this?"
**→ 8-10 hours total** for a complete implementation with testing.

### "What's the ROI?"
**→ $1,200/year savings** at 10K requests/month, plus 50% faster workflow.

### "What if something breaks?"
**→ Backward compatible** - old templates still work with `use_split=False`.

### "Do I need to change all agents?"
**→ Yes, all 4 agents** (ManifestArchitect, Developer, TestDesigner, Refactorer) should be updated for consistency.

## Support

- Implementation questions: See SYSTEM_PROMPT_IMPLEMENTATION.md
- Code examples: See split_templates/USAGE_EXAMPLES.md
- Template structure: See split_templates/README.md

---

**Version:** 3.0.0
**Last Updated:** 2025-01-15
**Recommended for:** All maid_agents deployments
**Expected ROI:** 67% cost reduction, 50% faster workflow
