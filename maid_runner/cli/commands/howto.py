"""CLI handler for 'maid howto' command."""

from __future__ import annotations

import argparse

_TOPICS = {
    "quickstart": (
        "Quick Start\n"
        "===========\n\n"
        "The MAID loop is: declare what you are about to change, test it,\n"
        "build it, then let MAID check the code against what you declared.\n\n"
        "1. Set up MAID in your project:\n"
        "   maid init\n\n"
        "2. Declare the change in a manifest under manifests/.\n"
        "   Run 'maid howto create' for the manifest format.\n\n"
        "3. Write a behavioral test that uses the artifacts you declared.\n"
        "   Run it and watch it fail; nothing implements them yet.\n\n"
        "4. Write the code until that test passes.\n\n"
        "5. Check your code against the manifest:\n"
        "   maid validate\n\n"
        "6. Run the commands your manifest declares:\n"
        "   maid test\n\n"
        "That is the whole loop: declare, test, build, check. MAID layers more\n"
        "on top of it once the loop is familiar, including sealing an approved\n"
        "plan, handoff gates, and manifest chains.\n\n"
        "Run 'maid howto' to see every topic.\n"
    ),
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
        "5. After approval, run: maid plan lock your-manifest.yaml\n"
        "6. Implement the code\n"
        "7. Run: maid validate your-manifest.yaml\n"
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
        "  maid validate --json\n\n"
        "Failure packets for bounded agent retries:\n"
        "  maid validate --packet\n"
        "  maid verify --profile agent-retry --since <baseline>\n"
        "  Default packet path: .maid/last-failure-packet.json\n"
        "  On failure, read the packet before retrying instead of re-exploring "
        "the repository.\n"
    ),
    "workflow": (
        "Complete MAID Workflow\n"
        "======================\n\n"
        "Phase 1: Define goal and create manifest\n"
        "Phase 2: Write behavioral tests\n"
        "  - maid validate --mode behavioral\n"
        "  - maid plan lock manifests/your-task.manifest.yaml\n"
        "Phase 3: Implement code to pass tests\n"
        "  - maid validate\n"
        "  - maid test\n"
        "Phase 4: Refactor while tests pass\n"
        "Phase 5: Integration verification\n"
        "  - maid validate (all manifests)\n"
        "  - maid test (all test commands)\n"
        "  - maid verify --profile handoff\n"
        "    (expands to: maid verify --summary --require-plan-lock "
        "--require-red-evidence)\n"
    ),
    "commands": (
        "CLI Commands\n"
        "============\n\n"
        "Validate manifests:\n"
        "  maid validate [manifest] --mode schema|behavioral|implementation\n"
        "  maid validate [manifest] --mode schema\n\n"
        "Run manifest validation commands:\n"
        "  maid test --manifest manifests/your-task.manifest.yaml\n\n"
        "Seal and inspect approved plans:\n"
        "  maid plan lock manifests/your-task.manifest.yaml\n"
        "  maid plan revise manifests/your-task.manifest.yaml --reason '<text>'\n"
        "  maid plan status manifests/your-task.manifest.yaml --json\n"
        "  maid plan lock --no-run records red_evidence: null; pytest exit 1 "
        "is valid red, exits 2/3/4/5 are invalid, and exit 0 is not red.\n\n"
        "Run the implementation handoff gate with opt-in plan-lock enforcement:\n"
        "  maid verify --profile handoff\n"
        "  Expands to: maid verify --summary --require-plan-lock "
        "--require-red-evidence\n"
        "  Named presets: handoff, pre-commit, agent-retry, deep. A profile sets\n"
        "  defaults only where you did not pass a flag yourself, never supplies a\n"
        "  changed-scope baseline, and reports which flags it contributed.\n\n"
        "Run validation gates with failure packets for agent retry loops:\n"
        "  maid validate --packet\n"
        "  maid verify --profile agent-retry --since <baseline>\n"
        "  The default packet path is .maid/last-failure-packet.json; passing "
        "gates clear stale packets at that path.\n\n"
        "  Plan-lock requirement errors apply to manifests changed in the "
        "task window; integrity errors for existing locks still apply.\n\n"
        "Create manifest drafts:\n"
        "  maid manifest create src/your_file.py --goal 'Describe the change' "
        '--artifacts \'[{"kind":"function","name":"your_function"}]\'\n\n'
        "Generate reviewed drafts from a diff:\n"
        "  maid manifest from-diff --since <commit> --slug describe-the-change\n"
        "  maid manifest from-diff --base-ref <ref> --slug describe-the-change\n"
        "  maid manifest from-diff --worktree --slug describe-the-change\n"
        "  Exactly one of --since, --base-ref, or --worktree is required; MAID "
        "does not guess main, dev, or a remote branch.\n"
        "  Generated drafts land in manifests/drafts/ with "
        "metadata.needs_review: true and require review before promotion.\n\n"
        "Prioritize inadequately covered files:\n"
        "  maid bootstrap --rank --model risk-v1 --limit 20\n"
        "  maid bootstrap --rank --model risk-v1 --json\n"
        "  maid bootstrap --rank --model risk-v1 --explain src/example.py\n"
        "  risk-v1 includes undeclared files, read-only registrations, and "
        "writable manifests without declared artifacts. It reports evidence "
        "and confidence for coverage gap, production blast radius, change "
        "pressure, complexity, and test/evidence gap. Low confidence means "
        "evidence is incomplete, not that risk is low.\n"
        "  legacy-v1 remains the compatibility default for completely undeclared "
        "files. It reports raw churn, inbound_refs, and public_artifacts values; "
        "orders by churn descending, inbound_refs descending, public_artifacts "
        "descending, then path ascending. --rank writes no manifests.\n\n"
        "Run a long-lived validator daemon:\n"
        "  maid serve --socket .maid/serve.sock\n"
        "  maid howto serve\n\n"
        "Add new language support through the validator plugin path:\n"
        "  docs/validator-plugin-authoring.md\n"
        "  Package a BaseValidator subclass under the maid_runner.validators "
        "entry-point group, run the conformance kit, and audit installed "
        "validators with maid validators.\n\n"
        "Inspect schemas and guidance:\n"
        "  maid schema\n"
        "  maid howto workflow\n"
    ),
    "brownfield": (
        "Onboarding An Existing Codebase\n"
        "===============================\n\n"
        "Do not try to cover an existing repository in one pass. Add coverage\n"
        "as you touch code, starting with the files that carry the most risk.\n\n"
        "1. Rank files by coverage risk:\n"
        "   maid bootstrap --rank --model risk-v1 --limit 20\n"
        "   maid bootstrap --rank --model risk-v1 --explain src/example.py\n\n"
        "   risk-v1 reports evidence and confidence for coverage gap, production\n"
        "   blast radius, change pressure, complexity, and test/evidence gap. Low\n"
        "   confidence means evidence is incomplete, not that risk is low.\n\n"
        "   legacy-v1 remains the compatibility default for completely undeclared\n"
        "   files. It reports raw churn, inbound_refs, and public_artifacts\n"
        "   values; orders by churn descending, inbound_refs descending,\n"
        "   public_artifacts descending, then path ascending. --rank writes no\n"
        "   manifests.\n\n"
        "2. Draft a manifest from one implemented change:\n"
        "   maid manifest from-diff --since <commit> --slug describe-the-change\n"
        "   maid manifest from-diff --base-ref <ref> --slug describe-the-change\n"
        "   maid manifest from-diff --worktree --slug describe-the-change\n\n"
        "   Exactly one of --since, --base-ref, or --worktree is required; MAID\n"
        "   does not guess main, dev, or a remote branch.\n\n"
        "3. Review every generated draft before promoting it. Drafts land in\n"
        "   manifests/drafts/ with metadata.needs_review: true, and needs_review\n"
        "   is not promotable: replace the goal placeholder, fill placeholder\n"
        "   artifacts, and clear the marker first.\n"
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
    "troubleshooting": (
        "Troubleshooting\n"
        "===============\n\n"
        "Full guide: docs/troubleshooting.md\n\n"
        "Start with the failing phase:\n"
        "  maid validate <manifest> --mode schema\n"
        "  maid validate <manifest> --mode behavioral\n"
        "  maid validate <manifest> --mode implementation\n"
        "  maid test --manifest <manifest>\n"
        "  maid verify --strict\n\n"
        "For retrying agents, run gates with --packet and read "
        ".maid/last-failure-packet.json on failure before applying fixes.\n\n"
        "Common diagnostics:\n"
        "  E200: declared artifact is not referenced by behavioral tests.\n"
        "  E230: validate command does not run the declared tests.\n"
        "  E300: declared artifact is not defined in implementation.\n"
        "  E301: unexpected public artifact is present.\n"
        "  E303: function or method signature differs from the manifest.\n"
        "  E306: declared file is missing.\n"
        "  E307: no validator is available for that file type.\n"
        "  E310: placeholder or stub implementation remains.\n"
        "  E320: required import is missing.\n"
        "  E114/E115: worktree or changed-scope gate needs manifest scope or "
        "a baseline.\n\n"
        "Chain and history checks:\n"
        "  maid chain log --active\n"
        "  maid audit supersessions\n"
        "  maid learn && maid recall --text '<topic>'\n\n"
        "FAQ: docs/troubleshooting.md#faq\n"
    ),
    "serve": (
        "Validator Daemon (maid serve)\n"
        "=============================\n\n"
        "Long-lived local daemon over a Unix socket. Eliminates Python\n"
        "startup cost on every validate call, useful for AI agents,\n"
        "editor integrations, and tight TDD loops.\n\n"
        "Start it:\n"
        "  maid serve\n"
        "  maid serve --socket .maid/serve.sock --pidfile .maid/serve.pid \\\n"
        "             --project-root . --client-timeout 30\n\n"
        "NDJSON protocol. One JSON request per line, one response per line.\n\n"
        'Request:  {"id": "<id>", "method": "validate|ping", "params": {...}}\n'
        'Success:  {"id": "<id>", "ok": true, "result": {...}}\n'
        'Failure:  {"id": "<id>", "ok": false, "error": {"code", "message"}}\n\n'
        "validate params:\n"
        "  manifest_path  (required, resolved under --project-root)\n"
        "  mode           schema|behavioral|implementation\n"
        "  manifest_dir   default 'manifests/'\n"
        "  no_chain, check_assertions, check_stubs, fail_on_warnings (bool)\n\n"
        "ok=false codes: MISSING_PARAM, BAD_MODE, PATH_ESCAPE,\n"
        "  UNKNOWN_METHOD, PROTOCOL_ERROR, HANDLER_ERROR, FRAME_TOO_LARGE.\n\n"
        "Defense in depth:\n"
        "  - socket 0600, runtime dir 0700, atomic pidfile (O_CREAT|O_EXCL)\n"
        "  - thread-per-client (no head-of-line blocking)\n"
        "  - 1 MiB request frame cap\n"
        "  - daemon-bound project root; client-supplied project_root ignored\n\n"
        "Full reference: docs/maid-serve.md\n"
    ),
}


# Reading order for the topics, declared once so the rendered "Next" footers
# cannot drift from each other. Rooted at quickstart, visits every topic, and
# closes back to the start.
_NEXT_TOPIC = {
    "quickstart": "create",
    "create": "validate",
    "validate": "workflow",
    "workflow": "commands",
    "commands": "brownfield",
    "brownfield": "snapshot",
    "snapshot": "migrate",
    "migrate": "troubleshooting",
    "troubleshooting": "serve",
    "serve": "quickstart",
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
    next_topic = _NEXT_TOPIC.get(args.topic)
    if next_topic is not None:
        print(f"Next: maid howto {next_topic}")
    return 0
