import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_SKILL = ".claude/skills/maid-incident-logger/SKILL.md"
DISTRIBUTED_SKILL = "maid_runner/claude/skills/maid-incident-logger/SKILL.md"

COMMAND_FORMS = (
    "maid incident capture --manifest <path> --packet <path> --rejected-diff <path> --tags <comma-list> [--notes <text>]",
    "maid incident update <incident-path> --chosen-diff <path>",
    "maid incident list [--tag <tag>] [--json]",
    "maid incident export --format dpo --output <path>",
    "maid incident suggest-temptations --paths <comma-list> [--json]",
)

PATTERN_TAGS = (
    "test-weakening",
    "trivial-test",
    "stub-implementation",
    "contract-renegotiation",
    "scope-escape",
    "runner-gaming",
    "false-done",
)

GUIDANCE_ANCHORS = (
    "## Deterministic Incident Commands",
    "## Capture Workflow",
    "## Pattern Tags",
    "## Recall Planning Link",
)


def _read(relative_path: str, root: Path = PROJECT_ROOT) -> str:
    return (root / relative_path).read_text()


def _sync_distribution(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    shutil.copytree(PROJECT_ROOT / ".claude", workspace / ".claude")
    scripts_dir = workspace / "scripts"
    scripts_dir.mkdir()
    shutil.copy2(PROJECT_ROOT / "scripts/sync_claude_files.py", scripts_dir)

    subprocess.run(
        [sys.executable, "scripts/sync_claude_files.py"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    return workspace


def test_incident_logger_guidance_quotes_exact_command_surface():
    text = _read(SOURCE_SKILL)

    for command_form in COMMAND_FORMS:
        assert command_form in text

    assert "~/.maid/incidents/" not in text
    assert "YYYYMMDD-HHMMSS-<repo-or-topic>.md" not in text
    assert "maid-incident.v1" not in text
    assert ".maid/incidents/" in text
    assert "no new CLI behavior" in text
    assert "No inference, classification models, or hidden summarization" in text


def test_incident_logger_guidance_documents_capture_then_update_workflow():
    text = _read(SOURCE_SKILL)
    capture_index = text.index(
        "capture the incident immediately with the failure packet and rejected diff"
    )
    update_index = text.index("update the same incident after the honest fix lands")

    assert capture_index < update_index
    assert "contract-integrity gate catches a gaming attempt" in text
    assert "--packet <path>" in text
    assert "--rejected-diff <path>" in text
    assert "--chosen-diff <path>" in text


def test_incident_logger_guidance_lists_closed_tag_vocabulary_exactly():
    text = _read(SOURCE_SKILL)
    vocabulary_block = text.split("## Pattern Tags", 1)[1].split(
        "## Recall Planning Link", 1
    )[0]
    listed_tags = tuple(
        line.removeprefix("- `").removesuffix("`")
        for line in vocabulary_block.splitlines()
        if line.startswith("- `")
    )

    assert listed_tags == PATTERN_TAGS
    assert "Unknown tags are rejected as a usage error" in vocabulary_block
    assert "Vocabulary changes require a manifest evolution" in vocabulary_block


def test_incident_logger_guidance_cross_links_recall_and_syncs_distribution(
    tmp_path: Path,
):
    source_text = _read(SOURCE_SKILL)
    synced_workspace = _sync_distribution(tmp_path)
    distributed_text = _read(DISTRIBUTED_SKILL, root=synced_workspace)

    for anchor in GUIDANCE_ANCHORS:
        assert anchor in source_text
        assert anchor in distributed_text

    for recall_term in (
        "066 recall workflow",
        "maid recall --for-manifest <path>",
        "maid recall --for-manifest <path> --plan-packet",
        "documentation-only cross-link",
    ):
        assert recall_term in source_text
        assert recall_term in distributed_text
