# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- Python 3.12 or higher
- jsonschema >= 4.25.1

**Development:**
- pytest >= 8.4.2 (for running tests)
- black >= 25.1.0 (for code formatting)
- ruff >= 0.13.0 (for linting)

[0.2.2]: https://github.com/mamertofabian/maid-runner/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/mamertofabian/maid-runner/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/mamertofabian/maid-runner/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/mamertofabian/maid-runner/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/mamertofabian/maid-runner/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/mamertofabian/maid-runner/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/mamertofabian/maid-runner/releases/tag/v0.1.0
