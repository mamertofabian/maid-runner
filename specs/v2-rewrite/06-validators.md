# MAID Runner v2 - Validator Plugin Architecture

**References:** [01-architecture.md](01-architecture.md), [03-data-types.md](03-data-types.md), [05-core-validation.md](05-core-validation.md)

## Module Location

- `maid_runner/validators/__init__.py` - Re-exports, auto-registration trigger
- `maid_runner/validators/registry.py` - ValidatorRegistry, auto_register(), UnsupportedLanguageError
- `maid_runner/validators/base.py` - BaseValidator ABC
- `maid_runner/validators/python.py` - Python validator (always available)
- `maid_runner/validators/typescript.py` - TypeScript validator (optional)
- `maid_runner/validators/svelte.py` - Svelte validator (optional)

## Design Principles

1. **Validators are self-contained** - They import only pure value types from `core.types` (enums and frozen dataclasses like `ArtifactKind`, `ArgSpec`)
2. **Validators receive strings, return data** - Input: source code + file path. Output: list of FoundArtifact.
3. **Plugin architecture** - New languages are added by implementing BaseValidator and registering
4. **Optional dependencies** - TypeScript/Svelte validators fail gracefully if tree-sitter not installed
5. **Two collection modes** - Implementation (find definitions) and behavioral (find references/usage)

## BaseValidator ABC (`validators/base.py`)

```python
from abc import ABC, abstractmethod
from pathlib import Path
from .base import FoundArtifact, CollectionResult


class BaseValidator(ABC):
    """Abstract base for language-specific code validators.

    Validators analyze source code to find artifact definitions (for
    implementation validation) or artifact references (for behavioral
    validation). They are stateless and can be reused across files.

    Subclasses MUST implement:
    - collect_implementation_artifacts()
    - collect_behavioral_artifacts()
    - supported_extensions() (class property)

    Subclasses MAY override:
    - can_validate() for custom file filtering
    """

    @classmethod
    @abstractmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        """File extensions this validator handles.

        Returns:
            Tuple of extensions including the dot, e.g. (".py",)
        """

    def can_validate(self, file_path: str | Path) -> bool:
        """Check if this validator can handle the given file.

        Default implementation checks file extension against
        supported_extensions(). Override for custom logic.
        """
        return Path(file_path).suffix in self.supported_extensions()

    @abstractmethod
    def collect_implementation_artifacts(
        self,
        source: str,
        file_path: str | Path,
    ) -> CollectionResult:
        """Collect artifact DEFINITIONS from source code.

        Analyzes the AST to find all classes, functions, methods,
        attributes, etc. defined in the source file.

        Args:
            source: Source code as string.
            file_path: Path to source file (for error messages).

        Returns:
            CollectionResult with list of FoundArtifact objects.
        """

    @abstractmethod
    def collect_behavioral_artifacts(
        self,
        source: str,
        file_path: str | Path,
    ) -> CollectionResult:
        """Collect artifact REFERENCES from source code (typically tests).

        Analyzes the AST to find all artifact names that are imported,
        called, or referenced. Used for behavioral validation to check
        that tests actually use the declared artifacts.

        Args:
            source: Source code as string.
            file_path: Path to source file (for error messages).

        Returns:
            CollectionResult with list of FoundArtifact representing references.
        """

    def generate_snapshot(
        self,
        source: str,
        file_path: str | Path,
    ) -> list[dict]:
        """Generate artifact declarations for snapshot manifest.

        Default implementation calls collect_implementation_artifacts()
        and converts FoundArtifacts to manifest-format dicts.
        Override for language-specific snapshot formatting.

        Returns:
            List of artifact dicts suitable for manifest YAML.
        """
        result = self.collect_implementation_artifacts(source, file_path)
        return [self._artifact_to_dict(a) for a in result.artifacts if not a.is_private]

    def generate_test_stub(
        self,
        artifacts: list[FoundArtifact],
        file_path: str | Path,
    ) -> str:
        """Generate test stub code for the given artifacts.

        Default implementation returns empty string.
        Override to generate language-specific test templates.

        Returns:
            Test file content as string.
        """
        return ""

    @staticmethod
    def _artifact_to_dict(artifact: FoundArtifact) -> dict:
        """Convert FoundArtifact to manifest-format dict."""
        d: dict = {"kind": artifact.kind.value, "name": artifact.name}
        if artifact.of:
            d["of"] = artifact.of
        if artifact.args:
            d["args"] = [
                {k: v for k, v in {"name": a.name, "type": a.type, "default": a.default}.items() if v is not None}
                for a in artifact.args
            ]
        if artifact.returns:
            d["returns"] = artifact.returns
        if artifact.is_async:
            d["async"] = True
        if artifact.bases:
            d["bases"] = list(artifact.bases)
        if artifact.type_annotation:
            d["type"] = artifact.type_annotation
        return d
```

## Validator Registry (`validators/registry.py`)

The registry lives in a separate `registry.py` module (not `__init__.py`) to avoid circular imports and keep concerns separated. An `auto_register()` function handles conditional registration of built-in validators.

```python
# validators/registry.py

class UnsupportedLanguageError(Exception):
    """No validator available for a file extension."""
    def __init__(self, extension: str):
        self.extension = extension
        super().__init__(
            f"No validator for '{extension}' files. "
            f"Install optional dependencies? (e.g., maid-runner[typescript])"
        )


class ValidatorRegistry:
    """Registry of language validators.

    Validators register themselves via auto_register() or manual
    registration. The registry provides lookup by file extension.
    """

    _validators: dict[str, type[BaseValidator]] = {}
    _instances: dict[str, BaseValidator] = {}  # Cached instances

    @classmethod
    def register(cls, validator_class: type[BaseValidator]) -> None:
        """Register a validator for its supported extensions."""
        for ext in validator_class.supported_extensions():
            cls._validators[ext] = validator_class

    @classmethod
    def get(cls, file_path: str | Path) -> BaseValidator:
        """Get a validator instance for the given file.

        Raises:
            UnsupportedLanguageError: If no validator registered for extension.
        """
        ext = Path(file_path).suffix
        if ext not in cls._validators:
            raise UnsupportedLanguageError(ext)
        if ext not in cls._instances:
            cls._instances[ext] = cls._validators[ext]()
        return cls._instances[ext]

    @classmethod
    def has_validator(cls, file_path: str | Path) -> bool:
        """Check if a validator is available for the given file."""
        return Path(file_path).suffix in cls._validators

    @classmethod
    def has_validator_for_extension(cls, ext: str) -> bool:
        """Check if a validator is registered for an extension."""
        return ext in cls._validators

    @classmethod
    def supported_extensions(cls) -> set[str]:
        """All file extensions with registered validators."""
        return set(cls._validators.keys())

    @classmethod
    def clear(cls) -> None:
        """Clear all registrations. Used in testing."""
        cls._validators.clear()
        cls._instances.clear()


def auto_register() -> None:
    """Auto-register all built-in validators.

    Python is always available. TypeScript and Svelte are conditional
    on tree-sitter being installed.
    """
    from .python import PythonValidator
    ValidatorRegistry.register(PythonValidator)

    try:
        from .typescript import TypeScriptValidator
        ValidatorRegistry.register(TypeScriptValidator)
    except ImportError:
        pass

    try:
        from .svelte import SvelteValidator
        ValidatorRegistry.register(SvelteValidator)
    except ImportError:
        pass
```

Callers (e.g., `core/validate.py`) invoke `auto_register()` at module load time to ensure validators are available before any validation runs.

## Python Validator (`validators/python.py`)

### Overview

Uses Python's built-in `ast` module. Zero external dependencies.

```python
class PythonValidator(BaseValidator):
    """Validates Python source files using stdlib ast module."""

    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".py",)
```

### Implementation Artifact Collection

Port from current `manifest_validator.py`'s `_ArtifactCollector` AST visitor. Must detect:

| Artifact | AST Node | Notes |
|----------|----------|-------|
| Class | `ast.ClassDef` | Extract name, bases, decorators |
| Function | `ast.FunctionDef`, `ast.AsyncFunctionDef` | Module-level only |
| Method | `ast.FunctionDef` inside `ast.ClassDef` | Filter self/cls params |
| Attribute (module) | `ast.Assign`, `ast.AnnAssign` at module level | Type aliases, constants |
| Attribute (class) | `ast.Assign`, `ast.AnnAssign` in `__init__` or class body | Instance and class attrs |
| Enum | `ast.ClassDef` with `enum.Enum` base | Treated as class with bases |

### Behavioral Artifact Collection

Port from current `_behavioral_validation.py`. Must detect artifact REFERENCES:

| Reference | AST Nodes | Notes |
|-----------|-----------|-------|
| Import | `ast.Import`, `ast.ImportFrom` | Name is imported |
| Function call | `ast.Call` with `ast.Name` | Function is called |
| Method call | `ast.Call` with `ast.Attribute` | method.name is called |
| Attribute access | `ast.Attribute` | obj.attr is accessed |
| Name reference | `ast.Name` | Name appears in expression |
| Class instantiation | `ast.Call` with `ast.Name` | ClassName() |

### Parameter Handling

```python
def _extract_args(self, func_node: ast.FunctionDef, is_method: bool) -> tuple[ArgSpec, ...]:
    """Extract function arguments, filtering self/cls for methods.

    Rules:
    - Regular methods: filter 'self' from first position
    - @classmethod: filter 'cls' from first position
    - @staticmethod: no filtering
    - Module-level functions: no filtering
    - *args and **kwargs: include with their names
    """
```

### Type Annotation Extraction

```python
def _annotation_to_str(self, node: ast.expr | None) -> str | None:
    """Convert AST annotation node to string representation.

    Handles:
    - ast.Name -> "str", "int", etc.
    - ast.Subscript -> "list[int]", "Dict[str, Any]", etc.
    - ast.Attribute -> "typing.Optional", etc.
    - ast.BinOp with | -> "str | None" (PEP 604)
    - ast.Constant -> string/number literals
    - ast.Tuple -> tuple of types
    - None -> None
    """
```

### Test Stub Generation

```python
def generate_test_stub(
    self,
    artifacts: list[FoundArtifact],
    file_path: str | Path,
) -> str:
    """Generate pytest test stub for Python artifacts.

    Template:
    ```python
    import pytest
    from {module} import {class_or_function}

    class Test{ClassName}:
        def test_{method_name}(self):
            # TODO: implement test
            pass
    ```
    """
```

## TypeScript Validator (`validators/typescript.py`)

### Overview

Uses `tree-sitter` with `tree-sitter-typescript` grammar. Optional dependency.

```python
class TypeScriptValidator(BaseValidator):
    """Validates TypeScript/JavaScript source files using tree-sitter."""

    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".ts", ".tsx", ".js", ".jsx")

    def __init__(self):
        """Initialize tree-sitter parser with TypeScript and TSX grammars.

        Raises:
            ImportError: If tree-sitter or tree-sitter-typescript not installed.
        """
```

### Implementation Artifact Collection

Port from current `typescript_validator.py`. Must detect:

| Artifact | Tree-sitter Node | Notes |
|----------|-------------------|-------|
| Class | `class_declaration` | Name, heritage (extends/implements) |
| Function | `function_declaration`, `lexical_declaration` with arrow | Module-scope only |
| Method | `method_definition` inside class | Including getters/setters |
| Interface | `interface_declaration` | TypeScript only |
| Type alias | `type_alias_declaration` | `type Foo = ...` |
| Enum | `enum_declaration` | Regular and const enums |
| Namespace | `module` (ambient) | `namespace Foo {}` |
| Attribute (class) | `public_field_definition` | Class properties |
| Attribute (module) | `lexical_declaration` (const/let) | Module-level variables |

### TSX Support

- Use TSX grammar for `.tsx` and `.jsx` files
- Use TypeScript grammar for `.ts` and `.js` files
- JSX elements detected as component usage (for behavioral validation)

### Key TypeScript-Specific Behaviors to Preserve

1. **Arrow function class properties** - `login = async (user: string) => {...}` detected as method of enclosing class

2. **Variable-to-class mapping** - `const AuthProvider: React.FC<Props> = ({children}) => {...}` maps `AuthProvider` as a function with the arrow function's parameters

3. **Positional argument tracking** - TypeScript arguments tracked by position and name

4. **Private member filtering** - Members prefixed with `_` or `#` (ES private) or TypeScript `private` keyword are all considered private

5. **Object property arrows excluded** - Arrow functions inside object literals (`{handler: () => {}}`) are NOT module-scope functions

6. **Module-scope arrow functions** - `const foo = () => {}` at module scope IS a function

7. **Generator function detection** - `function* gen()` and `async function* gen()` detected

8. **JSX element detection** - `<Component />` in JSX/TSX recognized for behavioral validation

### Test Stub Generation

```python
def generate_test_stub(
    self,
    artifacts: list[FoundArtifact],
    file_path: str | Path,
) -> str:
    """Generate Vitest/Jest test stub for TypeScript artifacts.

    Template:
    ```typescript
    import { describe, it, expect } from 'vitest'
    import { ClassName } from './{module}'

    describe('ClassName', () => {
      it('should {method_name}', () => {
        // TODO: implement test
      })
    })
    ```
    """
```

## Svelte Validator (`validators/svelte.py`)

### Overview

Extracts `<script>` content from Svelte files, then delegates to TypeScript validator.

```python
class SvelteValidator(BaseValidator):
    """Validates Svelte component files.

    Extracts TypeScript/JavaScript from <script> tags and delegates
    to TypeScriptValidator for artifact collection.
    """

    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".svelte",)

    def __init__(self):
        """Initialize with a TypeScriptValidator for script analysis."""
        self._ts_validator = TypeScriptValidator()
```

### Script Extraction

```python
def _extract_script(self, source: str) -> tuple[str, str]:
    """Extract script content and determine language.

    Looks for:
    - <script lang="ts"> ... </script>  -> ("content", "typescript")
    - <script> ... </script>             -> ("content", "javascript")
    - <script context="module"> ... </script> -> module script

    Returns:
        Tuple of (script_content, language).
    """
```

### Delegation Pattern

```python
def collect_implementation_artifacts(self, source, file_path):
    script_content, lang = self._extract_script(source)
    if not script_content:
        return CollectionResult(artifacts=[], language="svelte", file_path=str(file_path))
    # Delegate to TypeScript validator
    return self._ts_validator.collect_implementation_artifacts(script_content, file_path)
```

## Adding a New Language Validator

To add support for a new language (e.g., Go):

### Step 1: Create validator module

```python
# maid_runner/validators/go.py
from .base import BaseValidator, CollectionResult, FoundArtifact

class GoValidator(BaseValidator):
    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".go",)

    def collect_implementation_artifacts(self, source, file_path):
        # Use tree-sitter-go or custom parser
        ...

    def collect_behavioral_artifacts(self, source, file_path):
        ...
```

### Step 2: Register in `registry.py`

```python
# Add to auto_register() in validators/registry.py
def auto_register() -> None:
    # ... existing registrations ...

    try:
        from .go import GoValidator
        ValidatorRegistry.register(GoValidator)
    except ImportError:
        pass
```

### Step 3: Add optional dependency

```toml
# pyproject.toml
[project.optional-dependencies]
go = ["tree-sitter>=0.23", "tree-sitter-go>=0.23"]
all = ["maid-runner[typescript,svelte,go]"]
```

## Validator Contract

All validators MUST satisfy these invariants:

1. **Deterministic** - Same source code always produces same artifacts
2. **No side effects** - Validators don't read files, only analyze provided source strings
3. **Graceful on parse errors** - Return partial results + errors in CollectionResult, never raise
4. **Private filtering consistent** - `_name` and `__name` are always private
5. **Position info when available** - Line/column set on FoundArtifact when AST provides it
6. **Empty source -> empty result** - Empty string input returns empty artifact list, no errors
