import argparse
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import claude_maid_loop


class TestClaudeMaidLoopDiscovery(unittest.TestCase):
    def test_find_implementable_drafts_excludes_epics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            draft_dir = Path(temp_dir)
            child = draft_dir / "017-01-example.manifest.yaml"
            epic = draft_dir / "000-example.epic.yaml"
            child.write_text("schema: '2'\n", encoding="utf-8")
            epic.write_text("schema: '2'\n", encoding="utf-8")

            drafts = claude_maid_loop.find_implementable_drafts(draft_dir)

        self.assertEqual([child], drafts)


class TestClaudeMaidLoopCommand(unittest.TestCase):
    def test_build_implementation_command_uses_claude_print_stream_and_repo_skill(
        self,
    ) -> None:
        command = claude_maid_loop.build_implementation_command(
            claude="claude",
            selected_drafts=[Path("manifests/drafts/017-03-example.manifest.yaml")],
            model="sonnet",
            effort="medium",
            permission_mode="auto",
        )

        self.assertEqual(
            ["claude", "-p", "--verbose", "--output-format", "stream-json"],
            command[:5],
        )
        self.assertIn("--permission-mode", command)
        self.assertEqual("auto", command[command.index("--permission-mode") + 1])
        self.assertIn("--model", command)
        self.assertEqual("sonnet", command[command.index("--model") + 1])
        self.assertIn("--effort", command)
        self.assertEqual("medium", command[command.index("--effort") + 1])
        self.assertIn("maid-runner-draft-implement", command[-1])
        self.assertIn(
            ".claude/skills/maid-runner-draft-implement/SKILL.md", command[-1]
        )
        self.assertIn("AUTOMATION_STATUS: READY", command[-1])
        self.assertIn("AUTOMATION_COMMIT_MESSAGE", command[-1])

    def test_build_implementation_command_scopes_prompt_to_selected_draft(
        self,
    ) -> None:
        selected_draft = Path(
            "manifests/drafts/017-03-preserve-third-party-package-boundary.manifest.yaml"
        )

        command = claude_maid_loop.build_implementation_command(
            claude="claude",
            selected_drafts=[selected_draft],
            model="sonnet",
            effort="medium",
            permission_mode="auto",
        )

        self.assertIn("Selected draft manifest(s) for this pass:", command[-1])
        self.assertIn(selected_draft.as_posix(), command[-1])
        self.assertIn("Implement only the selected draft manifest(s)", command[-1])
        self.assertIn(
            "Do not promote, edit, delete, or implement any other", command[-1]
        )

    def test_build_implementation_command_requires_verbose_for_stream_json(
        self,
    ) -> None:
        command = claude_maid_loop.build_implementation_command(
            claude="claude",
            selected_drafts=[Path("manifests/drafts/017-03-example.manifest.yaml")],
            model="sonnet",
            effort="medium",
            permission_mode="auto",
        )

        self.assertIn("--verbose", command)
        self.assertLess(command.index("--verbose"), command.index("--output-format"))


class TestClaudeMaidLoopRenderer(unittest.TestCase):
    def test_render_claude_stream_event_handles_session_text_and_result(
        self,
    ) -> None:
        state: dict[str, object] = {}

        rendered = [
            claude_maid_loop.render_claude_stream_event(
                {"type": "system", "subtype": "init", "session_id": "session-1"},
                state,
            ),
            claude_maid_loop.render_claude_stream_event(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {"type": "text", "text": "Working.\n"},
                        ]
                    },
                },
                state,
            ),
            claude_maid_loop.render_claude_stream_event(
                {
                    "type": "result",
                    "subtype": "success",
                    "result": "Done.\nAUTOMATION_STATUS: READY",
                },
                state,
            ),
        ]

        self.assertEqual("[system] init session=session-1\n", rendered[0])
        self.assertEqual("\n[assistant]\nWorking.\n", rendered[1])
        self.assertEqual("[result] success\n", rendered[2])
        self.assertEqual("session-1", state["session_id"])
        self.assertEqual("Done.\nAUTOMATION_STATUS: READY", state["final_message"])

    def test_render_claude_stream_event_includes_task_payload_summaries(
        self,
    ) -> None:
        state: dict[str, object] = {}

        started = claude_maid_loop.render_claude_stream_event(
            {
                "type": "system",
                "subtype": "task_started",
                "description": "Run focused validation",
                "task_type": "local_bash",
            },
            state,
        )
        progress = claude_maid_loop.render_claude_stream_event(
            {
                "type": "system",
                "subtype": "task_progress",
                "description": "Reading tests/core/test_example.py",
                "last_tool_name": "Read",
                "usage": {
                    "total_tokens": 1234,
                    "tool_uses": 5,
                    "duration_ms": 6789,
                },
            },
            state,
        )
        notification = claude_maid_loop.render_claude_stream_event(
            {
                "type": "system",
                "subtype": "task_notification",
                "status": "completed",
                "summary": "Implementation review",
                "usage": {
                    "total_tokens": 4321,
                    "tool_uses": 7,
                    "duration_ms": 9876,
                },
            },
            state,
        )

        self.assertEqual(
            "[system] task_started local_bash Run focused validation\n",
            started,
        )
        self.assertEqual(
            "[system] task_progress Reading tests/core/test_example.py "
            "tool=Read tools=5 tokens=1234 elapsed=6.8s\n",
            progress,
        )
        self.assertEqual(
            "[system] task_notification completed Implementation review "
            "tools=7 tokens=4321 elapsed=9.9s\n",
            notification,
        )

    def test_parse_automation_status_uses_last_valid_status(self) -> None:
        self.assertEqual(
            "BLOCKED",
            claude_maid_loop.parse_automation_status(
                "AUTOMATION_STATUS: READY\nlater\nAUTOMATION_STATUS: BLOCKED\n"
            ),
        )
        self.assertIsNone(claude_maid_loop.parse_automation_status("Ready."))

    def test_parse_commit_packet_stops_at_first_non_file_line(self) -> None:
        packet = claude_maid_loop.parse_commit_packet(
            "AUTOMATION_COMMIT_MESSAGE: feat: implement draft\n"
            "AUTOMATION_COMMIT_FILES:\n"
            "- tools/claude_maid_loop.py\n"
            "Notes:\n"
            "- not-a-file\n"
            "AUTOMATION_STATUS: READY\n"
        )

        self.assertIsNotNone(packet)
        assert packet is not None
        self.assertIsInstance(packet, claude_maid_loop.CommitPacket)
        self.assertEqual("feat: implement draft", packet.message)
        self.assertEqual(["tools/claude_maid_loop.py"], packet.files)

    def test_parse_commit_packet_uses_last_complete_packet(self) -> None:
        packet = claude_maid_loop.parse_commit_packet(
            "AUTOMATION_COMMIT_MESSAGE: test: selected draft\n"
            "AUTOMATION_COMMIT_FILES:\n"
            "- manifests/017-03-selected.manifest.yaml\n"
            "- manifests/drafts/017-03-selected.manifest.yaml\n"
            "AUTOMATION_STATUS: READY\n"
            "\n"
            "AUTOMATION_COMMIT_MESSAGE: feat: expanded scope\n"
            "AUTOMATION_COMMIT_FILES:\n"
            "- manifests/017-04-unselected.manifest.yaml\n"
            "- manifests/drafts/017-04-unselected.manifest.yaml\n"
            "AUTOMATION_STATUS: READY\n"
        )

        self.assertIsNotNone(packet)
        assert packet is not None
        self.assertEqual("feat: expanded scope", packet.message)
        self.assertEqual(
            [
                "manifests/017-04-unselected.manifest.yaml",
                "manifests/drafts/017-04-unselected.manifest.yaml",
            ],
            packet.files,
        )


class TestClaudeMaidLoopRun(unittest.TestCase):
    def test_dirty_worktree_blocks_new_passes(self) -> None:
        self.assertTrue(callable(claude_maid_loop.git_status_short))
        self.assertTrue(callable(claude_maid_loop.run_claude_stream_command))
        args = argparse.Namespace(
            dry_run=False,
            log_dir=None,
            once=True,
            max_passes=1,
            claude="claude",
            color="never",
            model="sonnet",
            effort="medium",
            permission_mode="auto",
            auto_commit=False,
        )

        with (
            mock.patch.object(
                claude_maid_loop,
                "git_status_short",
                return_value=" M tools/claude_maid_loop.py\n",
            ),
            mock.patch.object(
                claude_maid_loop,
                "run_claude_stream_command",
                side_effect=AssertionError("dirty worktree must block Claude"),
            ),
        ):
            code = claude_maid_loop.run_loop(args)

        self.assertEqual(2, code)

    def test_ready_pass_prompts_for_commit_by_default(self) -> None:
        self.assertTrue(callable(claude_maid_loop.ask_commit_approval))
        self.assertTrue(callable(claude_maid_loop.commit_ready_changes))
        args = argparse.Namespace(
            dry_run=False,
            log_dir=None,
            once=True,
            max_passes=1,
            claude="claude",
            color="never",
            model="sonnet",
            effort="medium",
            permission_mode="auto",
            auto_commit=False,
        )
        result = claude_maid_loop.ClaudeRunResult(
            args=["claude"],
            returncode=0,
            session_id="session-1",
            final_message=(
                "Done.\n"
                "AUTOMATION_COMMIT_MESSAGE: feat: implement draft\n"
                "AUTOMATION_COMMIT_FILES:\n"
                "- tools/claude_maid_loop.py\n"
                "AUTOMATION_STATUS: READY\n"
            ),
            stdout_jsonl_path=Path(".claude-automation/run.jsonl"),
            stderr_path=Path(".claude-automation/run.stderr.log"),
            final_message_path=Path(".claude-automation/run.final.md"),
        )

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch.object(claude_maid_loop, "git_status_short", return_value=""),
            mock.patch.object(
                claude_maid_loop,
                "find_implementable_drafts",
                return_value=[Path("manifests/drafts/017-03-example.manifest.yaml")],
            ),
            mock.patch.object(
                claude_maid_loop,
                "run_claude_stream_command",
                return_value=result,
            ),
            mock.patch.object(
                claude_maid_loop,
                "ask_commit_approval",
                return_value=False,
            ) as approve,
            mock.patch.object(
                claude_maid_loop,
                "commit_ready_changes",
                side_effect=AssertionError("commit must wait for approval"),
            ),
        ):
            args.log_dir = temp_dir
            code = claude_maid_loop.run_loop(args)

        self.assertEqual(0, code)
        approve.assert_called_once_with(1, "READY")

    def test_auto_commit_skips_interactive_prompt(self) -> None:
        args = argparse.Namespace(
            dry_run=False,
            log_dir=None,
            once=True,
            max_passes=1,
            claude="claude",
            color="never",
            model="sonnet",
            effort="medium",
            permission_mode="auto",
            auto_commit=True,
        )
        result = claude_maid_loop.ClaudeRunResult(
            args=["claude"],
            returncode=0,
            session_id="session-1",
            final_message=(
                "Done.\n"
                "AUTOMATION_COMMIT_MESSAGE: feat: implement draft\n"
                "AUTOMATION_COMMIT_FILES:\n"
                "- tools/claude_maid_loop.py\n"
                "AUTOMATION_STATUS: READY\n"
            ),
            stdout_jsonl_path=Path(".claude-automation/run.jsonl"),
            stderr_path=Path(".claude-automation/run.stderr.log"),
            final_message_path=Path(".claude-automation/run.final.md"),
        )

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch.object(claude_maid_loop, "git_status_short", return_value=""),
            mock.patch.object(
                claude_maid_loop,
                "find_implementable_drafts",
                return_value=[Path("manifests/drafts/017-03-example.manifest.yaml")],
            ),
            mock.patch.object(
                claude_maid_loop,
                "run_claude_stream_command",
                return_value=result,
            ),
            mock.patch.object(
                claude_maid_loop,
                "ask_commit_approval",
                side_effect=AssertionError("auto-commit must not prompt"),
            ),
            mock.patch.object(
                claude_maid_loop,
                "commit_ready_changes",
                return_value=0,
            ) as commit,
        ):
            args.log_dir = temp_dir
            code = claude_maid_loop.run_loop(args)

        self.assertEqual(0, code)
        commit.assert_called_once()

    def test_stage_commit_packet_files_rejects_directories_and_unsafe_paths(
        self,
    ) -> None:
        self.assertTrue(callable(claude_maid_loop.stage_commit_packet_files))
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch.object(claude_maid_loop, "_ROOT", Path(temp_dir)),
            mock.patch.object(
                claude_maid_loop,
                "_run_git",
                side_effect=AssertionError("invalid paths must not run git add"),
            ),
        ):
            (Path(temp_dir) / "logs").mkdir()
            code = claude_maid_loop.stage_commit_packet_files(
                ["logs", "../outside", "/tmp/outside"]
            )

        self.assertEqual(1, code)

    def test_loop_rechecks_future_drafts_after_each_ready_commit(self) -> None:
        args = argparse.Namespace(
            dry_run=False,
            log_dir=None,
            once=False,
            max_passes=2,
            claude="claude",
            color="never",
            model="sonnet",
            effort="medium",
            permission_mode="auto",
            auto_commit=True,
        )
        result = claude_maid_loop.ClaudeRunResult(
            args=["claude"],
            returncode=0,
            session_id="session-1",
            final_message=(
                "Done.\n"
                "AUTOMATION_COMMIT_MESSAGE: feat: implement draft\n"
                "AUTOMATION_COMMIT_FILES:\n"
                "- tools/claude_maid_loop.py\n"
                "AUTOMATION_STATUS: READY\n"
            ),
            stdout_jsonl_path=Path(".claude-automation/run.jsonl"),
            stderr_path=Path(".claude-automation/run.stderr.log"),
            final_message_path=Path(".claude-automation/run.final.md"),
        )

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch.object(claude_maid_loop, "git_status_short", return_value=""),
            mock.patch.object(
                claude_maid_loop,
                "find_implementable_drafts",
                side_effect=[
                    [Path("manifests/drafts/017-03-example.manifest.yaml")],
                    [],
                ],
            ) as drafts,
            mock.patch.object(
                claude_maid_loop,
                "run_claude_stream_command",
                return_value=result,
            ) as run_claude,
            mock.patch.object(claude_maid_loop, "commit_ready_changes", return_value=0),
        ):
            args.log_dir = temp_dir
            code = claude_maid_loop.run_loop(args)

        self.assertEqual(0, code)
        self.assertEqual(2, drafts.call_count)
        run_claude.assert_called_once()

    def test_ready_pass_rejects_unselected_draft_promotions(self) -> None:
        args = argparse.Namespace(
            dry_run=False,
            log_dir=None,
            once=True,
            max_passes=1,
            claude="claude",
            color="never",
            model="sonnet",
            effort="medium",
            permission_mode="auto",
            auto_commit=True,
            batch_size=1,
        )
        result = claude_maid_loop.ClaudeRunResult(
            args=["claude"],
            returncode=0,
            session_id="session-1",
            final_message=(
                "Done.\n"
                "AUTOMATION_COMMIT_MESSAGE: feat: implement too much\n"
                "AUTOMATION_COMMIT_FILES:\n"
                "- manifests/017-03-selected.manifest.yaml\n"
                "- manifests/017-04-unselected.manifest.yaml\n"
                "- manifests/drafts/017-04-unselected.manifest.yaml\n"
                "AUTOMATION_STATUS: READY\n"
            ),
            stdout_jsonl_path=Path(".claude-automation/run.jsonl"),
            stderr_path=Path(".claude-automation/run.stderr.log"),
            final_message_path=Path(".claude-automation/run.final.md"),
        )

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch.object(
                claude_maid_loop,
                "git_status_short",
                side_effect=[
                    "",
                    "?? manifests/017-03-selected.manifest.yaml\n"
                    " D manifests/drafts/017-03-selected.manifest.yaml\n"
                    "?? manifests/017-04-unselected.manifest.yaml\n"
                    " D manifests/drafts/017-04-unselected.manifest.yaml\n",
                ],
            ),
            mock.patch.object(
                claude_maid_loop,
                "find_implementable_drafts",
                return_value=[
                    Path("manifests/drafts/017-03-selected.manifest.yaml"),
                    Path("manifests/drafts/017-04-unselected.manifest.yaml"),
                ],
            ),
            mock.patch.object(
                claude_maid_loop,
                "run_claude_stream_command",
                return_value=result,
            ),
            mock.patch.object(
                claude_maid_loop,
                "commit_ready_changes",
                side_effect=AssertionError(
                    "unselected draft promotion must block commit"
                ),
            ),
        ):
            args.log_dir = temp_dir
            code = claude_maid_loop.run_loop(args)

        self.assertEqual(1, code)

    def test_ready_pass_rejects_copy_status_unselected_promotions(self) -> None:
        args = argparse.Namespace(
            dry_run=False,
            log_dir=None,
            once=True,
            max_passes=1,
            claude="claude",
            color="never",
            model="sonnet",
            effort="medium",
            permission_mode="auto",
            auto_commit=True,
            batch_size=1,
        )
        result = claude_maid_loop.ClaudeRunResult(
            args=["claude"],
            returncode=0,
            session_id="session-1",
            final_message=(
                "Done.\n"
                "AUTOMATION_COMMIT_MESSAGE: test: implement selected draft\n"
                "AUTOMATION_COMMIT_FILES:\n"
                "- manifests/017-03-selected.manifest.yaml\n"
                "- manifests/drafts/017-03-selected.manifest.yaml\n"
                "AUTOMATION_STATUS: READY\n"
            ),
            stdout_jsonl_path=Path(".claude-automation/run.jsonl"),
            stderr_path=Path(".claude-automation/run.stderr.log"),
            final_message_path=Path(".claude-automation/run.final.md"),
        )

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch.object(
                claude_maid_loop,
                "git_status_short",
                side_effect=[
                    "",
                    "C  manifests/000-source.manifest.yaml -> "
                    "manifests/017-04-unselected.manifest.yaml\n",
                ],
            ),
            mock.patch.object(
                claude_maid_loop,
                "find_implementable_drafts",
                return_value=[
                    Path("manifests/drafts/017-03-selected.manifest.yaml"),
                    Path("manifests/drafts/017-04-unselected.manifest.yaml"),
                ],
            ),
            mock.patch.object(
                claude_maid_loop,
                "run_claude_stream_command",
                return_value=result,
            ),
            mock.patch.object(
                claude_maid_loop,
                "commit_ready_changes",
                side_effect=AssertionError(
                    "copy-status unselected promotion must block commit"
                ),
            ),
        ):
            args.log_dir = temp_dir
            code = claude_maid_loop.run_loop(args)

        self.assertEqual(1, code)

    def test_ready_pass_rejects_rename_status_unselected_promotion_source(
        self,
    ) -> None:
        args = argparse.Namespace(
            dry_run=False,
            log_dir=None,
            once=True,
            max_passes=1,
            claude="claude",
            color="never",
            model="sonnet",
            effort="medium",
            permission_mode="auto",
            auto_commit=True,
            batch_size=1,
        )
        result = claude_maid_loop.ClaudeRunResult(
            args=["claude"],
            returncode=0,
            session_id="session-1",
            final_message=(
                "Done.\n"
                "AUTOMATION_COMMIT_MESSAGE: test: implement selected draft\n"
                "AUTOMATION_COMMIT_FILES:\n"
                "- manifests/017-03-selected.manifest.yaml\n"
                "- manifests/drafts/017-03-selected.manifest.yaml\n"
                "AUTOMATION_STATUS: READY\n"
            ),
            stdout_jsonl_path=Path(".claude-automation/run.jsonl"),
            stderr_path=Path(".claude-automation/run.stderr.log"),
            final_message_path=Path(".claude-automation/run.final.md"),
        )

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch.object(
                claude_maid_loop,
                "git_status_short",
                side_effect=[
                    "",
                    "R  manifests/017-04-unselected.manifest.yaml -> "
                    "manifests/017-03-selected.manifest.yaml\n",
                ],
            ),
            mock.patch.object(
                claude_maid_loop,
                "find_implementable_drafts",
                return_value=[
                    Path("manifests/drafts/017-03-selected.manifest.yaml"),
                    Path("manifests/drafts/017-04-unselected.manifest.yaml"),
                ],
            ),
            mock.patch.object(
                claude_maid_loop,
                "run_claude_stream_command",
                return_value=result,
            ),
            mock.patch.object(
                claude_maid_loop,
                "commit_ready_changes",
                side_effect=AssertionError(
                    "rename-source unselected promotion must block commit"
                ),
            ),
        ):
            args.log_dir = temp_dir
            code = claude_maid_loop.run_loop(args)

        self.assertEqual(1, code)

    def test_ready_pass_adds_matching_promoted_draft_deletion_to_commit_packet(
        self,
    ) -> None:
        args = argparse.Namespace(
            dry_run=False,
            log_dir=None,
            once=True,
            max_passes=1,
            claude="claude",
            color="never",
            model="sonnet",
            effort="medium",
            permission_mode="auto",
            auto_commit=True,
        )
        result = claude_maid_loop.ClaudeRunResult(
            args=["claude"],
            returncode=0,
            session_id="session-1",
            final_message=(
                "Done.\n"
                "AUTOMATION_COMMIT_MESSAGE: test: implement promoted draft\n"
                "AUTOMATION_COMMIT_FILES:\n"
                "- manifests/017-03-example.manifest.yaml\n"
                "- tests/core/test_example.py\n"
                "AUTOMATION_STATUS: READY\n"
            ),
            stdout_jsonl_path=Path(".claude-automation/run.jsonl"),
            stderr_path=Path(".claude-automation/run.stderr.log"),
            final_message_path=Path(".claude-automation/run.final.md"),
        )

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch.object(
                claude_maid_loop,
                "git_status_short",
                side_effect=[
                    "",
                    "A  manifests/017-03-example.manifest.yaml\n"
                    " D manifests/drafts/017-03-example.manifest.yaml\n",
                    "",
                ],
            ),
            mock.patch.object(
                claude_maid_loop,
                "find_implementable_drafts",
                return_value=[Path("manifests/drafts/017-03-example.manifest.yaml")],
            ),
            mock.patch.object(
                claude_maid_loop,
                "run_claude_stream_command",
                return_value=result,
            ),
            mock.patch.object(
                claude_maid_loop,
                "commit_ready_changes",
                return_value=0,
            ) as commit,
        ):
            args.log_dir = temp_dir
            code = claude_maid_loop.run_loop(args)

        self.assertEqual(0, code)
        committed_packet = commit.call_args.args[0]
        self.assertEqual(
            [
                "manifests/017-03-example.manifest.yaml",
                "tests/core/test_example.py",
                "manifests/drafts/017-03-example.manifest.yaml",
            ],
            committed_packet.files,
        )

    def test_parser_documents_auto_commit_and_permission_mode(self) -> None:
        help_text = claude_maid_loop.build_parser().format_help()

        self.assertIn("Run fresh-session Claude Code MAID draft passes", help_text)
        self.assertIn("--auto-commit", help_text)
        self.assertIn("--permission-mode", help_text)
        self.assertIn("without prompting", help_text)

    def test_parser_documents_explicit_batch_size(self) -> None:
        parser = claude_maid_loop.build_parser()
        help_text = parser.format_help()

        self.assertIn("--batch-size", help_text)
        self.assertEqual(1, parser.parse_args([]).batch_size)
        self.assertEqual(2, parser.parse_args(["--batch-size", "2"]).batch_size)

    def test_main_accepts_auto_commit_flag(self) -> None:
        with mock.patch.object(
            claude_maid_loop, "run_loop", return_value=0
        ) as run_loop:
            code = claude_maid_loop.main(["--once", "--auto-commit"])

        self.assertEqual(0, code)
        run_loop.assert_called_once()
        self.assertTrue(run_loop.call_args.args[0].auto_commit)


class TestClaudeMaidLoopRepoWiring(unittest.TestCase):
    def test_package_script_exposes_claude_loop(self) -> None:
        maid_claude_loop_script = "maid:claude-loop"
        package_json = (Path(__file__).resolve().parents[2] / "package.json").read_text(
            encoding="utf-8"
        )

        self.assertIn(f'"{maid_claude_loop_script}"', package_json)
        self.assertIn("tools/claude_maid_loop.py", package_json)

    def test_gitignore_excludes_claude_automation_logs(self) -> None:
        claude_automation_ignore = ".claude-automation/"
        gitignore = (Path(__file__).resolve().parents[2] / ".gitignore").read_text(
            encoding="utf-8"
        )

        self.assertIn(claude_automation_ignore, gitignore)

    def test_claude_draft_implement_skill_requires_claude_review_guidance(
        self,
    ) -> None:
        maid_runner_draft_implement_skill_guidance = [
            "maid-implementer",
            "maid-plan-review",
            "maid-implementation-review",
            "Agent tool",
            "maid-implementation-reviewer",
            "AUTOMATION_STATUS: READY",
        ]
        skill = (
            Path(__file__).resolve().parents[2]
            / ".claude/skills/maid-runner-draft-implement/SKILL.md"
        ).read_text(encoding="utf-8")

        for expected_text in maid_runner_draft_implement_skill_guidance:
            self.assertIn(expected_text, skill)

    def test_claude_draft_implement_skill_requires_selected_scope_guidance(
        self,
    ) -> None:
        selected_scope_guidance = [
            "automation-selected draft manifest",
            "Do not promote unselected draft manifests",
        ]
        skill = (
            Path(__file__).resolve().parents[2]
            / ".claude/skills/maid-runner-draft-implement/SKILL.md"
        ).read_text(encoding="utf-8")

        for expected_text in selected_scope_guidance:
            self.assertIn(expected_text, skill)


if __name__ == "__main__":
    unittest.main()
