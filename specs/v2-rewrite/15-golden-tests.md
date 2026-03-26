# MAID Runner v2 - Golden Test Cases

**References:** [02-manifest-schema-v2.md](02-manifest-schema-v2.md), [05-core-validation.md](05-core-validation.md), [06-validators.md](06-validators.md)

## Purpose

These are concrete input/output test cases that define the expected behavior of each module. Tests MUST be written against these cases (behavior-first), not against the implementation.

---

## 1. Manifest Loading

### 1.1 Load Valid V2 YAML

**Input:**
```yaml
schema: "2"
goal: "Add greeting function"
type: feature
files:
  create:
    - path: src/greet.py
      artifacts:
        - kind: function
          name: greet
          args:
            - name: name
              type: str
          returns: str
  read:
    - tests/test_greet.py
validate:
  - pytest tests/test_greet.py -v
created: "2025-06-15T10:30:00Z"
```

**Expected Manifest:**
- `slug` = derived from filename
- `goal` = "Add greeting function"
- `schema_version` = "2"
- `task_type` = TaskType.FEATURE
- `files_create` = 1 FileSpec with path="src/greet.py", mode=FileMode.CREATE
- `files_create[0].artifacts` = 1 ArtifactSpec: kind=FUNCTION, name="greet", args=(ArgSpec("name", "str"),), returns="str"
- `files_read` = ("tests/test_greet.py",)
- `validate_commands` = (("pytest", "tests/test_greet.py", "-v"),)
- `created` = "2025-06-15T10:30:00Z"

### 1.2 Load Multi-File Manifest

**Input:**
```yaml
schema: "2"
goal: "Add auth service and models"
type: feature
files:
  create:
    - path: src/auth/service.py
      artifacts:
        - kind: class
          name: AuthService
        - kind: method
          name: login
          of: AuthService
          args:
            - name: username
              type: str
            - name: password
              type: str
          returns: Token
    - path: src/auth/models.py
      artifacts:
        - kind: class
          name: Token
        - kind: attribute
          name: value
          of: Token
          type: str
  edit:
    - path: src/config.py
      artifacts:
        - kind: attribute
          name: AUTH_SECRET
          type: str
  read:
    - src/database.py
validate:
  - pytest tests/test_auth.py -v
```

**Expected:**
- `files_create` has 2 FileSpec entries
- `files_edit` has 1 FileSpec entry with mode=FileMode.EDIT
- `files_create[0].artifacts[1].of` = "AuthService"
- `files_create[0].artifacts[1].kind` = ArtifactKind.METHOD
- `files_edit[0].artifacts[0].kind` = ArtifactKind.ATTRIBUTE
- `files_edit[0].artifacts[0].type_annotation` = "str"

### 1.3 Load Invalid - Missing Goal

**Input:**
```yaml
schema: "2"
files:
  create:
    - path: src/foo.py
      artifacts:
        - kind: class
          name: Foo
validate:
  - pytest tests/ -v
```

**Expected:** `ManifestSchemaError` raised with message mentioning "goal"

### 1.4 Load Invalid - No Files

**Input:**
```yaml
schema: "2"
goal: "Empty manifest"
validate:
  - pytest tests/ -v
```

**Expected:** `ManifestSchemaError` raised (at least one of files.create/edit/snapshot/delete required)

### 1.5 Slug Extraction

| Filename | Expected Slug |
|----------|---------------|
| `add-jwt-auth.manifest.yaml` | `add-jwt-auth` |
| `fix-cls-parameter.manifest.yaml` | `fix-cls-parameter` |
| `task-001-add-schema.manifest.json` | `task-001-add-schema` |
| `snapshot-auth-service.manifest.yaml` | `snapshot-auth-service` |

---

## 2. V1 Compatibility

### 2.1 Convert Simple V1 Create Manifest

**Input (JSON):**
```json
{
  "goal": "Add schema validation",
  "taskType": "create",
  "creatableFiles": ["maid_runner/validators/manifest_validator.py"],
  "readonlyFiles": ["tests/test_validate_schema.py"],
  "expectedArtifacts": {
    "file": "maid_runner/validators/manifest_validator.py",
    "contains": [
      {
        "type": "function",
        "name": "validate_schema",
        "parameters": [{"name": "manifest_data"}, {"name": "schema_path"}]
      }
    ]
  },
  "validationCommand": ["pytest", "tests/test_validate_schema.py"]
}
```

**Expected V2 dict after conversion:**
```yaml
schema: "2"
goal: "Add schema validation"
type: feature
files:
  create:
    - path: maid_runner/validators/manifest_validator.py
      artifacts:
        - kind: function
          name: validate_schema
          args:
            - name: manifest_data
            - name: schema_path
  read:
    - tests/test_validate_schema.py
validate:
  - pytest tests/test_validate_schema.py
```

### 2.2 Convert V1 Method (function + class)

**Input artifact:**
```json
{"type": "function", "name": "login", "class": "AuthService", "args": [{"name": "user", "type": "str"}], "returns": "bool"}
```

**Expected V2 artifact:**
```yaml
kind: method
name: login
of: AuthService
args:
  - name: user
    type: str
returns: bool
```

### 2.3 Convert V1 Returns Object Format

**Input:** `"returns": {"type": "Optional[dict]"}`
**Expected:** `returns: "Optional[dict]"` (flattened to string)

### 2.4 Convert V1 Supersedes Paths to Slugs

**Input:** `"supersedes": ["manifests/task-001-add-schema.manifest.json"]`
**Expected:** `supersedes: ["task-001-add-schema"]`

---

## 3. Manifest Chain

### 3.1 Basic Supersession

**Setup:**
```
manifests/
  old-feature.manifest.yaml    (goal: "Old feature")
  new-feature.manifest.yaml    (goal: "New feature", supersedes: [old-feature])
```

**Expected:**
- `chain.active_manifests()` returns only `new-feature`
- `chain.superseded_manifests()` returns `old-feature`
- `chain.is_superseded("old-feature")` = True
- `chain.superseded_by("old-feature")` = "new-feature"

### 3.2 Artifact Merge

**Setup:**
```
manifests/
  add-base.manifest.yaml:
    files.create: [{path: src/service.py, artifacts: [{kind: class, name: Service}, {kind: method, name: start, of: Service}]}]
    created: "2025-06-01"
  add-stop.manifest.yaml:
    files.edit: [{path: src/service.py, artifacts: [{kind: method, name: stop, of: Service}]}]
    created: "2025-06-15"
```

**Expected:**
- `chain.merged_artifacts_for("src/service.py")` returns 3 artifacts: Service (class), start (method), stop (method)
- Later manifest's artifacts override earlier ones with same merge_key

### 3.3 File Mode Resolution

**Setup:** File "src/app.py" appears in manifest A as `files.create` and manifest B as `files.edit`.

**Expected:** `chain.file_mode_for("src/app.py")` = FileMode.CREATE (strictest wins)

### 3.4 Circular Supersession Detection

**Setup:** A supersedes B, B supersedes A

**Expected:** `chain.validate_supersession_integrity()` returns error about circular supersession

---

## 4. Python Validator - Implementation Artifacts

### 4.1 Basic Class

**Source:**
```python
class UserService:
    pass
```

**Expected:** 1 artifact: kind=CLASS, name="UserService", of=None

### 4.2 Class with Bases

**Source:**
```python
from abc import ABC
class UserService(ABC):
    pass
```

**Expected:** kind=CLASS, name="UserService", bases=("ABC",)

### 4.3 Method with Self Filtered

**Source:**
```python
class Foo:
    def bar(self, x: int, y: str = "hello") -> bool:
        pass
```

**Expected method:** kind=METHOD, name="bar", of="Foo", args=(ArgSpec("x","int"), ArgSpec("y","str","\"hello\"")), returns="bool"
- `self` is NOT in args

### 4.4 Classmethod with Cls Filtered

**Source:**
```python
class Foo:
    @classmethod
    def create(cls, data: dict) -> "Foo":
        pass
```

**Expected:** kind=METHOD, name="create", of="Foo", args=(ArgSpec("data","dict"),), returns="Foo"
- `cls` is NOT in args

### 4.5 Static Method (No Filtering)

**Source:**
```python
class Foo:
    @staticmethod
    def helper(x: int) -> str:
        pass
```

**Expected:** kind=METHOD, name="helper", of="Foo", args=(ArgSpec("x","int"),), returns="str"
- No self/cls filtering needed

### 4.6 Async Function

**Source:**
```python
async def fetch_data(url: str) -> dict:
    pass
```

**Expected:** kind=FUNCTION, name="fetch_data", is_async=True, args=(ArgSpec("url","str"),), returns="dict"

### 4.7 Module-Level Attribute

**Source:**
```python
MAX_RETRIES: int = 3
```

**Expected:** kind=ATTRIBUTE, name="MAX_RETRIES", of=None, type_annotation="int"

### 4.8 Class Attribute (in __init__)

**Source:**
```python
class Config:
    def __init__(self):
        self.debug = False
        self.port = 8080
```

**Expected:** 2 attributes: (kind=ATTRIBUTE, name="debug", of="Config"), (kind=ATTRIBUTE, name="port", of="Config")

### 4.9 Property Treated as Attribute

**Source:**
```python
class User:
    @property
    def full_name(self) -> str:
        return f"{self.first} {self.last}"
```

**Expected:** kind=ATTRIBUTE, name="full_name", of="User" (NOT a method)

### 4.10 Private Members

**Source:**
```python
class Foo:
    def public_method(self): pass
    def _private_method(self): pass
    def __dunder_method(self): pass
```

**Expected:** All 3 methods collected, but `_private_method` and `__dunder_method` have `is_private=True`

### 4.11 Enum Class

**Source:**
```python
from enum import Enum
class Color(Enum):
    RED = 1
    GREEN = 2
```

**Expected:** kind=CLASS, name="Color", bases=("Enum",) + attributes RED, GREEN of class Color

### 4.12 Generic Class

**Source:**
```python
from typing import Generic, TypeVar
T = TypeVar('T')
class Container(Generic[T]):
    pass
```

**Expected:** kind=CLASS, name="Container", bases contains "Generic" (or "Generic[T]")

---

## 5. Type Comparison

### 5.1 Normalization Rules

| Input | Normalized | Notes |
|-------|-----------|-------|
| `Optional[str]` | `Union[None, str]` | Optional -> Union + sorted |
| `str \| None` | `Union[None, str]` | Pipe -> Union + sorted |
| `Union[str, int]` | `Union[int, str]` | Sorted alphabetically |
| `Union[int, str, None]` | `Union[None, int, str]` | Sorted |
| `Dict[str, int]` | `Dict[str, int]` | Unchanged (comma spacing normalized) |
| `Dict[str,int]` | `Dict[str, int]` | Comma spacing added |
| `List[ str ]` | `List[str]` | Extra spaces removed |
| `Optional[Dict[str, int]]` | `Union[Dict[str, int], None]` | Nested generics preserved |

### 5.2 Type Comparison Cases

| Manifest Type | Implementation Type | Match? |
|--------------|---------------------|--------|
| `str` | `str` | YES |
| `Optional[str]` | `str \| None` | YES |
| `Optional[str]` | `Union[str, None]` | YES |
| `Dict[str, int]` | `Dict[str,int]` | YES |
| `list[str]` | `List[str]` | YES (PEP 585) |
| `int` | `str` | NO |
| `Optional[str]` | `str` | NO |
| `None` (not specified) | `str` | YES (no constraint) |
| `str` | `None` (not specified) | WARNING (missing annotation) |

---

## 6. Implementation Validation

### 6.1 Strict Mode - All Artifacts Present (PASS)

**Manifest:**
```yaml
files:
  create:
    - path: src/greet.py
      artifacts:
        - kind: function
          name: greet
          args: [{name: name, type: str}]
          returns: str
```

**Source (`src/greet.py`):**
```python
def greet(name: str) -> str:
    return f"Hello, {name}!"
```

**Expected:** ValidationResult.success = True, errors = []

### 6.2 Strict Mode - Missing Artifact (FAIL)

**Manifest:** Same as 6.1
**Source:** `# empty file`

**Expected:** Error E300 "Artifact 'greet' not defined in src/greet.py"

### 6.3 Strict Mode - Unexpected Public Artifact (FAIL)

**Manifest:**
```yaml
files:
  create:
    - path: src/greet.py
      artifacts:
        - kind: function
          name: greet
```

**Source:**
```python
def greet(name):
    return f"Hello, {name}!"

def farewell(name):     # NOT in manifest
    return f"Goodbye, {name}!"
```

**Expected:** Error E301 "Unexpected public artifact 'farewell' in src/greet.py"

### 6.4 Strict Mode - Private Artifact Allowed (PASS)

**Manifest:** Same as 6.3 (only declares `greet`)
**Source:**
```python
def greet(name):
    return _format(name)

def _format(name):     # Private - allowed
    return f"Hello, {name}!"
```

**Expected:** PASS (private artifacts not flagged)

### 6.5 Permissive Mode - Extra Public Allowed (PASS)

**Manifest:**
```yaml
files:
  edit:
    - path: src/greet.py
      artifacts:
        - kind: function
          name: farewell
```

**Source:**
```python
def greet(name):        # Pre-existing, not in manifest
    return f"Hello, {name}!"

def farewell(name):     # Declared in manifest
    return f"Goodbye, {name}!"
```

**Expected:** PASS (edit mode allows extra public artifacts)

### 6.6 Absent Status - File Still Exists (FAIL)

**Manifest:**
```yaml
files:
  delete:
    - path: src/old_module.py
```

**Source:** `src/old_module.py` exists on disk

**Expected:** Error E305 "File 'src/old_module.py' should be absent but still exists"

### 6.7 Type Mismatch (FAIL)

**Manifest:**
```yaml
files:
  create:
    - path: src/calc.py
      artifacts:
        - kind: function
          name: add
          args: [{name: a, type: int}, {name: b, type: int}]
          returns: int
```

**Source:**
```python
def add(a: str, b: str) -> str:   # Wrong types
    return a + b
```

**Expected:** Error E302 "Type mismatch for parameter 'a' in function 'add': expected 'int', got 'str'"

---

## 7. Behavioral Validation

### 7.1 Artifact Used in Test (PASS)

**Manifest:**
```yaml
files:
  create:
    - path: src/greet.py
      artifacts:
        - kind: function
          name: greet
  read:
    - tests/test_greet.py
validate:
  - pytest tests/test_greet.py -v
```

**Test file (`tests/test_greet.py`):**
```python
from src.greet import greet

def test_greet():
    assert greet("World") == "Hello, World!"
```

**Expected:** PASS (greet is imported and called)

### 7.2 Artifact NOT Used in Test (FAIL)

Same manifest, but test file:
```python
def test_something():
    assert True
```

**Expected:** Error E200 "Artifact 'greet' not used in any test file"

---

## 8. TypeScript Validator

### 8.1 Interface Detection

**Source:**
```typescript
interface UserProps {
  name: string;
  age: number;
}
```

**Expected:** kind=INTERFACE, name="UserProps"

### 8.2 Arrow Function at Module Scope

**Source:**
```typescript
const greet = (name: string): string => {
  return `Hello, ${name}!`;
};
```

**Expected:** kind=FUNCTION, name="greet", args=(ArgSpec("name","string"),), returns="string"

### 8.3 Class with Methods

**Source:**
```typescript
class AuthService {
  async login(username: string, password: string): Promise<boolean> {
    return true;
  }
}
```

**Expected:**
- kind=CLASS, name="AuthService"
- kind=METHOD, name="login", of="AuthService", is_async=True, args=(ArgSpec("username","string"), ArgSpec("password","string")), returns="Promise<boolean>"

### 8.4 Private Members Filtered

**Source:**
```typescript
class Foo {
  public bar(): void {}
  private _baz(): void {}
  #secret(): void {}
}
```

**Expected:** bar has is_private=False; _baz and #secret have is_private=True

### 8.5 Object Property Arrows NOT Module Functions

**Source:**
```typescript
const config = {
  handler: () => console.log("hi"),
  process: (x: number) => x * 2
};
```

**Expected:** `handler` and `process` are NOT collected as module-level functions (they're object properties)

### 8.6 Enum Detection

**Source:**
```typescript
enum Direction {
  Up = "UP",
  Down = "DOWN"
}
```

**Expected:** kind=ENUM, name="Direction"

---

## 9. File Tracking

### 9.1 Classification

**Setup:**
- Source files: `src/a.py`, `src/b.py`, `src/c.py`
- Manifests reference: `src/a.py` (with artifacts and tests), `src/b.py` (only in files.read)
- `src/c.py` not in any manifest

**Expected:**
- `src/a.py` -> TRACKED
- `src/b.py` -> REGISTERED (only in read, no artifacts)
- `src/c.py` -> UNDECLARED
