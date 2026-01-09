# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.1] - 2026-01-09

### Fixed
- Chronological filtering in `_find_prior_manifests_for_file` function
  - Function now correctly returns only manifests with lower task numbers (chronologically prior)
  - Previously returned ALL manifests for a file, including newer ones, causing false validation errors
  - Fixed bug where validating older snapshot manifests incorrectly reported newer manifests as "prior"
  - Added comprehensive test coverage to prevent regression

## [0.9.0] - 2026-01-08

### Added
- **JSON Output Mode for LSP Integration** (Issue #46) - Machine-readable validation output for editor integration
  - New `--json-output` flag for `maid validate` command
  - Structured JSON output with validation results, errors, and diagnostics
  - Location information (file, line, column) for IDE integration
  - Enables seamless integration with VS Code, Neovim, and other LSP-aware editors

### Fixed
- Location info support for `AlignmentError` for better error reporting
- Multiple bug fixes for `--json-output` feature addressing edge cases and output format issues

### Changed
- Refactored shared validation logic into `_perform_core_validation` for better code organization

## [0.8.0] - 2026-01-08

### Added
- **Architectural Coherence Validation** (Issue #86) - Comprehensive validation for manifest consistency and architecture compliance
  - Duplicate artifact detection across manifests to identify redundant declarations
  - Naming convention validation ensuring consistent file and artifact naming patterns
  - Dependency validation to detect circular dependencies and missing relationships
  - Pattern compliance checking against configurable architectural rules
  - Constraint validation for cross-cutting concerns and project-wide rules
  - CLI integration via `maid validate --coherence` with optional JSON output (`--json`)
  - False positive filtering for legitimate artifact variations

### Changed
- **Claude Code Integration** improvements
  - MAID validation hook for automatic coherence checking
  - Plugin version alignment with package versioning
  - Installation documentation recommending Claude Code plugin marketplace

## [0.7.0] - 2025-12-31

### Added
- **Knowledge Graph Builder** (Issue #85) - Complete feature for visualizing and querying manifest relationships
  - Core data model with `ManifestNode`, `ArtifactNode`, `FileNode`, and relationship types
  - Graph builder module for constructing knowledge graphs from manifests
  - Query engine for traversing and analyzing manifest relationships
  - Export formats: DOT (Graphviz), JSON, and Mermaid diagram support
  - CLI integration via `maid graph` command with multiple output options
  - Public API for programmatic access to knowledge graph functionality
- **Manifest Chain Caching** (Issue #34) - Performance optimization for manifest chain resolution
  - Caches resolved manifest chains to avoid redundant file system operations
  - Automatic cache invalidation when manifests are modified
  - Significant performance improvement for large codebases with many manifests

### Changed
- **Code readability improvements** with consistent formatting across the codebase
- **Cache reliability improvements** with better logging and freshness checks

### Documentation
- **README expansion** with conceptual framework for Structural Determinism in Generative AI

## [0.6.0] - 2025-12-30

### Added
- **`maid manifest create` command** for programmatic manifest generation (Tasks 095-099)
  - Create new manifests with auto-numbering (`--goal "description"`)
  - Auto-supersedes snapshot manifests for the same file
  - Support for `--delete` flag to create file deletion manifests
  - Support for `--rename-to` flag to create file rename manifests
  - JSON output mode (`--json`) for tool integration
  - Dry-run mode (`--dry-run`) to preview manifest without writing
  - Path normalization for consistent manifest references
  - Artifact specification via `--artifacts` flag (JSON format)
- **Snapshot supersession validation** to prevent manifest abuse (Task 100)
  - Only snapshot manifests can be superseded
  - Edit/create/refactor manifests cannot supersede each other (prevents task "re-farming")
  - Legacy snapshots (without `taskType`) automatically detected and allowed
  - Clear error messages explaining supersession rules
  - Integrated into `maid validate` command
- **Auto-sync Claude files** before test runs via pytest conftest.py
  - Ensures packaged Claude documentation stays synchronized

### Fixed
- **Test file bypass security loophole** closed (Issue #100)
  - Improved path handling in validation
  - Added edge case tests for path normalization
- **Deduplication key** now includes `returns` field for more accurate artifact matching
- **E402 lint error** resolved in conftest.py

### Changed
- Supersession validation now integrated directly into manifest validation pipeline

## [0.5.0] - 2025-12-11

### Added
- **Multi-runner batch mode for `maid test`** (Tasks 093-094)
  - Intelligent batch testing that runs all test files in a single invocation per test runner type
  - Eliminates overhead of N separate test processes for N manifests (10-20x faster)
  - Automatic detection of test runner from `validationCommand` (pytest, vitest, jest, npm/pnpm test)
  - Support for mixed runner projects - batches each runner type separately
  - Package manager detection for JavaScript projects (pnpm/npm/yarn)
  - Environment setup handling (uv run prefix, PYTHONPATH configuration)
  - Clean, readable output format showing command prefix and test counts
  - Always displays test runner output with individual test counts and results
  - Example output: `Command: pnpm exec vitest run <141 test files>`

### Changed
- **Improved test execution output**
  - Test runner output now always visible (no longer requires `--verbose`)
  - Shows complete test results including counts, progress, and failures
  - More informative feedback during test execution

## [0.4.1] - 2025-12-10

### Fixed
- **Manifest chain validation with superseded manifests** (Task-092)
  - `discover_related_manifests()` now correctly filters out superseded manifests
  - Fixed bug where manifest chain validation incorrectly merged artifacts from superseded manifests
  - Resolves validation failures when active manifests remove artifacts declared in superseded manifests
  - Added type hints to `discover_related_manifests()` signature
  - Comprehensive test coverage for supersession filtering
- **Version retrieval in CLI**
  - Fixed pyproject.toml path resolution in dynamic version retrieval
  - Ensures correct version display in `maid --version` command

## [0.4.0] - 2025-12-09

### Added
- **Svelte file support** (Tasks 086-088)
  - Full validation support for Svelte files (`.svelte` extension)
  - AST parsing using tree-sitter for Svelte components
  - Integration with existing multi-language validation framework
- **Enhanced behavioral validation with import following** (Task 085)
  - Automatically follows imports from test files to detect artifact usage
  - Finds and analyzes imported test helper modules
  - Supports relative imports and test module patterns
  - Improves validation accuracy for modular test suites
- **Private implementation file categorization** (Tasks 089-091)
  - New categories for private implementation files in file tracking
  - Better organization and visibility of internal vs public modules
  - Improved compliance reporting for private artifacts
- **Dead code detection with vulture**
  - Added vulture dependency for detecting unused code
  - Helps maintain clean codebase by identifying dead code paths

### Changed
- **Major refactoring for code maintainability**
  - Extracted `validate.py` into smaller private helper modules
  - Refactored `manifest_validator.py` into focused private modules
  - Organized large test files into structured directory layout
  - Split task-005 type validation tests into smaller, focused modules
  - Improved code organization without changing public API

### Fixed
- **Private artifact behavioral validation**
  - Closed loophole in private artifact validation logic
  - Enhanced tracking of private class patterns
  - Added comprehensive behavioral tests for private artifacts
- **Test infrastructure improvements**
  - Fixed test imports with proper sys.path manipulation
  - Improved test file organization and maintainability
  - Added private test files for complete behavioral coverage

### Documentation
- **README improvements**
  - Clarified MAID Runner capabilities and scope
  - Updated documentation for new features
  - Enhanced examples and usage guidelines

## [0.3.1] - 2025-12-05

### Fixed
- **CLI validation for absent status files**
  - Validation now correctly skips existence checks for files marked with `status: "absent"` in manifests
  - Prevents false validation failures when cleaning up deleted files
  - Ensures proper handling of file deletion manifests in `maid validate` command

### Changed
- **PyPI release automation improvements**
  - Updated release commit messages to be more descriptive
  - Changed from generic "chore: bump version" to "release: vX.Y.Z - [Main feature]"
  - Improves GitHub release page readability and changelog clarity

## [0.3.0] - 2025-12-05

### Added
- **File deletion tracking with `status` field** (Tasks 082-084)
  - New optional `status` field in `expectedArtifacts` schema with enum values `["present", "absent"]`
  - Default value is `"present"` for backward compatibility with existing manifests
  - Files with `status: "absent"` are validated to not exist in the codebase
  - Strict semantic validation enforces proper deletion manifest structure:
    - Files in `creatableFiles` cannot have `status: "absent"` (contradiction)
    - Files with `status: "absent"` must have empty `contains` array
    - Files with `status: "absent"` must have `taskType: "refactor"`
    - Files with `status: "absent"` must have non-empty `supersedes` array
  - Replaces witness file pattern with self-documenting deletion manifests

### Changed
- **Documentation updates for file deletion and rename patterns**
  - Updated MAID specs, CLAUDE.md, and init.py to use new `status: "absent"` pattern
  - Added comprehensive documentation for file deletion and rename workflows
  - Clarified superseded manifest behavior (archived, not active in validation/tests)

### Fixed
- **CI workflow enhancement** to run Claude sync before validation
  - Ensures packaged documentation is up-to-date before validation

## [0.2.9] - 2025-12-05

### Changed
- **Lowered Python requirement** from 3.11+ to 3.10+ with CI matrix testing
  - Expands compatibility to support Python 3.10, 3.11, and 3.12
  - Adds comprehensive CI testing across all supported Python versions

### Fixed
- **Method parameter validation** to handle dict format
  - Properly processes parameters defined as dictionaries with `name` and `type` keys
  - Fixes validation failures when manifest uses dict parameter format
- **Snapshot force flag bug** where `maid snapshot --force` causes manifest to supersede itself
  - Prevents manifest from incorrectly marking itself as superseded
  - Ensures proper manifest chain integrity

## [0.2.8] - 2025-12-03

### Added
- **Schema-only validation mode** for `maid validate`
  - New `--validation-mode schema` option to validate manifest structure only
  - Useful for manifest authoring without implementation files
  - Enables faster validation during planning phase
- **TypeScript parameter type annotation extraction**
  - Extracts and validates parameter types from TypeScript code
  - Supports modern TypeScript syntax including arrow functions
- **TypeScript artifact type validation support**
  - Validates TypeScript artifact types (classes, functions, interfaces, etc.)
  - Full compatibility with TypeScript AST parsing

### Fixed
- Handle dict parameter format in validation
  - Properly processes parameters defined as dictionaries with `name` and `type` keys
  - Improves compatibility with different manifest parameter formats
- **Arrow function detection** in class and object properties
  - Detects arrow functions assigned to class properties
  - Detects arrow functions in object properties
  - Ensures complete TypeScript/JavaScript method coverage

## [0.2.6] - 2025-12-03

### Added
- **Pre-commit hooks** for automated code quality and MAID validation
  - Runs black formatter, ruff linter, and MAID validation on commit
  - Automatic MAID test execution before commits
  - Smart Claude files sync when `.claude/` directory changes
  - Integrates with existing git hook infrastructure
- **Smart project root detection** for non-standard directory layouts
  - Walks up directory tree looking for project markers (.git, pyproject.toml, package.json, etc.)
  - Fixes `maid test` and `maid validate` when manifests are in project root or custom test directories
- **`/maid-run` command** for complete MAID workflow orchestration
  - Chains all MAID phases (manifest creation, test design, implementation, refactoring)
  - Uses subagents for automated workflow execution
  - Included in distributable files copied by `maid init`
- **Installation instructions** in generated CLAUDE.md files
  - Prerequisites section explaining pip, uv, and pipx installation options
  - Helps users understand maid-runner is a Python CLI tool requiring installation

### Changed
- **Documentation improvements** for Claude Code integration
  - Updated agents and commands with refactoring guidance
  - Clarified when manifests are needed vs. when private refactoring is acceptable
  - Added phase separation notes (don't create tests in Phase 1)
  - Improved manifest rules clarity (immutability, one-file-per-manifest, Definition of Done)
  - Refactored `init.py` to extract duplicate sections into helper functions (~450 lines → ~100 lines)

### Fixed
- Include watchdog in dev dependencies to ensure all tests pass
  - Prevents import errors when running tests that check watch mode functionality
  - Still optional for end users via `[watch]` extra

## [0.2.5] - 2025-12-02

### Added
- Include `unit-testing-rules.md` in PyPI package and `maid init` output
- Multi-language support for file tracking (TypeScript, JavaScript, Python)
- Automatic exclusion of `node_modules` directory from file tracking

### Fixed
- Use correct test file extension (`.test.ts`) in snapshot validationCommand for TypeScript
- Remove unused `typing_extensions` dependency for TypedDict

## [0.2.4] - 2025-12-02

### Added
- Task ID prefix in watch mode validation output for easier identification
- Results summary at end of watch mode validation (pass/fail counts)

### Fixed
- Improved error handling for missing test files in behavioral validation
  - Provides clearer error messages when test files referenced in validation commands don't exist

## [0.2.3] - 2025-12-02

### Added
- **Watch Mode for `maid validate` Command** - Continuous validation during development
  - Single-manifest watch mode (`maid validate <manifest> --watch`)
  - Multi-manifest watch mode (`maid validate --watch-all`)
  - Watches manifest, implementation, and test files for changes
  - Runs both behavioral and implementation validation on changes
  - Optional test execution with `--skip-tests` flag
  - Dynamic manifest discovery (new manifests auto-detected)
- **`maid files` Command** - File tracking status overview
  - Shows UNDECLARED, REGISTERED, and TRACKED file counts
  - Quick visibility into MAID compliance across codebase
- **Idempotent `maid init`** - Marker-based CLAUDE.md handling
  - Updates only MAID-managed sections, preserves user content
  - Safe to re-run without losing customizations

### Changed
- Refactored validate watch-all to use single handler pattern (matching maid test architecture)
- Improved watch mode output buffering for non-TTY environments

### Fixed
- Handle `Generic[T]` and parameterized base classes in validator
- Use `(type, class, name)` key for artifact merging to prevent overwrites
- Handle atomic file writes in watch-all mode (editors using temp file + rename)
- Run validation for newly discovered manifests in watch-all mode

## [0.2.2] - 2025-12-01

### Fixed
- Fixed module import error when running `maid test` from projects without the optional `watchdog` dependency
  - Added fallback dummy classes to prevent `NameError` during module parsing
  - Enables basic `maid test` functionality without watch mode features
  - Watch mode features properly report errors if used without `watchdog` installed

## [0.2.1] - 2025-12-01

### Added
- **Watch Mode for `maid test` Command** - Live test execution with file change detection
  - Single-manifest watch mode (`maid test --manifest X --watch`)
  - Multi-manifest watch mode (`maid test --watch-all`)
  - Intelligent file-to-manifests mapping for targeted test runs
  - Debounced file change detection (2-second delay)
  - Automatic re-execution of validation commands on file changes
  - Requires optional `watchdog` dependency
- **CLI Enhancements**
  - Added `--watch` flag to `maid test` for single-manifest watch mode
  - Added `--watch-all` flag to `maid test` for multi-manifest watch mode
  - Added validation: `--watch` requires `--manifest` to be specified
  - Added mutual exclusivity check between `--watch` and `--watch-all` flags
- **Quality-Check-and-Commit Slash Command** - Custom command for running all quality checks and committing changes

### Changed
- Enhanced `maid test` command with watch mode capabilities for TDD workflows
- Improved error messages to guide users between single and multi-manifest watch modes
- Improved watch mode file matching and performance

### Fixed
- Support for multiple manifest path formats in watch mode
- Watch mode now monitors test files in addition to implementation files

### Removed
- Retired `dev_bootstrap.py` script in favor of `maid test` CLI command

## [0.2.0] - 2025-11-30

### Added
- **TypeScript/JavaScript Support** - Production-ready multi-language validation
  - TypeScript validator using tree-sitter for accurate AST parsing
  - Support for `.ts`, `.tsx`, `.js`, `.jsx` file extensions
  - Complete language coverage: classes, interfaces, type aliases, enums, namespaces
  - Function support: async, arrow, generic functions with full parameter detection
  - Method support: static, private, getters/setters, abstract, decorators
  - Framework support: Angular, React, NestJS, Vue with JSX/TSX syntax
- TypeScript test runner integration with automatic package manager detection (npm, pnpm, yarn)
- Extended manifest schema with new artifact types: `interface`, `type`, `enum`, `namespace`
- TypeScript snapshot generation via `maid snapshot` with automatic language detection
- System-wide TypeScript support via `maid snapshot-system` for cross-language projects
- TypeScript test stub generation via `maid generate-stubs` with Jest syntax
- Language-specific `maid init` - Generates Python or TypeScript-specific CLAUDE.md based on project type
- **Claude Code Integration** - Simplified MAID agents and slash commands for Claude Code workflows
  - Pre-configured agents: manifest-architect, test-designer, developer, refactorer, auditor, fixer
  - Slash commands: `/generate-manifest`, `/generate-tests`, `/implement`, `/refactor`, `/fix`, `/audit`
  - Automatic sync infrastructure for PyPI package distribution

### Changed
- Refactored validation architecture for language extensibility
  - Created `BaseValidator` abstract class for language-agnostic validation
  - Extracted `PythonValidator` from monolithic validator
  - Validator auto-detection based on file extensions
- Optimized test suite by replacing subprocess calls with direct function calls

### Dependencies
- Added `tree-sitter>=0.23.2` for TypeScript AST parsing
- Added `tree-sitter-typescript>=0.23.2` for TypeScript/TSX grammar support

## [0.1.3] - 2025-11-29

### Fixed
- Fixed async function detection in manifest validator (Task-049)
  - Added visit_AsyncFunctionDef handler to _ArtifactCollector class
  - Async functions are now properly detected and validated
  - Fixes validation failures for projects using async/await syntax

### Added
- GitHub Actions workflow for automated PyPI publishing
  - Automated build and publish on version tags
  - Includes artifact signing with Sigstore
  - Automatic GitHub releases with signed artifacts

### Changed
- Documentation improvements and cleanup
- Removed obsolete planning documents

## [0.1.2] - 2025-11-27

### Changed
- Updated README with MAID Ecosystem section
- Added documentation about MAID Agents integration
- Clarified relationship between MAID Runner (validation) and MAID Agents (orchestration)

## [0.1.1] - 2025-11-25

### Fixed
- Fixed `maid init` command by including `maid_specs.md` in package distribution
- Moved `docs/maid_specs.md` into `maid_runner/docs/` package directory for proper packaging
- Updated `maid init` file path resolution to locate specs within installed package

## [0.1.0] - 2025-11-25

### Added

#### Core Validation Framework
- Manifest schema validation against JSON schema
- Behavioral test validation using AST analysis
- Implementation validation using AST analysis
- Manifest chain support for tracking file evolution
- File tracking analysis with compliance levels (UNDECLARED, REGISTERED, TRACKED)

#### CLI Commands
- `maid validate` - Validate manifests, tests, and implementations
- `maid snapshot` - Generate snapshot manifests from existing code
- `maid snapshot-system` - Generate system-wide manifest aggregation
- `maid test` - Run validation commands from all manifests
- `maid manifests` - List manifests referencing a specific file
- `maid init` - Initialize MAID workflow in a project
- `maid generate-stubs` - Generate stub implementations from manifests
- `maid schema` - Output the manifest JSON schema

#### Validation Modes
- **Strict Mode** (`creatableFiles`) - Implementation must exactly match expectedArtifacts
- **Permissive Mode** (`editableFiles`) - Implementation must contain expectedArtifacts

#### Artifact Support
- Functions with parameters and return types
- Classes with inheritance
- Methods with class context
- Attributes (class and module-level)
- Type hints validation
- Private artifact handling (underscore prefix)

#### Python API
- `validate_schema()` - Validate manifest JSON schema
- `validate_with_ast()` - Validate implementation against manifest
- `discover_related_manifests()` - Find related manifests in chain
- `generate_snapshot()` - Generate manifest from code
- `AlignmentError` - Custom exception for validation failures
- `collect_behavioral_artifacts()` - Extract artifacts from test files

#### Documentation
- Comprehensive README with usage examples
- MAID specification document (maid_specs.md)
- Contributing guidelines
- MIT License
- Type hints support (PEP 561 compliant with py.typed marker)

#### Project Structure
- Tool-agnostic design (validation-only, no code generation)
- Clean separation of CLI and core validation logic
- Modular architecture with dedicated validators
- JSON schema for manifest structure enforcement

### Initial Release Notes

This is the first public release of MAID Runner, implementing the core Manifest-driven AI Development (MAID) methodology validation framework. The tool is designed to be tool-agnostic, focusing purely on validation rather than automation or code generation.

**Key Principles:**
- Explicitness: Every task context explicitly defined in manifests
- Extreme Isolation: Tasks touch minimal files, all specified in manifest
- Test-Driven Validation: Tests define success criteria
- Verifiable Chronology: Current state = sequential manifest application

**Requirements:**
- Python 3.10 or higher
- jsonschema >= 4.25.1

**Development:**
- pytest >= 8.4.2 (for running tests)
- black >= 25.1.0 (for code formatting)
- ruff >= 0.13.0 (for linting)

[0.9.1]: https://github.com/mamertofabian/maid-runner/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/mamertofabian/maid-runner/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/mamertofabian/maid-runner/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/mamertofabian/maid-runner/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/mamertofabian/maid-runner/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/mamertofabian/maid-runner/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/mamertofabian/maid-runner/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/mamertofabian/maid-runner/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/mamertofabian/maid-runner/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/mamertofabian/maid-runner/compare/v0.2.9...v0.3.0
[0.2.9]: https://github.com/mamertofabian/maid-runner/compare/v0.2.8...v0.2.9
[0.2.8]: https://github.com/mamertofabian/maid-runner/compare/v0.2.6...v0.2.8
[0.2.6]: https://github.com/mamertofabian/maid-runner/compare/v0.2.5...v0.2.6
[0.2.5]: https://github.com/mamertofabian/maid-runner/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/mamertofabian/maid-runner/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/mamertofabian/maid-runner/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/mamertofabian/maid-runner/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/mamertofabian/maid-runner/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/mamertofabian/maid-runner/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/mamertofabian/maid-runner/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/mamertofabian/maid-runner/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/mamertofabian/maid-runner/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/mamertofabian/maid-runner/releases/tag/v0.1.0
