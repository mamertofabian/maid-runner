# Coherence Validation

Coherence validation ensures architectural integrity by validating new manifests against the existing system architecture. It prevents duplicates, detects signature conflicts, and maintains consistency across the codebase.

## CLI Usage

```bash
# Validate with coherence checks (alongside standard validation)
uv run maid validate --coherence manifests/task-XXX.manifest.json

# Coherence-only mode (skip standard validation)
uv run maid validate --coherence-only manifests/task-XXX.manifest.json

# Verbose mode with detailed suggestions
uv run maid validate --coherence --verbose manifests/task-XXX.manifest.json

# JSON output for CI/CD pipelines
uv run maid validate --coherence-only --format json manifests/task-XXX.manifest.json
```

## Validation Checks

Coherence validation runs 7 architectural checks:

1. **Duplicate Artifact Detection** - Prevents redefining existing artifacts
2. **Signature Conflict Detection** - Detects same-name artifacts with different signatures
3. **Module Boundary Validation** - Ensures artifacts stay within module bounds
4. **Naming Convention Compliance** - Checks naming patterns against system norms
5. **Dependency Availability** - Verifies dependencies exist before use
6. **Pattern Consistency** - Validates against established architectural patterns
7. **Architectural Constraint Validation** - Enforces system-wide rules (configurable)

## JSON Output Format

When using `--format json`, coherence validation outputs structured JSON for CI/CD integration:

```json
{
  "manifest": "manifests/task-042.manifest.json",
  "valid": false,
  "summary": {
    "total_issues": 2,
    "errors": 1,
    "warnings": 1
  },
  "issues": [
    {
      "type": "DUPLICATE",
      "severity": "error",
      "message": "Function foo already declared in task-050",
      "location": "maid_runner/example.py:foo",
      "suggestion": "Use supersedes to explicitly replace the previous declaration"
    },
    {
      "type": "NAMING",
      "severity": "warning",
      "message": "Function FooBar does not follow snake_case convention",
      "location": "maid_runner/example.py:FooBar",
      "suggestion": "Rename to foo_bar to match codebase conventions"
    }
  ]
}
```

## Pre-Commit Hook Integration

Add coherence validation to your pre-commit workflow:

```bash
#!/bin/bash
# .git/hooks/pre-commit

# Validate manifests with coherence checks
for manifest in $(git diff --cached --name-only | grep '\.manifest\.json$'); do
  if ! uv run maid validate --coherence "$manifest"; then
    echo "Coherence validation failed for $manifest"
    exit 1
  fi
done
```

Make the hook executable:
```bash
chmod +x .git/hooks/pre-commit
```

## CI/CD Integration

### GitHub Actions

```yaml
# .github/workflows/validate.yml
name: MAID Validation

on:
  pull_request:
    paths:
      - 'manifests/*.manifest.json'
      - 'maid_runner/**/*.py'

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install uv
        run: pip install uv

      - name: Install dependencies
        run: uv sync

      - name: Validate all manifests with coherence
        run: uv run maid validate --coherence

      - name: Validate changed manifests (JSON output)
        run: |
          for manifest in $(git diff --name-only origin/main...HEAD | grep '\.manifest\.json$'); do
            echo "Validating $manifest"
            uv run maid validate --coherence "$manifest" --format json
          done
```

### GitLab CI

```yaml
# .gitlab-ci.yml
maid-validation:
  stage: test
  script:
    - pip install uv
    - uv sync
    - uv run maid validate --coherence
  only:
    changes:
      - manifests/*.manifest.json
      - maid_runner/**/*.py
```

## Architectural Constraint Configuration

Custom architectural constraints can be defined in `.maid-constraints.json`:

```json
{
  "version": "1",
  "enabled": true,
  "rules": [
    {
      "name": "no-direct-db-access-in-controllers",
      "description": "Controllers should not directly access database modules",
      "pattern": {
        "source_module": "controllers",
        "forbidden_dependency": "database"
      },
      "severity": "error",
      "suggestion": "Use repository pattern for data access"
    },
    {
      "name": "services-must-use-interfaces",
      "description": "Service classes should depend on interfaces, not implementations",
      "pattern": {
        "source_type": "class",
        "source_suffix": "Service",
        "required_dependency_suffix": "Interface"
      },
      "severity": "warning",
      "suggestion": "Inject interface dependencies for better testability"
    }
  ]
}
```

## Programmatic Usage

```python
from pathlib import Path
from maid_runner.coherence import (
    CoherenceValidator,
    CoherenceResult,
    format_coherence_result,
)

# Create validator
validator = CoherenceValidator(manifest_dir=Path("manifests"))

# Run validation
result = validator.validate(Path("manifests/task-042.manifest.json"))

# Check result
if not result.valid:
    print(f"Validation failed with {result.errors} errors")
    for issue in result.issues:
        print(f"  [{issue.severity.value}] {issue.message}")
        if issue.suggestion:
            print(f"    Suggestion: {issue.suggestion}")
```

## Performance

Coherence validation is optimized for speed:
- Target: <1s per manifest validation
- Uses system snapshot for fast artifact lookup
- Uses knowledge graph for efficient relationship queries
- Results are cached when using `--use-cache`
