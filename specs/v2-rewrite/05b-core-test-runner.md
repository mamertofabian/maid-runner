# MAID Runner v2 - Core Test Runner Module

**References:** [01-architecture.md](01-architecture.md), [03-data-types.md](03-data-types.md), [04-core-manifest.md](04-core-manifest.md)

## Module Location

`maid_runner/core/test_runner.py`

## Purpose

Executes validation commands from manifests. Supports individual manifest tests, batch execution across all manifests, and intelligent test batching for performance.

## Public API

```python
def run_tests(
    manifest_dir: str | Path = "manifests/",
    *,
    fail_fast: bool = False,
    batch: bool | None = None,
    project_root: str | Path = ".",
) -> BatchTestResult:
    """Run validation commands from all active manifests.

    Args:
        manifest_dir: Directory containing manifests.
        fail_fast: Stop on first test failure.
        batch: Force batch mode (True), disable (False), or auto-detect (None).
        project_root: Project root for command execution.

    Returns:
        BatchTestResult with per-manifest results.
    """


def run_manifest_tests(
    manifest_path: str | Path,
    *,
    fail_fast: bool = False,
    project_root: str | Path = ".",
) -> BatchTestResult:
    """Run validation commands from a single manifest.

    Args:
        manifest_path: Path to manifest file.
        fail_fast: Stop on first command failure.
        project_root: Project root for command execution.

    Returns:
        BatchTestResult with command results.
    """


def run_command(
    command: tuple[str, ...],
    *,
    cwd: str | Path = ".",
    timeout: int = 300,
) -> TestRunResult:
    """Run a single command and capture results.

    Args:
        command: Command and arguments as tuple.
        cwd: Working directory.
        timeout: Timeout in seconds (default: 5 minutes).

    Returns:
        TestRunResult with exit code, stdout, stderr, duration.
    """
```

## Batch Mode

When multiple manifests all use pytest, batch mode combines them into a single pytest invocation for 10-20x speedup.

### Batch Detection

```python
def _can_batch(commands: list[tuple[str, ...]]) -> dict[str, list[tuple[str, ...]]]:
    """Group commands by runner for potential batching.

    Returns dict of runner -> list of commands.
    Runners that can be batched: pytest, vitest.

    Example:
        Input: [
            ("pytest", "tests/test_a.py", "-v"),
            ("pytest", "tests/test_b.py", "-v"),
            ("vitest", "run", "tests/auth.test.ts"),
        ]
        Output: {
            "pytest": [("pytest", "tests/test_a.py", "-v"), ("pytest", "tests/test_b.py", "-v")],
            "vitest": [("vitest", "run", "tests/auth.test.ts")],
        }
    """
```

### Batch Execution

```python
def _batch_pytest(commands: list[tuple[str, ...]], cwd: Path) -> TestRunResult:
    """Combine multiple pytest commands into a single invocation.

    Extracts test file paths from each command and runs:
        pytest tests/test_a.py tests/test_b.py ... -v

    Deduplicates test files.
    Preserves common flags (-v, --tb=short, etc.).
    """


def _batch_vitest(commands: list[tuple[str, ...]], cwd: Path) -> TestRunResult:
    """Combine multiple vitest commands into a single invocation."""
```

### Auto-Detection

When `batch=None` (default):
- If ALL commands use the same runner (e.g., all pytest): batch mode enabled
- If commands use mixed runners: sequential mode
- If any command has non-standard flags: sequential mode (safety)

## Execution Flow

```
run_tests(manifest_dir="manifests/")
    │
    ├─ Build ManifestChain from manifest_dir
    │
    ├─ Get active manifests (excludes superseded)
    │
    ├─ Collect all validate commands:
    │   For each active manifest:
    │       For each command in manifest.validate_commands:
    │           Add (manifest_slug, command) to list
    │
    ├─ Determine batch strategy:
    │   If batch=True or auto-detect says batch:
    │       Group commands by runner
    │       Execute each group as batch
    │   Else:
    │       Execute each command sequentially
    │
    ├─ For each command/batch:
    │   ├─ Execute via subprocess
    │   ├─ Capture stdout, stderr, exit code, duration
    │   ├─ Build TestRunResult
    │   └─ If fail_fast and exit_code != 0: stop
    │
    └─ Aggregate into BatchTestResult
```

## Command Validation

Before executing, validate that commands are executable:

```python
def _validate_command(command: tuple[str, ...], cwd: Path) -> str | None:
    """Check if a command's executable exists.

    Returns warning message if executable not found, None if OK.

    Checks:
    - If command starts with "pytest", "python", "uv": check PATH
    - If command starts with "vitest", "npx": check PATH + node_modules/.bin
    - For "uv run ...": check that uv is installed
    """
```

## Subprocess Execution

```python
def _execute(
    command: tuple[str, ...],
    cwd: Path,
    timeout: int,
) -> TestRunResult:
    """Execute a command via subprocess.

    Uses subprocess.run with:
    - capture_output=True
    - text=True
    - cwd=cwd
    - timeout=timeout
    - env=os.environ (inherits current environment)

    On timeout: returns TestRunResult with exit_code=-1
    On other errors: returns TestRunResult with exit_code=-2
    """
```

## Watch Mode Integration

Watch mode is NOT in this module (it's in the CLI layer since it involves I/O).
The test runner provides the execution primitives; the CLI orchestrates re-runs.

The CLI watch implementation calls:
1. `run_manifest_tests()` on file change (single-manifest watch)
2. Identifies affected manifests, then calls `run_manifest_tests()` for each (multi-manifest watch)

## Test File Extraction

```python
def extract_test_files(commands: tuple[tuple[str, ...], ...]) -> list[str]:
    """Extract test file paths from validation commands.

    Examples:
        ("pytest", "tests/test_auth.py", "-v") -> ["tests/test_auth.py"]
        ("vitest", "run", "tests/auth.test.ts") -> ["tests/auth.test.ts"]
        ("pytest", "tests/", "-v") -> [] (directory, not specific file)
        ("uv", "run", "python", "-m", "pytest", "tests/test_x.py") -> ["tests/test_x.py"]
    """
```

This is used by behavioral validation to find test files for artifact reference checking.
