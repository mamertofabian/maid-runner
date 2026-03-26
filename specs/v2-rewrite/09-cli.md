# MAID Runner v2 - CLI Specification

**References:** [01-architecture.md](01-architecture.md), [05-core-validation.md](05-core-validation.md), [10-public-api.md](10-public-api.md)

## Design Principles

1. **Thin wrapper** - CLI functions call library API and format output. No business logic.
2. **Each command < 50 lines** - If longer, logic belongs in the library.
3. **Total CLI code < 500 lines** - Including argument parsing and formatting.
4. **Consistent output** - All commands support `--json` for machine-readable output.
5. **Exit codes** - 0 = success, 1 = validation failure, 2 = usage error.

## Module Location

- `maid_runner/cli/main.py` - Entry point, argument parser, subcommand routing
- `maid_runner/cli/commands/*.py` - One file per command group
- `maid_runner/cli/format.py` - Output formatters

## Entry Point

```python
# maid_runner/cli/main.py

def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Parses arguments and dispatches to command handlers.
    Returns exit code (0=success, 1=failure, 2=usage error).
    """
```

Registered as console script in pyproject.toml:
```toml
[project.scripts]
maid = "maid_runner.cli.main:main"
```

## Command Reference

### `maid validate`

**Purpose:** Validate manifests against code.

```
maid validate [MANIFEST_PATH] [OPTIONS]

Arguments:
  MANIFEST_PATH          Path to specific manifest (optional; validates all if omitted)

Options:
  --mode MODE            Validation mode: "behavioral" or "implementation" (default: implementation)
  --manifest-dir DIR     Manifest directory (default: manifests/)
  --no-chain             Disable manifest chain merging
  --coherence            Also run coherence checks
  --coherence-only       Run ONLY coherence checks (skip structural validation)
  --json                 Output results as JSON
  --quiet                Only show errors, no summary
  --watch                Watch for changes and re-validate (single manifest)
  --watch-all            Watch for changes across all manifests

Exit codes:
  0  All validations passed
  1  One or more validations failed
  2  Invalid arguments or manifest not found
```

**Implementation (`cli/commands/validate.py`):**

```python
def cmd_validate(args: argparse.Namespace) -> int:
    """Handle 'maid validate' command."""
    from maid_runner.core.validate import ValidationEngine, validate, validate_all
    from maid_runner.core.result import ValidationMode

    mode = ValidationMode(args.mode)
    engine = ValidationEngine(project_root=".")

    if args.manifest_path:
        result = engine.validate(
            args.manifest_path,
            mode=mode,
            use_chain=not args.no_chain,
            manifest_dir=args.manifest_dir,
        )
        _print_result(result, json_mode=args.json, quiet=args.quiet)
        return 0 if result.success else 1
    else:
        batch = engine.validate_all(args.manifest_dir, mode=mode)
        _print_batch_result(batch, json_mode=args.json, quiet=args.quiet)
        return 0 if batch.success else 1
```

### `maid test`

**Purpose:** Run validation commands from manifests.

```
maid test [OPTIONS]

Options:
  --manifest PATH        Run tests for specific manifest only
  --manifest-dir DIR     Manifest directory (default: manifests/)
  --fail-fast            Stop on first failure
  --verbose              Show full test output
  --watch                Watch mode for single manifest
  --watch-all            Watch mode for all manifests
  --batch                Force batch mode (combine compatible tests)
  --no-batch             Disable batch mode

Exit codes:
  0  All tests passed
  1  One or more tests failed
  2  Invalid arguments
```

**Implementation (`cli/commands/test.py`):**

```python
def cmd_test(args: argparse.Namespace) -> int:
    """Handle 'maid test' command."""
    from maid_runner.core.test_runner import run_tests, run_manifest_tests

    if args.manifest:
        result = run_manifest_tests(args.manifest, fail_fast=args.fail_fast)
    else:
        result = run_tests(
            manifest_dir=args.manifest_dir,
            fail_fast=args.fail_fast,
            batch=args.batch,
        )

    _print_test_result(result, verbose=args.verbose, json_mode=args.json)
    return 0 if result.success else 1
```

### `maid snapshot`

**Purpose:** Generate manifest from existing code.

```
maid snapshot FILE_PATH [OPTIONS]

Arguments:
  FILE_PATH              Source file to snapshot

Options:
  --output-dir DIR       Output directory for manifest (default: manifests/)
  --output FILE          Specific output file path
  --with-tests           Generate test stub file
  --force                Overwrite existing manifest
  --json                 Output manifest as JSON instead of YAML
  --dry-run              Show what would be generated without writing

Exit codes:
  0  Snapshot generated successfully
  1  Error during snapshot generation
  2  Invalid arguments or file not found
```

**Implementation (`cli/commands/snapshot.py`):**

```python
def cmd_snapshot(args: argparse.Namespace) -> int:
    """Handle 'maid snapshot' command."""
    from maid_runner.core.snapshot import generate_snapshot, save_snapshot

    manifest = generate_snapshot(args.file_path)

    if args.dry_run:
        print(format_manifest(manifest, json_mode=args.json))
        return 0

    path = save_snapshot(manifest, output_dir=args.output_dir, output=args.output)
    print(f"Snapshot saved to {path}")
    return 0
```

### `maid snapshot-system`

**Purpose:** Generate system-wide manifest aggregating all files.

```
maid snapshot-system [OPTIONS]

Options:
  --output FILE          Output file (default: manifests/system-snapshot.manifest.yaml)
  --manifest-dir DIR     Manifest directory (default: manifests/)
  --quiet                Minimal output
  --json                 Output as JSON
```

### `maid manifest create`

**Purpose:** Create a new manifest programmatically.

```
maid manifest create FILE_PATH [OPTIONS]

Arguments:
  FILE_PATH              Target file for the manifest

Options:
  --goal TEXT            Goal description (required)
  --type TYPE            Task type: feature, fix, refactor (default: feature)
  --artifacts JSON       Artifact declarations as JSON
  --output-dir DIR       Output directory (default: manifests/)
  --dry-run              Show manifest without writing
  --json                 Output as JSON
  --delete               Create deletion manifest
  --rename-to PATH       Create rename manifest (old path -> new path)
```

### `maid manifests`

**Purpose:** List manifests that reference a file.

```
maid manifests FILE_PATH [OPTIONS]

Arguments:
  FILE_PATH              File to search for in manifests

Options:
  --manifest-dir DIR     Manifest directory (default: manifests/)
  --json                 Output as JSON
  --quiet                Show paths only
```

### `maid files`

**Purpose:** Show file tracking status across the project.

```
maid files [OPTIONS]

Options:
  --manifest-dir DIR     Manifest directory (default: manifests/)
  --hide-private         Hide private implementation files
  --json                 Output as JSON
  --quiet                Show summary only
```

### `maid init`

**Purpose:** Initialize MAID in a project.

```
maid init [OPTIONS]

Options:
  --tool TOOL            AI tool: claude, cursor, windsurf, generic (default: auto-detect)
  --dry-run              Show what would be created without writing
  --force                Overwrite existing configuration
```

### `maid graph`

**Purpose:** Knowledge graph operations.

```
maid graph query QUESTION [OPTIONS]
maid graph export [OPTIONS]
maid graph analyze FILE_PATH [OPTIONS]

Subcommands:
  query                  Run a natural language query against the graph
  export                 Export graph to file (--format: json, dot, graphml)
  analyze               Analyze dependencies for a file

Options:
  --manifest-dir DIR     Manifest directory (default: manifests/)
  --format FORMAT        Export format: json, dot, graphml (default: json)
  --output FILE          Output file (default: stdout)
  --json                 JSON output for query/analyze
```

### `maid coherence`

**Purpose:** Run coherence validation standalone.

```
maid coherence [OPTIONS]

Options:
  --manifest-dir DIR     Manifest directory (default: manifests/)
  --checks LIST          Comma-separated check names to run
  --exclude LIST         Comma-separated check names to exclude
  --json                 Output as JSON
```

### `maid schema`

**Purpose:** Display the manifest JSON Schema.

```
maid schema [OPTIONS]

Options:
  --version VER          Schema version: 1 or 2 (default: 2)
```

### `maid howto`

**Purpose:** Show MAID workflow guidance.

```
maid howto [TOPIC]

Topics:
  create                 How to create a manifest
  validate               How to validate
  snapshot               How to snapshot existing code
  migrate                How to migrate from v1 to v2
  workflow               Complete MAID workflow
```

## Watch Mode

Watch mode is implemented in `cli/commands/validate.py` and `cli/commands/test.py` using the `watchdog` library (optional dependency).

### Single-Manifest Watch

```
maid validate manifests/add-auth.manifest.yaml --watch
maid test --manifest manifests/add-auth.manifest.yaml --watch
```

Monitors:
- The manifest file itself
- All files referenced in the manifest (create, edit, read)
- Re-runs validation/tests on any change

### Multi-Manifest Watch

```
maid validate --watch-all
maid test --watch-all
```

Monitors:
- All manifest files
- All source files referenced by any manifest
- On change: identifies affected manifests and re-runs only those

### Watch Implementation

```python
# In cli/commands/validate.py
def _watch_single(manifest_path: str, engine: ValidationEngine, args) -> int:
    """Watch a single manifest and its files."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        print("Watch mode requires 'watchdog'. Install: pip install maid-runner[watch]")
        return 2

    # ... setup observer, event handler, debounce, re-validate on change
```

## Output Formatting (`cli/format.py`)

```python
def format_validation_result(result: ValidationResult, *, json_mode: bool = False, quiet: bool = False) -> str:
    """Format a single validation result for display."""

def format_batch_result(result: BatchValidationResult, *, json_mode: bool = False, quiet: bool = False) -> str:
    """Format batch validation results for display."""

def format_test_result(result: BatchTestResult, *, verbose: bool = False, json_mode: bool = False) -> str:
    """Format test run results for display."""

def format_coherence_result(result: CoherenceResult, *, json_mode: bool = False) -> str:
    """Format coherence validation results for display."""

def format_file_tracking(report: FileTrackingReport, *, json_mode: bool = False, hide_private: bool = False) -> str:
    """Format file tracking report for display."""

def format_manifest(manifest: Manifest, *, json_mode: bool = False) -> str:
    """Format a manifest for display (YAML by default, JSON if requested)."""
```

### Text Format Conventions

```
# Validation success
✓ Manifest: add-jwt-auth
  Mode: implementation
  Files: 3 validated
  Duration: 45ms

# Validation failure
✗ Manifest: add-jwt-auth
  Mode: implementation
  Errors (2):
    E300 Artifact 'AuthService.login' not defined in src/auth/service.py
    E302 Type mismatch for 'AuthService.verify': expected 'bool', found 'str'
  Duration: 38ms

# Batch summary
Validation Results: 42 manifests
  Passed: 40
  Failed: 2
  Skipped: 3 (superseded)
  Duration: 1.2s
```

## Argument Parsing

Use `argparse` (stdlib, no external deps). The parser is built in `cli/main.py`:

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="maid",
        description="MAID Runner - Manifest-driven AI Development validator",
    )
    subparsers = parser.add_subparsers(dest="command")

    # maid validate
    validate_parser = subparsers.add_parser("validate", help="Validate manifests")
    validate_parser.add_argument("manifest_path", nargs="?")
    validate_parser.add_argument("--mode", default="implementation", choices=["behavioral", "implementation"])
    validate_parser.add_argument("--manifest-dir", default="manifests/")
    validate_parser.add_argument("--no-chain", action="store_true")
    validate_parser.add_argument("--coherence", action="store_true")
    validate_parser.add_argument("--coherence-only", action="store_true")
    validate_parser.add_argument("--json", action="store_true")
    validate_parser.add_argument("--quiet", action="store_true")
    validate_parser.add_argument("--watch", action="store_true")
    validate_parser.add_argument("--watch-all", action="store_true")
    validate_parser.set_defaults(func=cmd_validate)

    # ... similar for other commands

    return parser
```

## Error Handling

All CLI commands follow the same error handling pattern:

```python
def cmd_example(args: argparse.Namespace) -> int:
    try:
        # Call library API
        result = some_library_function(args.input)
        # Format and print
        print(format_result(result, json_mode=args.json))
        return 0 if result.success else 1
    except ManifestLoadError as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 2
    except UnsupportedLanguageError as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        if args.json:
            print(json.dumps({"error": f"Internal error: {e}"}))
        else:
            print(f"Internal error: {e}", file=sys.stderr)
        return 2
```
