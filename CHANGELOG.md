# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.3]: https://github.com/mamertofabian/maid-runner/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/mamertofabian/maid-runner/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/mamertofabian/maid-runner/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/mamertofabian/maid-runner/releases/tag/v0.1.0
