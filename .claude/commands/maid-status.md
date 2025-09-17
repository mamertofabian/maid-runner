---
description: Show MAID project status and available manifests
allowed-tools: Bash(ls*), Bash(PYTHONPATH=. uv run python*), Read
---

## Task: Display MAID Project Status

Show comprehensive status of the MAID project including manifests, tests, and implementations.

### Status Report:

```python
import json
from pathlib import Path
from collections import defaultdict

def show_maid_status():
    """Display comprehensive MAID project status."""

    print("🚀 MAID Project Status")
    print("=" * 50)

    # 1. List all manifests
    print("\n📋 Manifests:")
    manifests = sorted(Path("manifests").glob("*.json"))
    if not manifests:
        print("   No manifests found")
    else:
        for manifest_path in manifests:
            try:
                with open(manifest_path, "r") as f:
                    data = json.load(f)
                goal = data.get("goal", "No goal specified")
                impl_file = data.get("expectedArtifacts", {}).get("file", "N/A")
                print(f"   • {manifest_path.name}")
                print(f"     Goal: {goal[:60]}...")
                print(f"     Implementation: {impl_file}")
            except Exception as e:
                print(f"   • {manifest_path.name} - ⚠️  Error: {e}")

    # 2. List integration tests
    print("\n🧪 Integration Tests:")
    test_files = sorted(Path("tests").glob("test_task_*_integration.py"))
    if not test_files:
        print("   No integration tests found")
    else:
        for test_file in test_files:
            task_num = test_file.stem.split("_")[2]
            manifest_name = f"task-{task_num}.manifest.json"
            manifest_exists = Path(f"manifests/{manifest_name}").exists()
            status = "✅" if manifest_exists else "❌"
            print(f"   • {test_file.name} {status}")

    # 3. Implementation files status
    print("\n🔨 Implementation Files:")
    impl_files = defaultdict(list)
    for manifest_path in manifests:
        try:
            with open(manifest_path, "r") as f:
                data = json.load(f)
            impl_file = data.get("expectedArtifacts", {}).get("file")
            if impl_file:
                impl_files[impl_file].append(manifest_path.name)
        except:
            pass

    if not impl_files:
        print("   No implementation files tracked")
    else:
        for impl_file, manifest_list in impl_files.items():
            exists = "✅" if Path(impl_file).exists() else "❌"
            print(f"   • {impl_file} {exists}")
            print(f"     Modified by: {', '.join(manifest_list)}")

    # 4. Validation status
    print("\n✨ Quick Validation:")
    print("   Run '/run-validation [task-number]' to validate a task")
    print("   Run '/validate-manifest [manifest-file]' for detailed validation")

    # 5. Available commands
    print("\n📚 Available MAID Commands:")
    commands = [
        "/generate-manifest - Create new manifest",
        "/generate-tests - Generate tests from manifest",
        "/implement - Implement from manifest",
        "/refactor - Refactor implementation",
        "/improve-tests - Enhance test coverage",
        "/validate-manifest - Validate manifest and implementation",
        "/run-validation - Run validation tests",
        "/maid-help - Show detailed help",
        "/maid-status - Show this status"
    ]
    for cmd in commands:
        print(f"   • {cmd}")

    print("\n" + "=" * 50)

show_maid_status()
```

### Additional Checks:

1. **Schema Validity**: Verify all manifests against schema
2. **Test Coverage**: Show test coverage percentages
3. **Implementation Completeness**: Check all expected artifacts exist
4. **Manifest Chain**: Show dependencies between manifests

This command provides a quick overview of your MAID project's health and progress!