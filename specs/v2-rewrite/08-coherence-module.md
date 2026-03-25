# MAID Runner v2 - Coherence Validation Module

**References:** [01-architecture.md](01-architecture.md), [03-data-types.md](03-data-types.md), [07-graph-module.md](07-graph-module.md)

## Module Location

- `maid_runner/coherence/__init__.py` - Re-exports
- `maid_runner/coherence/engine.py` - CoherenceEngine orchestrator
- `maid_runner/coherence/result.py` - Result types
- `maid_runner/coherence/checks/` - Individual check implementations

## Purpose

Coherence validation enforces architectural integrity rules that go beyond structural validation. While the core validator checks "does the code match the manifest?", coherence checks ask "is the manifest ecosystem internally consistent?"

Seven architectural checks:
1. **Duplicate detection** - Same artifact declared in multiple manifests
2. **Signature conflicts** - Same name, different signatures across manifests
3. **Module boundary** - Artifacts accessing internals of other modules
4. **Naming conventions** - Consistent naming patterns
5. **Dependency availability** - Referenced dependencies exist
6. **Pattern consistency** - Architectural pattern violations
7. **Constraint enforcement** - Custom project constraints

## Result Types (`coherence/result.py`)

### IssueSeverity (Enum)

```python
class IssueSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
```

### IssueType (Enum)

```python
class IssueType(str, Enum):
    DUPLICATE = "duplicate"
    SIGNATURE_CONFLICT = "signature_conflict"
    BOUNDARY_VIOLATION = "boundary_violation"
    NAMING = "naming"
    DEPENDENCY = "dependency"
    PATTERN = "pattern"
    CONSTRAINT = "constraint"
```

### CoherenceIssue (Dataclass)

```python
@dataclass(frozen=True)
class CoherenceIssue:
    """A single coherence issue found during analysis."""
    issue_type: IssueType
    severity: IssueSeverity
    message: str
    file: str | None = None
    artifact: str | None = None
    manifests: tuple[str, ...] = ()    # Manifest slugs involved
    suggestion: str | None = None       # Actionable fix suggestion

    def to_dict(self) -> dict:
        d = {
            "type": self.issue_type.value,
            "severity": self.severity.value,
            "message": self.message,
        }
        if self.file:
            d["file"] = self.file
        if self.artifact:
            d["artifact"] = self.artifact
        if self.manifests:
            d["manifests"] = list(self.manifests)
        if self.suggestion:
            d["suggestion"] = self.suggestion
        return d
```

### CoherenceResult (Dataclass)

```python
@dataclass
class CoherenceResult:
    """Complete result of coherence validation."""
    issues: list[CoherenceIssue] = field(default_factory=list)
    checks_run: list[str] = field(default_factory=list)  # Names of checks executed
    duration_ms: float | None = None

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.WARNING)

    @property
    def success(self) -> bool:
        return self.error_count == 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "errors": self.error_count,
            "warnings": self.warning_count,
            "checks_run": self.checks_run,
            "issues": [i.to_dict() for i in self.issues],
            "duration_ms": self.duration_ms,
        }

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict(), indent=2)
```

## Check Interface (`coherence/checks/base.py`)

```python
from abc import ABC, abstractmethod

class BaseCheck(ABC):
    """Abstract base for coherence checks.

    Each check analyzes the knowledge graph for a specific type of
    architectural issue. Checks are stateless and independent.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this check."""

    @abstractmethod
    def run(self, graph: KnowledgeGraph, chain: ManifestChain) -> list[CoherenceIssue]:
        """Execute the check and return any issues found.

        Args:
            graph: The knowledge graph built from the manifest chain.
            chain: The manifest chain for additional context.

        Returns:
            List of issues found (empty if check passes).
        """
```

## Individual Checks

### Duplicate Check (`checks/duplicate.py`)

```python
class DuplicateCheck(BaseCheck):
    """Detects artifacts declared in multiple non-superseding manifests.

    Flags:
    - Same artifact name declared in different manifests for the same file
    - Same artifact name in different files (potential naming confusion)

    Severity: WARNING for cross-file, ERROR for same-file duplicates.
    """

    @property
    def name(self) -> str:
        return "duplicate"

    def run(self, graph, chain):
        # Algorithm:
        # 1. Group all DECLARES edges by artifact name
        # 2. For each group with multiple manifests:
        #    - If same file: ERROR (actual conflict)
        #    - If different files: WARNING (naming confusion)
        # 3. Exclude superseded manifest pairs
```

### Signature Check (`checks/signature.py`)

```python
class SignatureCheck(BaseCheck):
    """Detects conflicting function/method signatures across manifests.

    When multiple manifests declare the same function name but with
    different argument lists or return types, this is likely a conflict.

    Severity: ERROR for conflicting signatures in active manifests.
    """

    @property
    def name(self) -> str:
        return "signature"

    def run(self, graph, chain):
        # Algorithm:
        # 1. Group artifacts by qualified name (class.method or function)
        # 2. For each group, compare signatures:
        #    - Different arg count -> ERROR
        #    - Different arg names -> WARNING
        #    - Different arg types -> WARNING
        #    - Different return type -> WARNING
```

### Module Boundary Check (`checks/boundary.py`)

```python
class ModuleBoundaryCheck(BaseCheck):
    """Detects violations of module encapsulation.

    Checks that manifests don't declare artifacts that reach into
    private internals of other modules.

    Rules:
    - Files starting with _ are module-private
    - Artifacts in private files shouldn't be referenced by external manifests
    - Cross-module imports should use public interfaces

    Severity: WARNING for potential boundary violations.
    """

    @property
    def name(self) -> str:
        return "boundary"
```

### Naming Check (`checks/naming.py`)

```python
class NamingCheck(BaseCheck):
    """Checks naming convention consistency.

    Rules checked:
    - Python: snake_case for functions/methods, PascalCase for classes
    - TypeScript: camelCase for functions, PascalCase for classes/interfaces
    - Manifest slugs: kebab-case
    - Consistency within a module (don't mix styles)

    Severity: INFO for style inconsistencies, WARNING for violations.
    """

    @property
    def name(self) -> str:
        return "naming"
```

### Dependency Check (`checks/dependency.py`)

```python
class DependencyCheck(BaseCheck):
    """Verifies that declared dependencies are available.

    Checks:
    - Files in files.read actually exist on disk
    - Base classes referenced in artifacts exist somewhere in the chain
    - Validation commands reference existing test files

    Severity: ERROR for missing dependencies.
    """

    @property
    def name(self) -> str:
        return "dependency"
```

### Pattern Check (`checks/pattern.py`)

```python
class PatternCheck(BaseCheck):
    """Checks for architectural pattern consistency.

    Rules:
    - If a module has a validator pattern, new validators follow it
    - If a module uses factory pattern, new factories follow it
    - Detect anti-patterns (god classes, circular imports)

    Severity: WARNING for pattern violations, INFO for suggestions.
    """

    @property
    def name(self) -> str:
        return "pattern"
```

### Constraint Check (`checks/constraint.py`)

```python
class ConstraintCheck(BaseCheck):
    """Enforces custom architectural constraints.

    Reads constraints from .maidrc.yaml if present:

    ```yaml
    coherence:
      constraints:
        - type: max_artifacts_per_file
          value: 20
          severity: warning
        - type: no_cross_module_access
          modules: [auth, billing]
          severity: error
    ```

    Severity: Configurable per constraint.
    """

    @property
    def name(self) -> str:
        return "constraint"
```

## Check Registry (`checks/__init__.py`)

```python
# Default enabled checks
DEFAULT_CHECKS: list[type[BaseCheck]] = [
    DuplicateCheck,
    SignatureCheck,
    ModuleBoundaryCheck,
    NamingCheck,
    DependencyCheck,
    PatternCheck,
    ConstraintCheck,
]


def get_checks(
    enabled: list[str] | None = None,
    disabled: list[str] | None = None,
) -> list[BaseCheck]:
    """Get check instances, optionally filtering.

    Args:
        enabled: If set, only run these checks (by name).
        disabled: If set, exclude these checks (by name).

    Returns:
        List of BaseCheck instances to run.
    """
```

## CoherenceEngine (`coherence/engine.py`)

```python
class CoherenceEngine:
    """Orchestrates coherence validation.

    Builds knowledge graph, runs configured checks, aggregates results.

    Usage:
        engine = CoherenceEngine()
        result = engine.validate(chain)
    """

    def __init__(
        self,
        checks: list[BaseCheck] | None = None,
    ):
        """Initialize with optional custom check list.

        Args:
            checks: Checks to run. Defaults to DEFAULT_CHECKS.
        """

    def validate(
        self,
        chain: ManifestChain,
        *,
        graph: KnowledgeGraph | None = None,
    ) -> CoherenceResult:
        """Run all configured coherence checks.

        Args:
            chain: Manifest chain to validate.
            graph: Pre-built graph (optional; built from chain if not provided).

        Returns:
            CoherenceResult with aggregated issues from all checks.
        """

    def validate_single(
        self,
        manifest: Manifest,
        chain: ManifestChain,
    ) -> CoherenceResult:
        """Run coherence checks focused on a single manifest.

        Only reports issues related to the specified manifest.
        """
```

### Engine Algorithm

```
validate(chain):
    1. Build knowledge graph from chain (or use provided graph)
    2. For each configured check:
        a. Run check.run(graph, chain)
        b. Collect returned issues
    3. Aggregate all issues into CoherenceResult
    4. Sort issues by severity (errors first), then by file, then by type
    5. Return CoherenceResult
```

## Integration Points

### With Core Validation

Coherence validation is invoked from `core/validate.py` when requested:

```python
# In ValidationEngine.validate():
if coherence_enabled:
    coherence_engine = CoherenceEngine(checks=configured_checks)
    coherence_result = coherence_engine.validate(chain)
    # Coherence issues are reported separately from validation errors
```

### With CLI

The CLI exposes coherence through two mechanisms:

1. **Flag on validate command:** `maid validate --coherence` adds coherence checks to normal validation
2. **Standalone command:** `maid coherence validate` runs only coherence checks

### With Graph Module

Coherence checks use the knowledge graph (from `graph/` module) for structural analysis. The graph is built once and passed to all checks.

## Output Format

### Text Format (CLI Default)

```
Coherence Validation Results
============================

ERRORS (2):
  [duplicate] Function 'parse_config' declared in both:
    - manifests/add-config.manifest.yaml (src/config.py)
    - manifests/refactor-utils.manifest.yaml (src/config.py)
    Suggestion: Supersede one manifest or merge declarations

  [signature] Conflicting signatures for 'validate()':
    - manifests/add-validation.manifest.yaml: validate(data: dict) -> bool
    - manifests/fix-validation.manifest.yaml: validate(data: dict, strict: bool) -> Result
    Suggestion: Update older manifest or create superseding manifest

WARNINGS (1):
  [boundary] Manifest 'add-feature' accesses private file '_helpers.py'
    in module 'src/utils/'
    Suggestion: Use public API from 'src/utils/__init__.py'

7 checks run, 2 errors, 1 warning
```

### JSON Format

```json
{
  "success": false,
  "errors": 2,
  "warnings": 1,
  "checks_run": ["duplicate", "signature", "boundary", "naming", "dependency", "pattern", "constraint"],
  "issues": [
    {
      "type": "duplicate",
      "severity": "error",
      "message": "Function 'parse_config' declared in both manifests",
      "file": "src/config.py",
      "artifact": "parse_config",
      "manifests": ["add-config", "refactor-utils"],
      "suggestion": "Supersede one manifest or merge declarations"
    }
  ]
}
```
