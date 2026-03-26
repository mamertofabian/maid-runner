"""CLI handler for 'maid howto' command."""

from __future__ import annotations

import argparse

_TOPICS = {
    "create": (
        "How to Create a Manifest\n"
        "========================\n\n"
        "1. Define your goal: What change are you making?\n"
        "2. Create a YAML manifest file in manifests/:\n\n"
        "   schema: '2'\n"
        "   goal: Your goal description\n"
        "   type: feature\n"
        "   files:\n"
        "     create:\n"
        "       - path: src/your_file.py\n"
        "         artifacts:\n"
        "           - kind: function\n"
        "             name: your_function\n"
        "   validate:\n"
        "     - pytest tests/test_your_file.py -v\n\n"
        "3. Write tests first (TDD)\n"
        "4. Run: maid validate your-manifest.yaml --mode behavioral\n"
        "5. Implement the code\n"
        "6. Run: maid validate your-manifest.yaml\n"
    ),
    "validate": (
        "How to Validate\n"
        "===============\n\n"
        "Validate a single manifest:\n"
        "  maid validate manifests/your-task.manifest.yaml\n\n"
        "Validate all manifests:\n"
        "  maid validate\n\n"
        "Behavioral validation (checks tests USE artifacts):\n"
        "  maid validate --mode behavioral\n\n"
        "JSON output for CI/tools:\n"
        "  maid validate --json\n"
    ),
    "snapshot": (
        "How to Snapshot Existing Code\n"
        "=============================\n\n"
        "Generate a manifest from existing code:\n"
        "  maid snapshot src/your_file.py\n\n"
        "Preview without writing:\n"
        "  maid snapshot src/your_file.py --dry-run\n\n"
        "System-wide snapshot:\n"
        "  maid snapshot-system\n"
    ),
    "migrate": (
        "How to Migrate from v1 to v2\n"
        "============================\n\n"
        "1. v1 JSON manifests are auto-detected and converted\n"
        "2. Create new manifests in YAML v2 format\n"
        "3. Both formats work during migration\n"
        "4. Run: maid validate to check everything\n"
    ),
    "workflow": (
        "Complete MAID Workflow\n"
        "======================\n\n"
        "Phase 1: Define goal and create manifest\n"
        "Phase 2: Write behavioral tests\n"
        "  - maid validate --mode behavioral\n"
        "Phase 3: Implement code to pass tests\n"
        "  - maid validate\n"
        "  - maid test\n"
        "Phase 4: Refactor while tests pass\n"
        "Phase 5: Integration verification\n"
        "  - maid validate (all manifests)\n"
        "  - maid test (all test commands)\n"
    ),
}


def cmd_howto(args: argparse.Namespace) -> int:
    if args.topic is None:
        print("MAID Howto Topics")
        print("=================\n")
        for topic in _TOPICS:
            print(f"  maid howto {topic}")
        print("\nRun 'maid howto <topic>' for details.")
        return 0

    content = _TOPICS.get(args.topic)
    if content is None:
        print(f"Unknown topic: '{args.topic}'")
        print(f"Available: {', '.join(_TOPICS.keys())}")
        return 2

    print(content)
    return 0
