📋 IMPLEMENTATION PLAN: MAID Runner MCP Server

🎯 Project Overview

Repository: maid-runner-mcp
Purpose: Expose MAID Runner validation tools via Model Context Protocol (MCP) for seamless
  integration with AI agents and development tools.

Core Value Proposition:
- Replace subprocess-based MAID CLI invocations with structured MCP tool calls
- Enable AI agents (Claude, GPT-4, etc.) to use MAID validation natively
- Provide discoverable tools, resources, and prompts for MAID workflow
- Maintain tool-agnostic philosophy while adding protocol-based access

---
📚 Background Research Summary

Model Context Protocol (MCP)

- Architecture: Client-server protocol using JSON-RPC 2.0
- Transports: stdio (default), SSE, WebSocket
- Components: Tools (executable functions), Resources (data exposure), Prompts
(interaction templates)
- Python SDK: mcp package with FastMCP for rapid server development
- Official Spec: High reputation, 92.7 benchmark score for Python SDK

MAID Runner

- Philosophy: Validation-only, tool-agnostic framework
- CLI Commands: validate, snapshot, test, manifests, init, generate-stubs, schema
- Core Features: Schema validation, AST-based implementation checking, manifest chain
merging, file tracking analysis
- Current Integration: Subprocess calls from external tools (Claude Code, Aider, etc.)
- Future Plans: LSP server (v1.3), VS Code extension, enhanced reporting

---
🏗️ Architecture Design

┌─────────────────────────────────────────────────────────────┐
│                    AI Agent / MCP Client                     │
│              (Claude Code, Aider, Custom Agents)             │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ MCP Protocol (JSON-RPC 2.0)
                              │ stdio / SSE / WebSocket
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    maid-runner-mcp Server                    │
│                                                              │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐           │
│  │   Tools    │  │ Resources  │  │  Prompts   │           │
│  ├────────────┤  ├────────────┤  ├────────────┤           │
│  │ validate   │  │ manifests  │  │ plan-task  │           │
│  │ snapshot   │  │ validation │  │ implement  │           │
│  │ test       │  │ schema     │  │ refactor   │           │
│  │ manifests  │  │ file-track │  │ review     │           │
│  │ init       │  │            │  │            │           │
│  └────────────┘  └────────────┘  └────────────┘           │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ Python API / CLI
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     MAID Runner Core                         │
│              (maid-runner Python package)                    │
└─────────────────────────────────────────────────────────────┘

---
🛠️ Tool Design

1. maid_validate Tool

Purpose: Validate manifests against implementation or behavioral tests

Input Schema:
{
  "type": "object",
  "properties": {
    "manifest_path": {
      "type": "string",
      "description": "Path to manifest JSON file (relative or absolute)"
    },
    "validation_mode": {
      "type": "string",
      "enum": ["implementation", "behavioral"],
      "default": "implementation",
      "description": "Validation mode: implementation checks definitions, behavioral 
checks usage"
    },
    "use_manifest_chain": {
      "type": "boolean",
      "default": false,
      "description": "Use manifest chain to merge related manifests"
    },
    "manifest_dir": {
      "type": "string",
      "description": "Directory containing manifests to validate all at once (mutually 
exclusive with manifest_path)"
    },
    "quiet": {
      "type": "boolean",
      "default": false,
      "description": "Suppress success messages"
    }
  },
  "required": ["manifest_path"]
}

Output Schema:
{
  "type": "object",
  "properties": {
    "success": {"type": "boolean"},
    "mode": {"type": "string"},
    "manifest": {"type": "string"},
    "target_file": {"type": "string"},
    "used_chain": {"type": "boolean"},
    "errors": {
      "type": "array",
      "items": {"type": "string"}
    },
    "file_tracking": {
      "type": "object",
      "properties": {
        "undeclared": {"type": "array"},
        "registered": {"type": "array"},
        "tracked": {"type": "array"}
      }
    }
  }
}

Implementation:
- Call maid_runner.cli.validate.run_validation() directly
- Parse output and structure as JSON
- Handle exit codes and error messages

---
2. maid_snapshot Tool

Purpose: Generate snapshot manifest from existing Python code

Input Schema:
{
  "type": "object",
  "properties": {
    "file_path": {
      "type": "string",
      "description": "Path to Python file to snapshot"
    },
    "output_dir": {
      "type": "string",
      "default": "manifests",
      "description": "Directory to write manifest"
    },
    "force": {
      "type": "boolean",
      "default": false,
      "description": "Overwrite existing manifests without prompting"
    },
    "skip_test_stub": {
      "type": "boolean",
      "default": false,
      "description": "Skip test stub generation"
    }
  },
  "required": ["file_path"]
}

Output Schema:
{
  "type": "object",
  "properties": {
    "success": {"type": "boolean"},
    "manifest_path": {"type": "string"},
    "test_stub_path": {"type": "string"},
    "superseded_manifests": {
      "type": "array",
      "items": {"type": "string"}
    },
    "errors": {
      "type": "array",
      "items": {"type": "string"}
    }
  }
}

---
3. maid_test Tool

Purpose: Run validation commands from manifests

Input Schema:
{
  "type": "object",
  "properties": {
    "manifest_dir": {
      "type": "string",
      "default": "manifests",
      "description": "Directory containing manifests"
    },
    "manifest": {
      "type": "string",
      "description": "Run validation for single manifest (filename or path)"
    },
    "fail_fast": {
      "type": "boolean",
      "default": false,
      "description": "Stop on first failure"
    },
    "timeout": {
      "type": "integer",
      "default": 300,
      "description": "Command timeout in seconds"
    }
  }
}

Output Schema:
{
  "type": "object",
  "properties": {
    "success": {"type": "boolean"},
    "total_manifests": {"type": "integer"},
    "passed": {"type": "integer"},
    "failed": {"type": "integer"},
    "failed_manifests": {
      "type": "array",
      "items": {"type": "string"}
    },
    "results": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "manifest": {"type": "string"},
          "success": {"type": "boolean"},
          "output": {"type": "string"},
          "duration_ms": {"type": "number"}
        }
      }
    }
  }
}

---
4. maid_list_manifests Tool

Purpose: List manifests that reference a file

Input Schema:
{
  "type": "object",
  "properties": {
    "file_path": {
      "type": "string",
      "description": "Path to file to search for in manifests"
    },
    "manifest_dir": {
      "type": "string",
      "default": "manifests",
      "description": "Directory containing manifests"
    }
  },
  "required": ["file_path"]
}

Output Schema:
{
  "type": "object",
  "properties": {
    "file_path": {"type": "string"},
    "total_manifests": {"type": "integer"},
    "created_by": {"type": "array", "items": {"type": "string"}},
    "edited_by": {"type": "array", "items": {"type": "string"}},
    "read_by": {"type": "array", "items": {"type": "string"}}
  }
}

---
5. maid_init Tool

Purpose: Initialize MAID methodology in a repository

Input Schema:
{
  "type": "object",
  "properties": {
    "target_dir": {
      "type": "string",
      "default": ".",
      "description": "Target directory to initialize"
    },
    "force": {
      "type": "boolean",
      "default": false,
      "description": "Overwrite existing files without prompting"
    }
  }
}

---
6. maid_get_schema Tool

Purpose: Get the manifest JSON schema

Input Schema: None (no parameters)

Output Schema:
{
  "type": "object",
  "properties": {
    "schema": {"type": "object"}
  }
}

---
📦 Resource Design

1. manifest:// Resource

Purpose: Access manifest files as resources

URI Template: manifest://{manifest_name}

Example URIs:
- manifest://task-013-email-validation
- manifest://task-042-snapshot-system

Content Type: application/json

Implementation:
- List all manifests in manifests/ directory
- Return manifest content as JSON
- Support discovery via list_resources()

---
2. validation:// Resource

Purpose: Access validation results as resources

URI Template: validation://{manifest_name}/result

Content: Cached validation results (structured JSON)

Use Case: AI agents can review previous validation results without re-running

---
3. schema://manifest Resource

Purpose: Expose manifest JSON schema

URI: schema://manifest

Content: The manifest.schema.json file

---
4. file-tracking:// Resource

Purpose: Expose file tracking analysis results

URI: file-tracking://analysis

Content: Current file tracking status (undeclared, registered, tracked)

---
💬 Prompt Design

1. plan-task Prompt

Purpose: Guide AI in creating a new MAID task manifest

Arguments:
- goal (required): Task description
- file_path (optional): Target file for task
- task_type (optional): create, edit, refactor, snapshot

Template:
You are creating a MAID task manifest for: {goal}

Follow the MAID Planning Loop (Phase 2):
1. Draft the manifest (primary contract)
2. Draft behavioral tests (support the manifest)
3. Validate structure: maid_validate --validation-mode behavioral
4. Iterate until validation passes

Manifest Structure:
- goal: Clear task description
- taskType: {task_type}
- creatableFiles: New files (strict validation)
- editableFiles: Existing files (permissive validation)
- readonlyFiles: Dependencies and tests
- expectedArtifacts: Public API contract
- validationCommand: Test command

Remember:
- The manifest is the PRIMARY CONTRACT
- Tests support implementation and verify behavior
- Use maid_get_schema for schema reference
- Validate with maid_validate before proceeding

---
2. implement-task Prompt

Purpose: Guide AI in implementing code from manifest

Arguments:
- manifest_path (required): Path to manifest

Template:
You are implementing: {manifest_path}

Follow the MAID Implementation Loop (Phase 3):
1. Read manifest to load only specified files
2. Implement code based on expectedArtifacts
3. Validate: maid_validate {manifest_path} --use-manifest-chain
4. Run tests: Execute validationCommand
5. Iterate until all tests pass

Key Principles:
- Load ONLY files from manifest (editableFiles + readonlyFiles)
- Public artifacts must match expectedArtifacts exactly (creatableFiles)
- Public artifacts must contain expectedArtifacts at minimum (editableFiles)
- Private artifacts (_prefix) are optional

Validation Flow:
1. Schema validation (manifest structure)
2. Behavioral validation (tests USE artifacts)
3. Implementation validation (code DEFINES artifacts)

Use maid_validate to check progress.

---
3. refactor-code Prompt

Purpose: Guide AI in refactoring while maintaining manifest compliance

Arguments:
- file_path (required): File to refactor
- goal (required): Refactoring goal

Template:
You are refactoring: {file_path}
Goal: {goal}

MAID Refactoring Workflow:
1. Find existing manifests: maid_list_manifests {file_path}
2. Create snapshot: maid_snapshot {file_path}
3. Create refactoring manifest (supersedes snapshot)
4. Refactor code
5. Validate: maid_validate --use-manifest-chain
6. Ensure all tests pass

Critical Rules:
- DO NOT break public API contracts
- Maintain all expectedArtifacts from previous manifests
- Use supersedes to update manifest chain
- Run maid_validate after each change

Refactoring is safe when validation passes with --use-manifest-chain.

---
4. review-manifest Prompt

Purpose: Guide AI in reviewing manifest quality

Arguments:
- manifest_path (required): Manifest to review

Template:
Review this manifest for MAID compliance: {manifest_path}

Review Checklist:
1. Schema Compliance:
    - Valid JSON structure
    - All required fields present
    - Correct artifact types

2. MAID Principles:
    - Goal is clear and specific
    - Extreme isolation (minimal files touched)
    - Explicit context (all dependencies in readonlyFiles)
    - Test-driven (validationCommand present)

3. Artifact Quality:
    - Public artifacts explicitly declared
    - Type hints included where possible
    - Methods include class context
    - Parameters properly specified

4. Validation Coverage:
    - Tests exercise all expectedArtifacts
    - validationCommand is comprehensive

Use maid_validate to verify compliance.
Provide specific recommendations for improvement.

---
📁 Project Structure

maid-runner-mcp/
├── README.md                      # Project documentation
├── LICENSE                        # MIT License
├── pyproject.toml                 # Project configuration
├── uv.lock                        # Dependency lock file
├── .gitignore                     # Git ignore rules
│
├── src/
│   └── maid_runner_mcp/
│       ├── __init__.py            # Package initialization
│       ├── __version__.py         # Version info
│       ├── server.py              # Main MCP server (FastMCP)
│       ├── tools/                 # Tool implementations
│       │   ├── __init__.py
│       │   ├── validate.py        # maid_validate tool
│       │   ├── snapshot.py        # maid_snapshot tool
│       │   ├── test.py            # maid_test tool
│       │   ├── manifests.py       # maid_list_manifests tool
│       │   ├── init.py            # maid_init tool
│       │   └── schema.py          # maid_get_schema tool
│       ├── resources/             # Resource implementations
│       │   ├── __init__.py
│       │   ├── manifest.py        # manifest:// resources
│       │   ├── validation.py      # validation:// resources
│       │   └── tracking.py        # file-tracking:// resources
│       ├── prompts/               # Prompt implementations
│       │   ├── __init__.py
│       │   ├── plan_task.py       # plan-task prompt
│       │   ├── implement.py       # implement-task prompt
│       │   ├── refactor.py        # refactor-code prompt
│       │   └── review.py          # review-manifest prompt
│       └── utils/                 # Utility functions
│           ├── __init__.py
│           ├── output_parser.py   # Parse MAID CLI output
│           └── manifest_utils.py  # Manifest helpers
│
├── tests/                         # Test suite
│   ├── __init__.py
│   ├── test_tools/
│   │   ├── test_validate.py
│   │   ├── test_snapshot.py
│   │   └── test_test.py
│   ├── test_resources/
│   │   ├── test_manifest.py
│   │   └── test_tracking.py
│   └── test_prompts/
│       ├── test_plan_task.py
│       └── test_implement.py
│
├── examples/                      # Example usage
│   ├── basic_client.py            # Example MCP client
│   ├── claude_integration.py      # Claude Code integration example
│   └── workflow_demo.py           # Complete MAID workflow demo
│
├── docs/                          # Documentation
│   ├── setup.md                   # Setup guide
│   ├── tools.md                   # Tool reference
│   ├── resources.md               # Resource reference
│   ├── prompts.md                 # Prompt reference
│   └── integration.md             # Integration guide
│
└── manifests/                     # MAID manifests (dogfooding)
    └── task-001-initial-implementation.manifest.json

---
🔧 Implementation Details

Technology Stack

Core Dependencies:
[project]
dependencies = [
    "maid-runner>=0.1.0",         # MAID Runner core
    "mcp>=1.0.0",                 # MCP Python SDK
]

Development Dependencies:
[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "black>=25.0.0",
    "ruff>=0.6.0",
    "mypy>=1.0.0",
]

---
Main Server Implementation (server.py)

"""MAID Runner MCP Server.

Exposes MAID Runner validation tools via Model Context Protocol.
"""
from mcp.server.fastmcp import FastMCP
from pathlib import Path

# Import tool implementations
from .tools.validate import register_validate_tool
from .tools.snapshot import register_snapshot_tool
from .tools.test import register_test_tool
from .tools.manifests import register_manifests_tool
from .tools.init import register_init_tool
from .tools.schema import register_schema_tool

# Import resource implementations
from .resources.manifest import register_manifest_resources
from .resources.validation import register_validation_resources
from .resources.tracking import register_tracking_resources

# Import prompt implementations
from .prompts.plan_task import register_plan_task_prompt
from .prompts.implement import register_implement_prompt
from .prompts.refactor import register_refactor_prompt
from .prompts.review import register_review_prompt

# Create FastMCP server
mcp = FastMCP("MAID Runner")

# Register all tools
register_validate_tool(mcp)
register_snapshot_tool(mcp)
register_test_tool(mcp)
register_manifests_tool(mcp)
register_init_tool(mcp)
register_schema_tool(mcp)

# Register all resources
register_manifest_resources(mcp)
register_validation_resources(mcp)
register_tracking_resources(mcp)

# Register all prompts
register_plan_task_prompt(mcp)
register_implement_prompt(mcp)
register_refactor_prompt(mcp)
register_review_prompt(mcp)

if __name__ == "__main__":
    # Run server with stdio transport (default)
    mcp.run()

---
Example Tool Implementation (tools/validate.py)

"""MAID Validate Tool Implementation."""
from typing import Optional
from mcp.server.fastmcp import FastMCP
from maid_runner.cli.validate import run_validation
import sys
from io import StringIO
import json

def register_validate_tool(mcp: FastMCP):
    """Register the maid_validate tool with the MCP server."""

    @mcp.tool()
    def maid_validate(
        manifest_path: str,
        validation_mode: str = "implementation",
        use_manifest_chain: bool = False,
        manifest_dir: Optional[str] = None,
        quiet: bool = True,
    ) -> dict:
        """Validate MAID manifest against implementation or behavioral tests.
        
        Args:
            manifest_path: Path to manifest JSON file
            validation_mode: Validation mode (implementation or behavioral)
            use_manifest_chain: Use manifest chain for validation
            manifest_dir: Directory containing manifests (for batch validation)
            quiet: Suppress success messages
            
        Returns:
            Validation result with success status, errors, and file tracking
        """
        # Capture stdout/stderr
        old_stdout = sys.stdout
        old_stderr = sys.stderr

        stdout_capture = StringIO()
        stderr_capture = StringIO()

        sys.stdout = stdout_capture
        sys.stderr = stderr_capture

        try:
            # Call MAID Runner validation
            run_validation(
                manifest_path=manifest_path,
                validation_mode=validation_mode,
                use_manifest_chain=use_manifest_chain,
                quiet=quiet,
                manifest_dir=manifest_dir,
            )

            # Validation passed
            success = True
            errors = []

        except SystemExit as e:
            # Validation failed or completed
            success = (e.code == 0)
            errors = stderr_capture.getvalue().strip().split('\n') if not success else []

        except Exception as e:
            # Unexpected error
            success = False
            errors = [str(e)]

        finally:
            # Restore stdout/stderr
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        # Parse output for structured data
        output = stdout_capture.getvalue()

        # Build structured response
        result = {
            "success": success,
            "mode": validation_mode,
            "manifest": manifest_path,
            "used_chain": use_manifest_chain,
            "errors": errors if not success else [],
        }

        # Parse file tracking analysis from output if present
        if use_manifest_chain and "FILE TRACKING ANALYSIS" in output:
            result["file_tracking"] = _parse_file_tracking(output)

        # Add raw output for debugging
        result["output"] = output

        return result

def _parse_file_tracking(output: str) -> dict:
    """Parse file tracking analysis from validation output."""
    # TODO: Implement parsing logic
    # Extract UNDECLARED, REGISTERED, TRACKED counts and file lists
    return {
        "undeclared": [],
        "registered": [],
        "tracked": []
    }

---
🧪 Testing Strategy

Unit Tests

- Test each tool individually
- Mock MAID Runner calls
- Verify input validation
- Check output structure

Integration Tests

- Test with real MAID Runner
- Use test manifests
- Verify end-to-end workflows

MCP Protocol Tests

- Test JSON-RPC communication
- Verify tool discovery
- Test resource access
- Validate prompt rendering

---
📚 Documentation Plan

README.md

- Project overview
- Installation instructions
- Quick start guide
- Tool reference
- Integration examples

docs/setup.md

- Detailed installation
- Configuration
- Transport options (stdio, SSE, WebSocket)
- Troubleshooting

docs/tools.md

- Complete tool reference
- Input/output schemas
- Examples for each tool
- Error handling

docs/integration.md

- Claude Code integration
- Aider integration
- Custom agent integration
- Best practices

---
🚀 Implementation Phases

Phase 1: Foundation (Week 1)

- ✅ Project setup (pyproject.toml, structure)
- ✅ Basic FastMCP server
- ✅ maid_validate tool (core functionality)
- ✅ maid_get_schema tool (simple)
- ✅ Basic tests
- ✅ README with quick start

Phase 2: Core Tools (Week 2)

- ✅ maid_snapshot tool
- ✅ maid_test tool
- ✅ maid_list_manifests tool
- ✅ maid_init tool
- ✅ Structured output parsing
- ✅ Error handling

Phase 3: Resources (Week 3)

- ✅ manifest:// resources
- ✅ validation:// resources
- ✅ schema:// resources
- ✅ file-tracking:// resources
- ✅ Resource discovery
- ✅ Caching strategy

Phase 4: Prompts (Week 4)

- ✅ plan-task prompt
- ✅ implement-task prompt
- ✅ refactor-code prompt
- ✅ review-manifest prompt
- ✅ Prompt argument handling
- ✅ Template rendering

Phase 5: Polish & Documentation (Week 5)

- ✅ Complete documentation
- ✅ Integration examples
- ✅ Claude Code configuration
- ✅ CI/CD setup
- ✅ Publishing to PyPI
- ✅ Announcement

---
🎯 Success Criteria

1. Functional:
  - All MAID CLI commands available as MCP tools
  - Structured JSON responses
  - Resource access working
  - Prompts rendering correctly
2. Integration:
  - Works with Claude Code
  - Works with MCP Inspector
  - Example client provided
  - Clear integration docs
3. Quality:
  80% test coverage
  - Type hints throughout
  - Documentation complete
  - Error handling robust
4. Performance:
  - Tool calls <500ms for validation
  - Resource access <100ms
  - Minimal memory overhead

---
🔮 Future Enhancements

v1.1

- WebSocket transport support
- Streaming validation results
- Progress reporting for long operations
- Notification support (manifest updates)

v1.2

- Advanced caching strategies
- Batch operations
- Parallel validation
- Custom transport options

v1.3

- Multi-language support (TypeScript, Go)
- Advanced prompts (code generation)
- AI-powered manifest suggestions
- Integration with GitHub Copilot

---
🤝 Integration Examples

Claude Code Integration

.claude/tools/maid.json:
{
  "maid-runner": {
    "command": "uv",
    "args": ["run", "maid-runner-mcp"],
    "env": {
      "MAID_MANIFEST_DIR": "manifests"
    }
  }
}

Example Usage in Claude Code:

User: Validate the latest manifest with chain support

Claude: I'll validate using the MAID Runner MCP server.
[Calls maid_validate tool with use_manifest_chain=true]

Result: ✅ Validation passed!
- Mode: implementation
- Manifest: task-042.manifest.json
- Used chain: Yes
- File tracking: 3 UNDECLARED, 5 REGISTERED, 42 TRACKED

---
📝 Key Design Decisions

1. Use FastMCP: Simpler than low-level API, faster development
2. Direct Python API calls: Call maid_runner functions directly instead of subprocess
3. Structured JSON outputs: Parse and structure all outputs for AI consumption
4. Progressive enhancement: Start with tools, add resources and prompts incrementally
5. Dogfooding MAID: Use MAID methodology to develop this project
6. Tool-agnostic philosophy: MCP is just another integration method, not a dependency

---
⚠️ Important Considerations

1. MAID Runner Dependency:
  - Requires maid-runner>=0.1.0
  - Should we vendor or depend on published package?
  - Decision: Depend on PyPI package for loose coupling
2. Async vs Sync:
  - MCP SDK uses async patterns
  - MAID Runner is mostly synchronous
  - Decision: Wrap sync calls in async functions
3. Error Handling:
  - MAID Runner uses SystemExit for errors
  - Need to catch and convert to structured errors
  - Decision: Try/except SystemExit, parse stderr
4. File Paths:
  - Relative vs absolute paths
  - Working directory handling
  - Decision: Always resolve to absolute, document assumptions
5. Transport Selection:
  - stdio for development/local
  - SSE/WebSocket for remote/production
  - Decision: stdio default, document others

---
🎬 Conclusion

This implementation plan provides a comprehensive roadmap for creating maid-runner-mcp, an
  MCP server that exposes MAID Runner validation tools to AI agents in a structured,
protocol-based manner.

Key Benefits:
1. Structured Access: Replace subprocess calls with typed tool invocations
2. Discoverability: AI agents can discover available tools and schemas
3. Rich Context: Resources and prompts guide AI agents through MAID workflow
4. Tool-Agnostic: Maintains MAID's philosophy while adding protocol integration
5. Future-Proof: Foundation for advanced AI-assisted development workflows

Next Steps:
1. Create repository structure
2. Implement Phase 1 (Foundation)
3. Test with MCP Inspector
4. Iterate based on feedback
5. Document and publish

This project bridges the gap between MAID Runner's validation-only philosophy and the
growing ecosystem of AI development tools using MCP! 🚀

=============

> Make sure to check the @docs/planning/GITHUB_ISSUES_CREATED.md as well 
  ⎿  Read docs/planning/GITHUB_ISSUES_CREATED.md (790 lines)

● Excellent point! I've reviewed the GitHub issues document. Let me enhance the 
  implementation plan to show how maid-runner-mcp fits into the existing MAID Runner roadmap
   and complements planned features.

  ---
  🔄 UPDATED: Integration with Existing Roadmap

  Positioning in the MAID Ecosystem

  The maid-runner-mcp project fits naturally into the existing roadmap as a new integration 
  epic alongside:

  - Epic #27: IDE Integration (LSP, VS Code)
  - Epic #28: CI/CD Integration (GitHub Actions, pre-commit hooks)
  - Epic #83: System Architecture Mapping (knowledge graph, system snapshots)
  - Epic #58: MAID Agent Automation (separate maid-agents repo)

  ┌─────────────────────────────────────────────────────────────┐
  │                    MAID Ecosystem                            │
  ├─────────────────────────────────────────────────────────────┤
  │                                                              │
  │  maid-runner (Core Validation)                              │
  │  ├── v1.3: Performance, CI/CD, System Architecture Mapping  │
  │  ├── v2.0: IDE Integration (LSP, VS Code)                   │
  │  └── v1.4+: Multi-language support                          │
  │                                                              │
  │  maid-runner-mcp (MCP Integration) ⭐ NEW                   │
  │  ├── Exposes MAID Runner as MCP server                      │
  │  ├── Tools, Resources, Prompts for AI agents                │
  │  └── Fits between v1.3 and v2.0 priorities                  │
  │                                                              │
  │  maid-agents (Automation - Future)                          │
  │  ├── Guardian Agent, Dependency Graph, Manifest Generation  │
  │  └── Can consume maid-runner-mcp tools!                     │
  │                                                              │
  │  maid-studio (Visual Architecture - v2.0+)                  │
  │  ├── Visual manifest designer, architecture dashboard       │
  │  └── Can also consume maid-runner-mcp resources!            │
  └─────────────────────────────────────────────────────────────┘

  ---
  Synergies with Existing Epics

  1. Epic #28: CI/CD Integration (v1.3 - Q1 2025)

  Synergy: MCP provides a standardized protocol for CI/CD tools to access MAID validation

  Specific Benefits:
  - Issue #32 (GitHub Actions Templates): MCP tools can be called from GitHub Actions
  - Issue #42 (Python API): MCP server IS a Python API (protocol-based)
  - Issue #46 (Reporting Formats): MCP structuredContent provides native JSON output

  Example GitHub Action with MCP:
  - name: Validate MAID Manifests via MCP
    uses: maid-mcp-action@v1
    with:
      mcp-server: maid-runner-mcp
      tool: maid_validate
      args: |
        {
          "manifest_dir": "manifests",
          "use_manifest_chain": true
        }

  ---
  2. Epic #83: System Architecture Mapping (v1.3 - High Priority)

  Synergy: MCP resources can expose the manifest knowledge graph

  Specific Benefits:
  - Issue #84 (System-Wide Snapshot): Expose via snapshot://system resource
  - Issue #85 (Knowledge Graph): Query graph via graph://query resource
  - Issue #86 (Coherence Validator): Run as maid_validate_coherence tool

  New MCP Resources (extends the plan):
  // New resource: system-wide snapshot
  "snapshot://system" → Complete system architecture manifest

  // New resource: knowledge graph query
  "graph://query?type=class&name=EmailValidator" → Graph nodes/edges

  // New resource: architectural metrics
  "metrics://architecture" → Coherence, coverage, complexity scores

  ---
  3. Epic #58: MAID Agent Automation (Future - Separate Repo)

  Synergy: maid-agents can consume maid-runner-mcp as a client!

  Integration Path:
  # maid-agents can use MCP client to call MAID Runner
  from mcp.client import ClientSession, stdio_client

  async def guardian_agent_workflow():
      """Guardian Agent uses MCP to validate and fix."""
      async with stdio_client({"command": "maid-runner-mcp"}) as (read, write):
          async with ClientSession(read, write) as session:
              await session.initialize()

              # Monitor tests (Guardian Agent feature)
              test_result = await session.call_tool("maid_test", {
                  "manifest_dir": "manifests"
              })

              if not test_result.success:
                  # Generate fix manifest (Guardian Agent feature)
                  manifest = generate_fix_manifest(test_result.failed_manifests)

                  # Validate via MCP
                  validation = await session.call_tool("maid_validate", {
                      "manifest_path": manifest
                  })

  Specific Benefits:
  - Issue #66 (Test Monitoring): Use maid_test tool via MCP
  - Issue #69 (Manifest Generator): Validate generated manifests via maid_validate
  - Issue #74 (Auto-detect readonlyFiles): Query graph://dependencies resource

  ---
  4. Epic #27: IDE Integration (v2.0 - Q2 2025)

  Synergy: MCP and LSP can coexist and complement each other

  Comparison:
  | Feature   | LSP Server                | MCP Server                   |
  |-----------|---------------------------|------------------------------|
  | Purpose   | Real-time editor feedback | AI agent tool access         |
  | Clients   | VS Code, IntelliJ, Vim    | Claude, GPT-4, Custom agents |
  | Protocol  | Language Server Protocol  | Model Context Protocol       |
  | Use Case  | Human developers          | AI assistants                |
  | Transport | stdio, HTTP               | stdio, SSE, WebSocket        |

  Complementary Use:
  - LSP: Provides real-time diagnostics while editing manifests
  - MCP: Enables AI agents to create/validate manifests programmatically
  - Both can share the same MAID Runner validation core!

  ---
  Where MCP Fits in the Roadmap

  Proposed: Epic #88: MCP Integration (v1.3.5 - Q1/Q2 2025)

  Priority: High (bridges v1.3 and v2.0 milestones)

  Timeline: 5 weeks (can start after Issue #34, #40, #44 from Epic #26)

  Child Issues (suggested):

  ### Issue #89: MCP Server Foundation
  - Implement FastMCP server with core tools
  - Priority: High, Effort: 1 week
  - Labels: type:feature, category:integration, version:v1.3.5, impl:separate-repo

  ### Issue #90: MCP Resource Implementation
  - Add manifest://, validation://, schema:// resources
  - Priority: High, Effort: 1 week
  - Dependencies: #89

  ### Issue #91: MCP Prompt Templates
  - Implement plan-task, implement-task, refactor-code prompts
  - Priority: Medium, Effort: 1 week
  - Dependencies: #89

  ### Issue #92: MCP Integration with System Architecture Mapping
  - Expose knowledge graph and system snapshot via MCP resources
  - Priority: High, Effort: 1 week
  - Dependencies: #84, #85, #89

  ### Issue #93: MCP Integration Documentation
  - Claude Code integration guide, example workflows
  - Priority: Medium, Effort: 1 week
  - Dependencies: #89, #90, #91

  Rationale for Priority:
  1. Enables AI agents NOW: Unlike MAID Agent (v1.4+), this is immediate
  2. Complements CI/CD work: Shares synergies with Epic #28
  3. Foundation for future: MAID Agent can use MCP client
  4. Low risk: Separate repo, doesn't affect MAID Runner core

  ---
  Dependencies and Interactions

  Depends On (from existing issues):

  - Issue #42 (Python API): MCP server is a form of Python API
  - Issue #84 (System Snapshot): Can expose as MCP resource
  - Issue #85 (Knowledge Graph): Can expose as MCP resource

  Enables (for future work):

  - Issue #58 (MAID Agent Epic): Agents can consume MCP tools
  - Issue #76 (Visual Studio Epic): Studio can use MCP resources
  - Issue #53 (Integration Tutorials): MCP is another integration to document

  ---
  Implementation Strategy with Existing Roadmap

  Phase 1: Parallel with v1.3 Performance Work (Week 1-2)

  While Issues #34, #40, #44 are being implemented in maid-runner:
  - Set up maid-runner-mcp repository
  - Implement basic FastMCP server
  - Add core tools: maid_validate, maid_snapshot, maid_test
  - No blocking dependencies on performance work

  Phase 2: Integrate with System Architecture Mapping (Week 3)

  After Issues #84, #85 are complete:
  - Add snapshot://system resource
  - Add graph://query resource
  - Add metrics://architecture resource
  - Demonstrates real value of System Architecture Mapping to AI agents

  Phase 3: Polish and Documentation (Week 4-5)

  Parallel with CI/CD documentation (Issue #38):
  - Add prompt templates
  - Write integration guides (Claude Code, Aider, etc.)
  - Create example workflows
  - Publish to PyPI

  ---
  Updated Ecosystem Diagram

  ┌──────────────────────────────────────────────────────────────┐
  │                        AI Agents                              │
  │  Claude Code, Aider, Cursor, Custom Agents, Future MAID Agent│
  └──────────────────────────────────────────────────────────────┘
                  │                    │
                  │ MCP Protocol       │ Direct CLI/API
                  ▼                    ▼
  ┌─────────────────────────┐   ┌──────────────────────────────┐
  │   maid-runner-mcp       │   │  CI/CD, Pre-commit Hooks     │
  │   (v1.3.5 - NEW)        │   │  (Epic #28 - v1.3)           │
  ├─────────────────────────┤   └──────────────────────────────┘
  │ Tools:                  │                │
  │ - maid_validate         │                │
  │ - maid_snapshot         │                │
  │ - maid_test             │                │
  │                         │                │
  │ Resources:              │                │
  │ - manifest://           │                │
  │ - snapshot://system ⭐  │                │
  │ - graph://query ⭐      │                │
  │ - validation://         │                │
  │                         │                │
  │ Prompts:                │                │
  │ - plan-task             │                │
  │ - implement-task        │                │
  └─────────────────────────┘                │
                  │                          │
                  │ Python API               │
                  ▼                          ▼
  ┌──────────────────────────────────────────────────────────────┐
  │                    maid-runner (Core)                         │
  │                                                               │
  │  v1.3: Performance + CI/CD + System Architecture Mapping ⭐   │
  │  v2.0: IDE Integration (LSP, VS Code)                        │
  │  v1.4+: Multi-language Support                               │
  └──────────────────────────────────────────────────────────────┘

  ---
  Key Advantages of MCP Integration

  1. Immediate Value: Works with Claude Code TODAY (not future v1.4+)
  2. Tool-Agnostic: Any MCP client can use it (not tied to specific AI)
  3. Complements Roadmap: Doesn't compete with LSP or MAID Agent
  4. Low Overhead: Separate repo, doesn't impact core development
  5. Foundation: MAID Agent (v1.4+) can consume it as a client
  6. Demonstrates Value: Shows System Architecture Mapping to AI agents

  ---
  Risk Analysis

  | Risk                              | Mitigation
                         |
  |-----------------------------------|-----------------------------------------------------
  -----------------------|
  | Duplicates Python API (Issue #42) | MCP IS a Python API (protocol-based); can be seen as
   implementation of #42 |
  | Competes with LSP                 | Different use cases: LSP for humans, MCP for AI
  agents                     |
  | Maintenance burden                | Separate repo, thin wrapper over maid-runner
                         |
  | Low adoption                      | Claude Code already supports MCP; growing ecosystem
                         |
  | Premature                         | v1.3 features (System Architecture Mapping) make it
  more valuable          |

  ---
  Recommendation

  Create Epic #88: MCP Integration

  Proposed GitHub Issue:

  # Epic #88: MCP Integration (v1.3.5)

  **Timeline:** Q1/Q2 2025 (between v1.3 and v2.0)
  **Priority:** High
  **Repository:** `maid-runner-mcp` (new separate repository)

  ## Goal

  Expose MAID Runner validation tools via Model Context Protocol (MCP) to enable seamless
  integration with AI development tools (Claude Code, Aider, custom agents).

  ## Motivation

  - **Immediate Value**: Works with existing MCP clients (Claude Code) TODAY
  - **Protocol-Based Access**: Standardized alternative to subprocess calls
  - **Future Foundation**: MAID Agent (v1.4+) can consume as MCP client
  - **Complements Roadmap**: Works alongside LSP, CI/CD, and System Architecture Mapping

  ## Features

  1. **MCP Tools**: `maid_validate`, `maid_snapshot`, `maid_test`, `maid_list_manifests`,
  `maid_init`, `maid_get_schema`
  2. **MCP Resources**: `manifest://`, `snapshot://system`, `graph://query`,
  `validation://`, `schema://`
  3. **MCP Prompts**: `plan-task`, `implement-task`, `refactor-code`, `review-manifest`
  4. **Integration**: Expose System Architecture Mapping (Epic #83) via resources

  ## Child Issues

  - [ ] #89: MCP Server Foundation (1 week)
  - [ ] #90: MCP Resource Implementation (1 week)
  - [ ] #91: MCP Prompt Templates (1 week)
  - [ ] #92: MCP Integration with System Architecture Mapping (1 week, depends on #84, #85)
  - [ ] #93: MCP Integration Documentation (1 week)

  ## Dependencies

  - **Weak dependency**: Issue #84, #85 (System Architecture Mapping) - makes it more
  valuable but not required
  - **No blocking dependencies**: Can start immediately in parallel with v1.3 work

  ## Success Criteria

  - [ ] All MAID CLI commands available as MCP tools
  - [ ] Works with Claude Code (example configuration provided)
  - [ ] System snapshot and knowledge graph exposed as resources
  - [ ] Documentation with integration guides
  - [ ] Published to PyPI as `maid-runner-mcp`

  ## Labels

  `type:feature`, `category:integration`, `version:v1.3.5`, `priority:high`,
  `impl:separate-repo`, `epic:mcp-integration`

  ---
  Conclusion: Perfect Timing

  The maid-runner-mcp project is perfectly positioned to:

  1. Bridge v1.3 and v2.0: Provides immediate AI integration while LSP is being developed
  2. Amplify System Architecture Mapping: Makes Epic #83 immediately accessible to AI agents
  3. Enable Future MAID Agent: Provides the protocol infrastructure for Epic #58
  4. Complement CI/CD Work: Another form of programmatic access (Epic #28)
  5. Demonstrate MAID Value: Show how MAID methodology works with modern AI tools

  Recommended Priority: High - Start after core v1.3 performance work (Issues #34, #40) and
  run in parallel with System Architecture Mapping (Issues #84, #85).

  This positions MAID Runner as the validation framework for AI-assisted development with
  multiple integration paths (CLI, Python API, MCP, LSP, CI/CD). 🚀
  