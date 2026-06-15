import unittest
from pathlib import Path

from tools import claude_maid_loop, codex_maid_loop


class TestOutcomeReadyGuidance(unittest.TestCase):
    def test_agents_guidance_requires_outcome_capture_before_handoff(self) -> None:
        root = Path(__file__).resolve().parents[2]
        agents_guidance = (root / "AGENTS.md").read_text(encoding="utf-8")

        for expected_text in (
            "Capture Outcome after implementation review and before final handoff",
            "evidence-backed `outcome:` section",
            "Do not report ready, merge-ready, commit-ready, or handoff-ready",
        ):
            self.assertIn(expected_text, agents_guidance)

    def test_codex_draft_implement_skill_requires_outcome_before_ready(self) -> None:
        root = Path(__file__).resolve().parents[2]
        skill = (root / ".codex/skills/maid-runner-draft-implement/SKILL.md").read_text(
            encoding="utf-8"
        )
        distributed_skill = (
            root / "maid_runner/codex/skills/maid-runner-draft-implement/SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertEqual(skill, distributed_skill)

        for expected_text in (
            "Capture Outcome after implementation review and before final handoff",
            "evidence-backed `outcome:` section",
            "AUTOMATION_STATUS: READY",
            "Do not report READY when Outcome is missing",
        ):
            self.assertIn(expected_text, skill)

    def test_codex_loop_prompt_requires_outcome_before_ready(self) -> None:
        final_path = Path("/tmp/final.md")
        command = codex_maid_loop.build_implementation_command(
            codex="codex",
            final_message_path=final_path,
            selected_drafts=[Path("manifests/drafts/017-01-example.manifest.yaml")],
        )
        prompt = command[-1]

        for expected_text in (
            "Capture Outcome after implementation review and before final handoff",
            "evidence-backed `outcome:` section",
            "Do not report AUTOMATION_STATUS: READY when Outcome is missing",
        ):
            self.assertIn(expected_text, prompt)

    def test_claude_draft_implement_skill_requires_outcome_before_ready(
        self,
    ) -> None:
        skill = (
            Path(__file__).resolve().parents[2]
            / ".claude/skills/maid-runner-draft-implement/SKILL.md"
        ).read_text(encoding="utf-8")

        for expected_text in (
            "Capture Outcome after implementation review and before final handoff",
            "evidence-backed `outcome:` section",
            "AUTOMATION_STATUS: READY",
            "Do not report READY when Outcome is missing",
        ):
            self.assertIn(expected_text, skill)

    def test_claude_loop_prompt_requires_outcome_before_ready(self) -> None:
        command = claude_maid_loop.build_implementation_command(
            claude="claude",
            selected_drafts=[Path("manifests/drafts/017-03-example.manifest.yaml")],
            model="sonnet",
            effort="medium",
            permission_mode="auto",
        )
        prompt = command[-1]

        for expected_text in (
            "Capture Outcome after implementation review and before final handoff",
            "evidence-backed `outcome:` section",
            "Do not report AUTOMATION_STATUS: READY when Outcome is missing",
        ):
            self.assertIn(expected_text, prompt)


if __name__ == "__main__":
    unittest.main()
