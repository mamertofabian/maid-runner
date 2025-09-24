# MAID Subagents

This directory contains specialized subagents for the MAID (Manifest-driven AI Development) workflow. These agents handle specific phases of the MAID development process.

## Available Agents

### 1. maid-manifest-architect
**Phase:** 1 - Goal Definition and Manifest Creation
**Purpose:** Creates and validates MAID manifests following v1.2 specifications
**Invocation:** Use when creating new task manifests or refining requirements

### 2. maid-test-designer
**Phase:** 2 - Behavioral Test Creation
**Purpose:** Creates comprehensive behavioral tests from manifests
**Invocation:** Use after manifest validation to create tests that exercise all declared artifacts

### 3. maid-developer
**Phase:** 3 - Implementation
**Purpose:** Implements code to make behavioral tests pass while maintaining manifest compliance
**Invocation:** Use after tests are created to implement the solution

### 4. maid-refactorer
**Phase:** 3.5 - Code Quality Refactoring
**Purpose:** Improves code quality, maintainability, and performance while preserving manifest compliance
**Invocation:** Use after implementation passes all tests to enhance code quality

### 5. maid-auditor
**Phase:** Cross-cutting - Compliance Enforcement
**Purpose:** Enforces strict MAID methodology compliance, catches violations and shortcuts across all phases
**Invocation:** Use after each phase or as final gate to ensure no compromises in methodology

## Usage

These agents will be automatically invoked by Claude Code when appropriate based on their descriptions. You can also explicitly request them:

```bash
# Examples of explicit invocation:
> Use the maid-manifest-architect agent to create a manifest for adding feature X
> Have the maid-test-designer create tests for task-005
> Get the maid-developer to implement the code for task-005
> Use the maid-refactorer to improve code quality for task-005
> Run the maid-auditor to check for MAID compliance violations
```

## Workflow

The typical MAID workflow using these agents:

1. **Define Goal** → maid-manifest-architect creates and validates manifest
2. **Create Tests** → maid-test-designer creates behavioral tests
3. **Implement** → maid-developer implements code to pass tests
4. **Refactor** → maid-refactorer improves code quality while maintaining test compliance
5. **Audit** → maid-auditor ensures strict MAID compliance (runs after each phase or as final gate)

Each agent handles its phase completely with iterative validation loops, ensuring quality at each step. The auditor acts as a cross-cutting concern, validating compliance throughout the workflow.

## Key Features

- **Complete Phase Ownership**: Each agent handles their entire phase autonomously
- **Validation-Driven**: Progress is measured by objective validation, not subjective assessment
- **Clear Handoffs**: Each agent knows when to pass work to the next phase
- **MAID Compliance**: All agents follow MAID v1.2 methodology strictly

## Note

These are project-level agents specific to the MAID Runner project. They understand the project's structure, validation tools, and MAID methodology deeply.