# MAID Runner v2 - Porting Reference

**References:** [05-core-validation.md](05-core-validation.md), [06-validators.md](06-validators.md)

## Purpose

This document captures the critical algorithms and rules from the current codebase that MUST be preserved during porting. An agent implementing v2 should use these as the behavioral specification — the rules that make the validation correct.

**Source files referenced:** Read these from the current codebase for full context when implementing.

---

## 1. Type Normalization Pipeline

**Current location:** `maid_runner/validators/_type_normalization.py`
**New location:** `maid_runner/core/_type_compare.py`

### Normalization Steps (Applied in Order)

```
Input type string
    │
    ├─ 1. Strip whitespace: "  str  " -> "str"
    ├─ 2. Remove all internal spaces: "Dict[ str , int ]" -> "Dict[str,int]"
    ├─ 3. Convert pipe unions: "str | None" -> "Union[str,None]"
    ├─ 4. Convert Optional: "Optional[str]" -> "Union[str,None]"
    ├─ 5. Sort Union members: "Union[str,None]" -> "Union[None,str]"
    └─ 6. Normalize comma spacing: "Dict[str,int]" -> "Dict[str, int]"
```

### Key Algorithm: Bracket-Aware Splitting

When splitting by delimiter (comma or pipe), respect bracket nesting:

```python
def split_by_delimiter(text: str, delimiter: str) -> list[str]:
    parts = []
    current = ""
    depth = 0
    for char in text:
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
        elif char == delimiter and depth == 0:
            parts.append(current.strip())
            current = ""
            continue
        current += char
    if current:
        parts.append(current.strip())
    return parts
```

This ensures `Dict[str, int] | None` splits at the `|` but not at the `,` inside `Dict`.

### Type Comparison Function

```python
def compare_types(manifest_type, impl_type) -> bool:
    # None handling
    if manifest_type is None and impl_type is None: return True
    if manifest_type is None or impl_type is None: return False
    # Normalize both, then string compare
    return normalize(manifest_type) == normalize(impl_type)
```

**Rule: If manifest_type is None (not specified), any impl_type is acceptable.** This is handled by the caller, not the comparison function.

---

## 2. Python AST Artifact Collection

**Current location:** `maid_runner/validators/manifest_validator.py` `_ArtifactCollector` class
**New location:** `maid_runner/validators/python.py` `PythonValidator`

### Collection Strategy

The collector is an `ast.NodeVisitor` that walks the AST tree. It maintains:

```python
# Implementation mode collections
found_classes: set[str]                    # Class names defined
found_class_bases: dict[str, list[str]]    # class -> base class names
found_functions: dict[str, list]           # func -> parameter list
found_methods: dict[str, dict[str, list]]  # class -> {method -> params}
found_attributes: dict[str|None, set]      # class|None -> attribute names
found_function_types: dict                 # func -> {parameters: [...], returns: ...}
found_method_types: dict                   # class -> {method -> {parameters: [...], returns: ...}}
variable_to_class: dict[str, str]          # variable -> class (for instance tracking)

# Behavioral mode collections (tracking usage in tests)
used_classes: set[str]                     # Classes instantiated or referenced
used_functions: set[str]                   # Functions called
used_methods: dict[str, set[str]]          # class -> methods called
used_arguments: set[str]                   # Arguments passed in calls
```

### Node Visitor Rules

#### `visit_ClassDef`
- Add class name to `found_classes`
- Extract base class names: handle `ast.Name`, `ast.Attribute`, `ast.Subscript` (for `Generic[T]`)
- Store bases in `found_class_bases`
- Track `current_class` context for nested function/assignment visitors

#### `visit_FunctionDef` / `visit_AsyncFunctionDef` (same handler)
- If at module scope (`current_class is None`): store in `found_functions`
- If inside class:
  - If has `@property` decorator: store as CLASS ATTRIBUTE (not method)
  - Otherwise: store as METHOD in `found_methods[current_class]`
- Extract parameter types with type annotations
- Extract return type annotation
- `visit_AsyncFunctionDef = visit_FunctionDef` (aliased)

#### `visit_Assign`
- At class scope:
  - `self.attr = ...` -> class attribute
  - `NAME = ...` (at class body level, not in method) -> class attribute (enum members, class constants)
- At module scope (not inside any function):
  - `NAME = ...` -> module attribute
  - `X, Y = ...` (tuple unpacking) -> module attributes X and Y
- Track `variable_to_class` mapping when RHS is a class instantiation: `x = Foo()` maps x -> Foo

#### `visit_AnnAssign`
- `name: type = value` at module scope -> module attribute
- `name: type = value` at class scope -> class attribute
- This handles dataclass fields, TypedDict fields, class-level type annotations

#### Self/Cls Filtering Rules

**Critical behavior to preserve exactly:**

```python
# When storing methods, parameters include self/cls in found_methods
# When COMPARING, self/cls are filtered out

# In _validate_method_parameters:
actual_param_names = [p for p in actual_parameters if p not in ("self", "cls")]
# OR for dict format:
actual_param_names = [p["name"] for p in actual_parameters if p.get("name") not in ("self", "cls")]
```

**Also:** Manifests MUST NOT declare `self` as a parameter. If they do, it's an immediate error:
```
"Manifest error: Parameter 'self' should not be explicitly declared in method '{name}'"
```

#### Property Detection

Functions with `@property` decorator are treated as class ATTRIBUTES, not methods:
```python
def _has_property_decorator(node):
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Name) and decorator.id == "property":
            return True
    return False
```

### AST Type Annotation Extraction

**Current location:** `maid_runner/validators/_type_annotation.py`

Convert AST nodes to type strings:

| AST Node | Output |
|----------|--------|
| `ast.Name(id="str")` | `"str"` |
| `ast.Constant(value="ForwardRef")` | `"ForwardRef"` |
| `ast.Subscript(List, str)` | `"List[str]"` |
| `ast.Subscript(Dict, (str, int))` | `"Dict[str, int]"` |
| `ast.Attribute(typing, Optional)` | `"typing.Optional"` |
| `ast.BinOp(str, BitOr, None)` | `"Union[str, None]"` |
| `ast.Ellipsis` | `"..."` |
| Anything else | `ast.unparse(node)` fallback |

### Base Class Name Extraction

For `class Foo(Bar, Generic[T], module.Base)`:

```python
def extract_base_class_name(base):
    if isinstance(base, ast.Name):        return base.id           # "Bar"
    elif isinstance(base, ast.Attribute): return "module.Base"     # walk Attribute chain
    elif isinstance(base, ast.Subscript): return base.value.id     # "Generic" (strip [T])
```

---

## 3. Strict vs Permissive Validation

**Current location:** `maid_runner/validators/_artifact_validation.py` `_validate_no_unexpected_artifacts`

### Strict Mode (creatableFiles / files.create)

After validating all expected artifacts exist, check for UNEXPECTED public artifacts:

```python
# Build expected sets from manifest
expected_classes = {a.name for a in artifacts if a.kind in (CLASS, INTERFACE, TYPE, ENUM, NAMESPACE)}
expected_functions = {a.name for a in artifacts if a.kind == FUNCTION and a.of is None}
expected_methods = {}  # class -> set of method names

# Check code
unexpected_classes = {c for c in found_classes if not c.startswith("_")} - expected_classes
unexpected_functions = {f for f in found_functions if not f.startswith("_")} - expected_functions
for class_name, methods in found_methods.items():
    if class_name.startswith("_"): continue
    public_methods = {m for m in methods if not m.startswith("_")}
    unexpected = public_methods - expected_methods.get(class_name, set())
    # Report unexpected
```

**Key rule:** Private artifacts (starting with `_`) are ALWAYS allowed, even in strict mode.

### Test File Exception

**Strict mode is skipped for test files.** Detection is path-based:

```python
def is_test_file(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if normalized.startswith("./"): normalized = normalized[2:]
    if normalized.startswith("tests/") or "/tests/" in normalized: return True
    return normalized.split("/")[-1].startswith("test_")
```

### Permissive Mode (editableFiles / files.edit)

Only checks that expected artifacts EXIST. Additional public artifacts are silently allowed.

---

## 4. Behavioral Validation Logic

**Current location:** `maid_runner/cli/_behavioral_validation.py`

### What Counts as "Using" an Artifact in a Test

The behavioral collector tracks usage through these AST patterns:

**Classes are "used" when:**
- Imported (`from module import ClassName`)
- Instantiated (`obj = ClassName()`)
- Referenced as a type (`isinstance(x, ClassName)`)
- Assigned to variable (`ref = ClassName`) — class itself, not instance
- Used as base class in test code

**Functions are "used" when:**
- Imported and called (`func()`)
- Referenced by name in an expression

**Methods are "used" when:**
- Called on an instance (`obj.method()`)
- The class is used AND the method name appears as an attribute call

**Arguments are "used" when:**
- Passed as keyword args (`func(name="test")`)
- Passed positionally (`func("test")`) — tracked as `__positional__`
- The `__positional__` sentinel means "positional args were used, don't enforce keyword names"

### Imported Test Files

Tests can be split across files. The main test file imports helper test files:

```python
# test_feature.py
from _test_feature_helpers import *
```

The validator follows these imports and collects artifacts from imported test files too. Detection:
- Look for `from _test_xxx import` patterns in the test file AST
- Resolve the imported file path relative to the test file
- Collect artifacts from that file as well

### Behavioral Validation Scope

**Critical rule:** Behavioral validation checks artifacts from the CURRENT manifest only, NOT the merged chain. This is intentional — behavioral tests should test what the current task declares, not accumulated state.

---

## 5. TypeScript Validator Patterns

**Current location:** `maid_runner/validators/typescript_validator.py` (1,677 lines)
**New location:** `maid_runner/validators/typescript.py`

### Tree-Sitter Setup

```python
import tree_sitter_typescript as ts_typescript
from tree_sitter import Language, Parser

# Two grammars:
TS_LANGUAGE = Language(ts_typescript.language_typescript())   # .ts, .js
TSX_LANGUAGE = Language(ts_typescript.language_tsx())         # .tsx, .jsx

# Choose grammar based on extension:
if ext in (".tsx", ".jsx"):
    parser.language = TSX_LANGUAGE
else:
    parser.language = TS_LANGUAGE
```

### Key Node Types to Query

| Node Type | What It Represents |
|-----------|-------------------|
| `class_declaration` | `class Foo { ... }` |
| `abstract_class_declaration` | `abstract class Foo { ... }` |
| `interface_declaration` | `interface Foo { ... }` |
| `type_alias_declaration` | `type Foo = ...` |
| `enum_declaration` | `enum Foo { ... }` |
| `function_declaration` | `function foo() { ... }` |
| `generator_function_declaration` | `function* foo() { ... }` |
| `lexical_declaration` | `const/let/var foo = ...` |
| `method_definition` | Method inside class |
| `public_field_definition` | Class property |
| `export_statement` | `export ...` (wraps other declarations) |
| `ambient_declaration` | `declare namespace/module` |

### Arrow Function Detection

Arrow functions at module scope are detected via `lexical_declaration`:

```
lexical_declaration
  └── variable_declarator
       ├── name: "greet"
       └── value: arrow_function
            ├── parameters: (name: string)
            └── return_type: string
```

**Critical rule:** Arrow functions inside OBJECT LITERALS are NOT module-scope functions. Check the parent chain:

```python
# Walk up from arrow_function node
# If any ancestor is object/object_pattern/pair -> NOT a module function
# If ancestors are only: variable_declarator -> lexical_declaration -> program -> YES module function
```

### Variable-to-Class Mapping (React Pattern)

```typescript
const AuthProvider: React.FC<Props> = ({children}) => { ... };
```

This creates a FUNCTION named "AuthProvider" with the arrow function's parameters. The type annotation `React.FC<Props>` is the type, but the artifact is a function.

### Private Member Detection

Three forms of "private" in TypeScript:
1. `_name` — underscore prefix (convention)
2. `#name` — ES private fields (syntax)
3. `private name` — TypeScript access modifier keyword

All three are treated as private (is_private=True).

### JSX Element Detection (Behavioral Mode)

In `.tsx`/`.jsx` files, `<Component />` usage is detected as a reference to `Component`. Node type: `jsx_element` or `jsx_self_closing_element`.

### Generator Functions

`function* gen()` and `async function* gen()` are detected via `generator_function_declaration`. They produce FUNCTION artifacts with `is_async` set appropriately.

---

## 6. Svelte Validator

**Current location:** `maid_runner/validators/svelte_validator.py`
**New location:** `maid_runner/validators/svelte.py`

### Script Extraction

Svelte files contain `<script>` tags. Extract content:

```python
# Use tree-sitter-svelte to parse the .svelte file
# Find script_element nodes
# Extract the raw_text content
# Detect lang attribute: <script lang="ts"> -> TypeScript, else JavaScript
```

### Delegation

After extracting script content, delegate entirely to TypeScriptValidator:

```python
ts_result = self._ts_validator.collect_implementation_artifacts(script_content, file_path)
```

The Svelte validator adds no additional artifact types beyond what the TypeScript validator finds in the script content.

---

## 7. File Tracking Classification

**Current location:** `maid_runner/validators/file_tracker.py`

### Source File Discovery

Find all source files, excluding:
- `node_modules/`, `.venv/`, `__pycache__/`, `.git/`, `.idea/`
- `dist/`, `build/`, `htmlcov/`, `.pytest_cache/`
- Manifest files (`.manifest.yaml`, `.manifest.json`)
- Configuration files (`pyproject.toml`, `package.json`, etc.)

Include files with extensions: `.py`, `.ts`, `.tsx`, `.js`, `.jsx`, `.svelte`

### Classification Algorithm

```
For each source file:
    manifests = chain.manifests_for_file(path)

    if len(manifests) == 0:
        status = UNDECLARED

    else:
        has_artifacts = any(m.artifacts_for(path) for m in manifests)
        has_tests = any(test_file in m.files_read for m in manifests for test_file in ...)
        only_in_read = all(m.file_mode_for(path) == READ for m in manifests)

        if has_artifacts and has_tests and not only_in_read:
            status = TRACKED
        else:
            status = REGISTERED
            issues = []
            if not has_artifacts: issues.append("No expectedArtifacts")
            if not has_tests: issues.append("No validation command")
            if only_in_read: issues.append("Only in readonlyFiles")
```

---

## 8. Validation Command Existence Check

**Current location:** `maid_runner/cli/validate.py` (added in task-150)

Before running validation commands, check that executables exist:

```python
# For "pytest" commands: check if pytest is importable or in PATH
# For "vitest" commands: check node_modules/.bin/vitest or npx
# For "uv run ..." commands: check if uv is in PATH
# For "python -m ..." commands: check if python is in PATH
```

Produce a WARNING (not error) if executable not found. This prevents confusing "command not found" errors during validation.

---

## 9. Supersede Hint for Unexpected Artifacts

**Current location:** Task-147 and Task-151

When an unexpected artifact is found in strict mode, the error message includes a hint about which manifest to supersede:

```
Unexpected public function 'parse' in src/utils.py
  Hint: This artifact may be declared in an older manifest.
  Consider creating a new manifest that supersedes the relevant one.
  Related manifests: [snapshot-utils, add-parse-function]
```

This is a UX improvement that helps the AI agent self-correct.

---

## 10. Batch Test Optimization

**Current location:** `maid_runner/cli/_batch_test_runner.py`

### Strategy

When all manifests use pytest, instead of running N separate pytest processes:

```
# Instead of:
pytest tests/test_a.py -v   (process 1)
pytest tests/test_b.py -v   (process 2)
pytest tests/test_c.py -v   (process 3)

# Run once:
pytest tests/test_a.py tests/test_b.py tests/test_c.py -v   (single process)
```

### Extraction

From each validation command, extract the test file path:
- `pytest tests/test_foo.py -v` -> `tests/test_foo.py`
- `uv run python -m pytest tests/test_foo.py -v` -> `tests/test_foo.py`
- `vitest run tests/foo.test.ts` -> (separate group, can't batch with pytest)

### Fallback

If commands use mixed runners (pytest + vitest), fall back to sequential execution.
