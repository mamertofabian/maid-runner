---
description: Generate a MAID manifest for a task
argument-hint: [task-number] [goal description]
allowed-tools: Write, Read, Glob
---

## Task: Generate MAID Manifest

You need to generate a manifest file for task $1 with the following goal:
"$2"

### Requirements:

1. Create a manifest file at `manifests/task-$1.manifest.json`
2. The manifest must conform to the schema at `validators/schemas/manifest.schema.json`
3. Include the following sections:
   - `goal`: Clear description of what needs to be implemented
   - `creatableFiles`: List of files that can be created (if any)
   - `editableFiles`: List of existing files that can be edited (if any)
   - `readonlyFiles`: List of files that should only be read (typically test files)
   - `expectedArtifacts`: Specification of expected code artifacts including:
     - Classes with optional base classes
     - Functions with parameter lists
     - Attributes with their parent classes
   - `validationCommand`: The pytest command to run the tests

### Schema Reference:
The manifest must validate against @validators/schemas/manifest.schema.json

### Example Structure:
```json
{
  "goal": "Implement the X functionality that does Y",
  "creatableFiles": ["path/to/new/file.py"],
  "editableFiles": ["path/to/existing/file.py"],
  "readonlyFiles": ["tests/test_file.py"],
  "expectedArtifacts": {
    "file": "path/to/implementation.py",
    "contains": [
      {
        "type": "class",
        "name": "MyClass",
        "bases": ["BaseClass"]
      },
      {
        "type": "function",
        "name": "my_function",
        "parameters": ["param1", "param2"]
      }
    ]
  },
  "validationCommand": ["pytest tests/test_file.py"]
}
```

Generate the manifest based on the provided goal description. Be thorough in defining the expected artifacts.