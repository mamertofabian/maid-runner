# MAID Agents

Claude Code automation agents for the MAID (Manifest-driven AI Development) methodology.

## Overview

MAID Agents is a Claude Code-based automation layer for the MAID methodology. It uses Claude Code's headless CLI mode to automate the four phases of MAID workflow:

1. **Phase 1: Goal Definition** - ManifestArchitect agent creates precise manifests
2. **Phase 2: Planning Loop** - TestDesigner agent generates behavioral tests
3. **Phase 3: Implementation** - Developer agent implements code to pass tests
4. **Phase 3.5: Refactoring** - Refactorer agent improves code quality

## Installation

```bash
# Install from source
cd maid_agents/
uv pip install -e .

# Verify installation
ccmaid --version
```

## Prerequisites

- maid-runner package installed
- Claude Code CLI installed and authenticated
- Python 3.12+

## Usage

```bash
# Run full MAID workflow
ccmaid run "Add user authentication to the API"

# Run specific phases
ccmaid plan "Add user authentication"  # Phase 1-2: Manifest + Tests
ccmaid implement manifests/task-042.manifest.json  # Phase 3-3.5

# Validate existing manifests
ccmaid validate manifests/task-042.manifest.json
```

## Architecture

See `docs/architecture.md` for detailed architecture and design decisions.

## Development

This package dogfoods the MAID methodology - it was built using MAID itself!

All manifests are in `manifests/`, all behavioral tests in `tests/`.

## License

MIT License - See LICENSE file
