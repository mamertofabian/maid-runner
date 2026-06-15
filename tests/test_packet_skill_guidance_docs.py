from pathlib import Path

from maid_runner.cli.commands.howto import _TOPICS, cmd_howto


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
CLAUDE_SKILL = ROOT / ".claude/skills/maid-implementer/SKILL.md"
CLAUDE_DIST_SKILL = ROOT / "maid_runner/claude/skills/maid-implementer/SKILL.md"
CODEX_SKILL = ROOT / ".codex/skills/maid-runner-draft-implement/SKILL.md"
CODEX_DIST_SKILL = (
    ROOT / "maid_runner/codex/skills/maid-runner-draft-implement/SKILL.md"
)

PACKET_GUIDANCE_ANCHORS = (
    "run validation gates with `--packet`",
    "read `.maid/last-failure-packet.json`",
    "instead of re-exploring the repository",
    "`next_action`",
    "default 5 attempt bound",
    "escalate to a human with the final packet",
    "never authorize weakening tests or manifests to silence errors",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_readme_and_howto_describe_packet_flag() -> None:
    readme = _read(README)
    howto_text = "\n".join(_TOPICS.values())

    assert "maid validate --packet" in readme
    assert "maid verify --packet" in readme
    assert "writes a failure packet only when the run fails" in readme
    assert "removes any stale packet at that path" in readme
    assert ".maid/last-failure-packet.json" in readme

    assert "maid validate --packet" in howto_text
    assert "maid verify --packet" in howto_text
    assert ".maid/last-failure-packet.json" in howto_text
    assert cmd_howto


def test_skill_guidance_instructs_packet_driven_retries() -> None:
    skill_text = "\n".join(
        _read(path)
        for path in (
            CLAUDE_SKILL,
            CLAUDE_DIST_SKILL,
            CODEX_SKILL,
            CODEX_DIST_SKILL,
        )
    )

    for anchor in PACKET_GUIDANCE_ANCHORS:
        assert anchor in skill_text


def test_packet_guidance_anchors_are_synced_to_distribution_copies() -> None:
    skill_pairs = (
        (CLAUDE_SKILL, CLAUDE_DIST_SKILL),
        (CODEX_SKILL, CODEX_DIST_SKILL),
    )

    for source, distribution in skill_pairs:
        source_text = _read(source)
        distribution_text = _read(distribution)
        for anchor in PACKET_GUIDANCE_ANCHORS:
            assert anchor in source_text
            assert anchor in distribution_text
