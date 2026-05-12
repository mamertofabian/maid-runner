import argparse
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import codex_maid_loop


class TestCodexMaidLoopDiscovery(unittest.TestCase):
    def test_find_implementable_drafts_excludes_epics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            draft_dir = Path(temp_dir)
            child = draft_dir / "017-01-example.manifest.yaml"
            epic = draft_dir / "000-example.epic.yaml"
            child.write_text("schema: '2'\n", encoding="utf-8")
            epic.write_text("schema: '2'\n", encoding="utf-8")

            drafts = codex_maid_loop.find_implementable_drafts(draft_dir)

        self.assertEqual([child], drafts)


class TestCodexMaidLoopCommand(unittest.TestCase):
    def test_build_implementation_command_uses_fresh_exec_session_and_repo_skill(
        self,
    ) -> None:
        final_path = Path("/tmp/final.md")

        command = codex_maid_loop.build_implementation_command(
            codex="codex",
            final_message_path=final_path,
            selected_drafts=[Path("manifests/drafts/017-01-example.manifest.yaml")],
        )

        self.assertEqual(
            [
                "codex",
                "--ask-for-approval",
                "on-request",
                "-c",
                'approvals_reviewer="auto_review"',
                "exec",
            ],
            command[:6],
        )
        self.assertIn("--model", command)
        self.assertEqual("gpt-5.5", command[command.index("--model") + 1])
        self.assertIn("-c", command)
        self.assertIn("model_reasoning_effort=medium", command)
        self.assertIn("--json", command)
        self.assertIn("--cd", command)
        self.assertEqual("maid-runner", Path(command[command.index("--cd") + 1]).name)
        self.assertIn("--sandbox", command)
        self.assertEqual("workspace-write", command[command.index("--sandbox") + 1])
        self.assertIn("--output-last-message", command)
        self.assertIn("maid-runner-draft-implement", command[-1])
        self.assertIn(".codex/skills/maid-runner-draft-implement/SKILL.md", command[-1])
        self.assertNotIn(".claude/skills/maid-runner-draft-implement", command[-1])
        self.assertIn("AUTOMATION_STATUS: READY", command[-1])
        self.assertIn("AUTOMATION_COMMIT_MESSAGE", command[-1])
        self.assertIn("fork_context=false", command[-1])
        self.assertIn("close_agent", command[-1])

    def test_build_implementation_command_scopes_prompt_to_selected_draft(
        self,
    ) -> None:
        final_path = Path("/tmp/final.md")
        selected_draft = Path(
            "manifests/drafts/017-03-preserve-third-party-package-boundary.manifest.yaml"
        )

        command = codex_maid_loop.build_implementation_command(
            codex="codex",
            final_message_path=final_path,
            selected_drafts=[selected_draft],
        )

        self.assertIn("Selected draft manifest(s) for this pass:", command[-1])
        self.assertIn(selected_draft.as_posix(), command[-1])
        self.assertIn("Implement only the selected draft manifest(s)", command[-1])
        self.assertIn(
            "Do not promote, edit, delete, or implement any other", command[-1]
        )


class TestCodexMaidLoopRenderer(unittest.TestCase):
    def test_render_codex_json_event_handles_documented_events(self) -> None:
        state: dict[str, object] = {}

        rendered = [
            codex_maid_loop.render_codex_json_event(
                {"type": "thread.started", "thread_id": "session-1"},
                state,
            ),
            codex_maid_loop.render_codex_json_event(
                {
                    "type": "item.started",
                    "item": {
                        "id": "item_1",
                        "type": "command_execution",
                        "command": "bash -lc ls",
                        "status": "in_progress",
                    },
                },
                state,
            ),
            codex_maid_loop.render_codex_json_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_2",
                        "type": "agent_message",
                        "text": "Ready.\nAUTOMATION_STATUS: READY",
                    },
                },
                state,
            ),
            codex_maid_loop.render_codex_json_event(
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
                state,
            ),
            codex_maid_loop.render_codex_json_event(
                {"type": "error", "message": "bad request"},
                state,
            ),
        ]

        self.assertEqual("[thread] session-1\n", rendered[0])
        self.assertEqual("[command:started] bash -lc ls\n", rendered[1])
        self.assertIn("[assistant]", rendered[2])
        self.assertEqual("[turn] completed input=10 output=5\n", rendered[3])
        self.assertEqual("[error] bad request\n", rendered[4])
        self.assertEqual("session-1", state["session_id"])

    def test_parse_automation_status_uses_last_valid_status(self) -> None:
        self.assertEqual(
            "BLOCKED",
            codex_maid_loop.parse_automation_status(
                "AUTOMATION_STATUS: READY\nlater\nAUTOMATION_STATUS: BLOCKED\n"
            ),
        )
        self.assertIsNone(codex_maid_loop.parse_automation_status("Ready to merge"))

    def test_parse_commit_packet(self) -> None:
        packet = codex_maid_loop.parse_commit_packet(
            "Done.\n"
            "AUTOMATION_COMMIT_MESSAGE: feat: implement draft loop\n"
            "AUTOMATION_COMMIT_FILES:\n"
            "- manifests/017-01-example.manifest.yaml\n"
            "- tools/codex_maid_loop.py\n"
            "AUTOMATION_STATUS: READY\n"
        )

        self.assertIsNotNone(packet)
        assert packet is not None
        self.assertEqual("feat: implement draft loop", packet.message)
        self.assertEqual(
            [
                "manifests/017-01-example.manifest.yaml",
                "tools/codex_maid_loop.py",
            ],
            packet.files,
        )

    def test_parse_commit_packet_stops_at_first_non_file_line(self) -> None:
        packet = codex_maid_loop.parse_commit_packet(
            "AUTOMATION_COMMIT_MESSAGE: feat: implement draft loop\n"
            "AUTOMATION_COMMIT_FILES:\n"
            "- tools/codex_maid_loop.py\n"
            "Notes:\n"
            "- not-a-file\n"
            "AUTOMATION_STATUS: READY\n"
        )

        self.assertIsNotNone(packet)
        assert packet is not None
        self.assertEqual(["tools/codex_maid_loop.py"], packet.files)

    def test_parse_commit_packet_uses_last_complete_packet(self) -> None:
        packet = codex_maid_loop.parse_commit_packet(
            "AUTOMATION_COMMIT_MESSAGE: test: selected draft\n"
            "AUTOMATION_COMMIT_FILES:\n"
            "- manifests/017-01-selected.manifest.yaml\n"
            "- manifests/drafts/017-01-selected.manifest.yaml\n"
            "AUTOMATION_STATUS: READY\n"
            "\n"
            "AUTOMATION_COMMIT_MESSAGE: feat: expanded scope\n"
            "AUTOMATION_COMMIT_FILES:\n"
            "- manifests/017-02-unselected.manifest.yaml\n"
            "- manifests/drafts/017-02-unselected.manifest.yaml\n"
            "AUTOMATION_STATUS: READY\n"
        )

        self.assertIsNotNone(packet)
        assert packet is not None
        self.assertEqual("feat: expanded scope", packet.message)
        self.assertEqual(
            [
                "manifests/017-02-unselected.manifest.yaml",
                "manifests/drafts/017-02-unselected.manifest.yaml",
            ],
            packet.files,
        )


class TestCodexMaidLoopRun(unittest.TestCase):
    def test_dirty_worktree_blocks_new_passes(self) -> None:
        self.assertTrue(callable(codex_maid_loop.git_status_short))
        self.assertTrue(callable(codex_maid_loop.run_codex_json_command))
        args = argparse.Namespace(
            dry_run=False,
            log_dir=None,
            once=True,
            max_passes=1,
            codex="codex",
            color="never",
            model="gpt-5.5",
            reasoning_effort="medium",
            auto_commit=False,
        )

        with (
            mock.patch.object(
                codex_maid_loop,
                "git_status_short",
                return_value=" M tools/codex_maid_loop.py\n",
            ),
            mock.patch.object(
                codex_maid_loop,
                "run_codex_json_command",
                side_effect=AssertionError("dirty worktree must block Codex"),
            ),
        ):
            code = codex_maid_loop.run_loop(args)

        self.assertEqual(2, code)

    def test_ready_pass_prompts_for_commit_by_default(self) -> None:
        self.assertTrue(callable(codex_maid_loop.ask_commit_approval))
        self.assertTrue(callable(codex_maid_loop.commit_ready_changes))
        args = argparse.Namespace(
            dry_run=False,
            log_dir=None,
            once=True,
            max_passes=1,
            codex="codex",
            color="never",
            model="gpt-5.5",
            reasoning_effort="medium",
            auto_commit=False,
        )
        final_message = (
            "Done.\n"
            "AUTOMATION_COMMIT_MESSAGE: feat: implement draft\n"
            "AUTOMATION_COMMIT_FILES:\n"
            "- tools/codex_maid_loop.py\n"
            "AUTOMATION_STATUS: READY\n"
        )
        result = codex_maid_loop.CodexRunResult(
            args=["codex"],
            returncode=0,
            session_id="session-1",
            final_message=final_message,
            stdout_jsonl_path=Path(".codex-automation/run.jsonl"),
            stderr_path=Path(".codex-automation/run.stderr.log"),
            final_message_path=Path(".codex-automation/run.final.md"),
        )

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch.object(codex_maid_loop, "git_status_short", return_value=""),
            mock.patch.object(
                codex_maid_loop,
                "find_implementable_drafts",
                return_value=[Path("manifests/drafts/017-01-example.manifest.yaml")],
            ),
            mock.patch.object(
                codex_maid_loop,
                "run_codex_json_command",
                return_value=result,
            ),
            mock.patch.object(
                codex_maid_loop,
                "ask_commit_approval",
                return_value=False,
            ) as approve,
            mock.patch.object(
                codex_maid_loop,
                "commit_ready_changes",
                side_effect=AssertionError("commit must wait for approval"),
            ),
        ):
            args.log_dir = temp_dir
            code = codex_maid_loop.run_loop(args)

        self.assertEqual(0, code)
        approve.assert_called_once_with(1, "READY")

    def test_ready_pass_commits_only_after_explicit_approval(self) -> None:
        self.assertTrue(callable(codex_maid_loop.stage_commit_packet_files))
        args = argparse.Namespace(
            dry_run=False,
            log_dir=None,
            once=True,
            max_passes=1,
            codex="codex",
            color="never",
            model="gpt-5.5",
            reasoning_effort="medium",
            auto_commit=False,
        )
        final_message = (
            "Done.\n"
            "AUTOMATION_COMMIT_MESSAGE: feat: implement draft\n"
            "AUTOMATION_COMMIT_FILES:\n"
            "- tools/codex_maid_loop.py\n"
            "AUTOMATION_STATUS: READY\n"
        )
        result = codex_maid_loop.CodexRunResult(
            args=["codex"],
            returncode=0,
            session_id="session-1",
            final_message=final_message,
            stdout_jsonl_path=Path(".codex-automation/run.jsonl"),
            stderr_path=Path(".codex-automation/run.stderr.log"),
            final_message_path=Path(".codex-automation/run.final.md"),
        )

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch.object(codex_maid_loop, "git_status_short", return_value=""),
            mock.patch.object(
                codex_maid_loop,
                "find_implementable_drafts",
                return_value=[Path("manifests/drafts/017-01-example.manifest.yaml")],
            ),
            mock.patch.object(
                codex_maid_loop,
                "run_codex_json_command",
                return_value=result,
            ),
            mock.patch.object(
                codex_maid_loop,
                "ask_commit_approval",
                return_value=True,
            ),
            mock.patch.object(
                codex_maid_loop,
                "commit_ready_changes",
                return_value=0,
            ) as commit,
        ):
            args.log_dir = temp_dir
            code = codex_maid_loop.run_loop(args)

        self.assertEqual(0, code)
        commit.assert_called_once()
        self.assertIsInstance(commit.call_args.args[0], codex_maid_loop.CommitPacket)

    def test_auto_commit_skips_interactive_prompt(self) -> None:
        args = argparse.Namespace(
            dry_run=False,
            log_dir=None,
            once=True,
            max_passes=1,
            codex="codex",
            color="never",
            model="gpt-5.5",
            reasoning_effort="medium",
            auto_commit=True,
        )
        final_message = (
            "Done.\n"
            "AUTOMATION_COMMIT_MESSAGE: feat: implement draft\n"
            "AUTOMATION_COMMIT_FILES:\n"
            "- tools/codex_maid_loop.py\n"
            "AUTOMATION_STATUS: READY\n"
        )
        result = codex_maid_loop.CodexRunResult(
            args=["codex"],
            returncode=0,
            session_id="session-1",
            final_message=final_message,
            stdout_jsonl_path=Path(".codex-automation/run.jsonl"),
            stderr_path=Path(".codex-automation/run.stderr.log"),
            final_message_path=Path(".codex-automation/run.final.md"),
        )

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch.object(codex_maid_loop, "git_status_short", return_value=""),
            mock.patch.object(
                codex_maid_loop,
                "find_implementable_drafts",
                return_value=[Path("manifests/drafts/017-01-example.manifest.yaml")],
            ),
            mock.patch.object(
                codex_maid_loop,
                "run_codex_json_command",
                return_value=result,
            ),
            mock.patch.object(
                codex_maid_loop,
                "ask_commit_approval",
                side_effect=AssertionError("auto-commit must not prompt"),
            ),
            mock.patch.object(
                codex_maid_loop,
                "commit_ready_changes",
                return_value=0,
            ) as commit,
        ):
            args.log_dir = temp_dir
            code = codex_maid_loop.run_loop(args)

        self.assertEqual(0, code)
        commit.assert_called_once()

    def test_ready_pass_rejects_unlisted_dirty_paths_before_commit(self) -> None:
        args = argparse.Namespace(
            dry_run=False,
            log_dir=None,
            once=True,
            max_passes=1,
            codex="codex",
            color="never",
            model="gpt-5.5",
            reasoning_effort="medium",
            auto_commit=True,
            batch_size=1,
        )
        result = codex_maid_loop.CodexRunResult(
            args=["codex"],
            returncode=0,
            session_id="session-1",
            final_message=(
                "Done.\n"
                "AUTOMATION_COMMIT_MESSAGE: test: incomplete packet\n"
                "AUTOMATION_COMMIT_FILES:\n"
                "- tools/codex_maid_loop.py\n"
                "AUTOMATION_STATUS: READY\n"
            ),
            stdout_jsonl_path=Path(".codex-automation/run.jsonl"),
            stderr_path=Path(".codex-automation/run.stderr.log"),
            final_message_path=Path(".codex-automation/run.final.md"),
        )

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch.object(
                codex_maid_loop,
                "git_status_short",
                side_effect=[
                    "",
                    " M tools/codex_maid_loop.py\n"
                    " M tests/ci/test_codex_maid_loop.py\n",
                ],
            ),
            mock.patch.object(
                codex_maid_loop,
                "find_implementable_drafts",
                return_value=[Path("manifests/drafts/017-01-selected.manifest.yaml")],
            ),
            mock.patch.object(
                codex_maid_loop,
                "run_codex_json_command",
                return_value=result,
            ),
            mock.patch.object(
                codex_maid_loop,
                "commit_ready_changes",
                side_effect=AssertionError("incomplete packet must block commit"),
            ),
        ):
            args.log_dir = temp_dir
            code = codex_maid_loop.run_loop(args)

        self.assertEqual(1, code)

    def test_ready_pass_rejects_unselected_draft_promotions(self) -> None:
        args = argparse.Namespace(
            dry_run=False,
            log_dir=None,
            once=True,
            max_passes=1,
            codex="codex",
            color="never",
            model="gpt-5.5",
            reasoning_effort="medium",
            auto_commit=True,
            batch_size=1,
        )
        result = codex_maid_loop.CodexRunResult(
            args=["codex"],
            returncode=0,
            session_id="session-1",
            final_message=(
                "Done.\n"
                "AUTOMATION_COMMIT_MESSAGE: feat: implement too much\n"
                "AUTOMATION_COMMIT_FILES:\n"
                "- manifests/017-01-selected.manifest.yaml\n"
                "- manifests/017-02-unselected.manifest.yaml\n"
                "- manifests/drafts/017-02-unselected.manifest.yaml\n"
                "AUTOMATION_STATUS: READY\n"
            ),
            stdout_jsonl_path=Path(".codex-automation/run.jsonl"),
            stderr_path=Path(".codex-automation/run.stderr.log"),
            final_message_path=Path(".codex-automation/run.final.md"),
        )

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch.object(
                codex_maid_loop,
                "git_status_short",
                side_effect=[
                    "",
                    "?? manifests/017-01-selected.manifest.yaml\n"
                    " D manifests/drafts/017-01-selected.manifest.yaml\n"
                    "?? manifests/017-02-unselected.manifest.yaml\n"
                    " D manifests/drafts/017-02-unselected.manifest.yaml\n",
                ],
            ),
            mock.patch.object(
                codex_maid_loop,
                "find_implementable_drafts",
                return_value=[
                    Path("manifests/drafts/017-01-selected.manifest.yaml"),
                    Path("manifests/drafts/017-02-unselected.manifest.yaml"),
                ],
            ),
            mock.patch.object(
                codex_maid_loop,
                "run_codex_json_command",
                return_value=result,
            ),
            mock.patch.object(
                codex_maid_loop,
                "commit_ready_changes",
                side_effect=AssertionError(
                    "unselected draft promotion must block commit"
                ),
            ),
        ):
            args.log_dir = temp_dir
            code = codex_maid_loop.run_loop(args)

        self.assertEqual(1, code)

    def test_ready_pass_rejects_copy_status_unselected_promotions(self) -> None:
        args = argparse.Namespace(
            dry_run=False,
            log_dir=None,
            once=True,
            max_passes=1,
            codex="codex",
            color="never",
            model="gpt-5.5",
            reasoning_effort="medium",
            auto_commit=True,
            batch_size=1,
        )
        result = codex_maid_loop.CodexRunResult(
            args=["codex"],
            returncode=0,
            session_id="session-1",
            final_message=(
                "Done.\n"
                "AUTOMATION_COMMIT_MESSAGE: test: implement selected draft\n"
                "AUTOMATION_COMMIT_FILES:\n"
                "- manifests/017-01-selected.manifest.yaml\n"
                "- manifests/drafts/017-01-selected.manifest.yaml\n"
                "AUTOMATION_STATUS: READY\n"
            ),
            stdout_jsonl_path=Path(".codex-automation/run.jsonl"),
            stderr_path=Path(".codex-automation/run.stderr.log"),
            final_message_path=Path(".codex-automation/run.final.md"),
        )

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch.object(
                codex_maid_loop,
                "git_status_short",
                side_effect=[
                    "",
                    "C  manifests/000-source.manifest.yaml -> "
                    "manifests/017-02-unselected.manifest.yaml\n",
                ],
            ),
            mock.patch.object(
                codex_maid_loop,
                "find_implementable_drafts",
                return_value=[
                    Path("manifests/drafts/017-01-selected.manifest.yaml"),
                    Path("manifests/drafts/017-02-unselected.manifest.yaml"),
                ],
            ),
            mock.patch.object(
                codex_maid_loop,
                "run_codex_json_command",
                return_value=result,
            ),
            mock.patch.object(
                codex_maid_loop,
                "commit_ready_changes",
                side_effect=AssertionError(
                    "copy-status unselected promotion must block commit"
                ),
            ),
        ):
            args.log_dir = temp_dir
            code = codex_maid_loop.run_loop(args)

        self.assertEqual(1, code)

    def test_ready_pass_rejects_rename_status_unselected_promotion_source(
        self,
    ) -> None:
        args = argparse.Namespace(
            dry_run=False,
            log_dir=None,
            once=True,
            max_passes=1,
            codex="codex",
            color="never",
            model="gpt-5.5",
            reasoning_effort="medium",
            auto_commit=True,
            batch_size=1,
        )
        result = codex_maid_loop.CodexRunResult(
            args=["codex"],
            returncode=0,
            session_id="session-1",
            final_message=(
                "Done.\n"
                "AUTOMATION_COMMIT_MESSAGE: test: implement selected draft\n"
                "AUTOMATION_COMMIT_FILES:\n"
                "- manifests/017-01-selected.manifest.yaml\n"
                "- manifests/drafts/017-01-selected.manifest.yaml\n"
                "AUTOMATION_STATUS: READY\n"
            ),
            stdout_jsonl_path=Path(".codex-automation/run.jsonl"),
            stderr_path=Path(".codex-automation/run.stderr.log"),
            final_message_path=Path(".codex-automation/run.final.md"),
        )

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch.object(
                codex_maid_loop,
                "git_status_short",
                side_effect=[
                    "",
                    "R  manifests/017-02-unselected.manifest.yaml -> "
                    "manifests/017-01-selected.manifest.yaml\n",
                ],
            ),
            mock.patch.object(
                codex_maid_loop,
                "find_implementable_drafts",
                return_value=[
                    Path("manifests/drafts/017-01-selected.manifest.yaml"),
                    Path("manifests/drafts/017-02-unselected.manifest.yaml"),
                ],
            ),
            mock.patch.object(
                codex_maid_loop,
                "run_codex_json_command",
                return_value=result,
            ),
            mock.patch.object(
                codex_maid_loop,
                "commit_ready_changes",
                side_effect=AssertionError(
                    "rename-source unselected promotion must block commit"
                ),
            ),
        ):
            args.log_dir = temp_dir
            code = codex_maid_loop.run_loop(args)

        self.assertEqual(1, code)

    def test_stage_commit_packet_files_rejects_directories_and_unsafe_paths(
        self,
    ) -> None:
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch.object(codex_maid_loop, "_ROOT", Path(temp_dir)),
            mock.patch.object(
                codex_maid_loop,
                "_run_git",
                side_effect=AssertionError("invalid paths must not run git add"),
            ),
        ):
            (Path(temp_dir) / "logs").mkdir()
            code = codex_maid_loop.stage_commit_packet_files(
                ["logs", "../outside", "/tmp/outside"]
            )

        self.assertEqual(1, code)

    def test_stage_commit_packet_files_rejects_missing_untracked_paths(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch.object(codex_maid_loop, "_ROOT", Path(temp_dir)),
            mock.patch.object(
                codex_maid_loop,
                "_run_git",
                side_effect=AssertionError("missing packet files must not be staged"),
            ),
        ):
            code = codex_maid_loop.stage_commit_packet_files(["missing.txt"])

        self.assertEqual(1, code)

    def test_loop_rechecks_future_drafts_after_each_ready_commit(self) -> None:
        args = argparse.Namespace(
            dry_run=False,
            log_dir=None,
            once=False,
            max_passes=2,
            codex="codex",
            color="never",
            model="gpt-5.5",
            reasoning_effort="medium",
            auto_commit=False,
        )
        final_message = (
            "Done.\n"
            "AUTOMATION_COMMIT_MESSAGE: feat: implement draft\n"
            "AUTOMATION_COMMIT_FILES:\n"
            "- tools/codex_maid_loop.py\n"
            "AUTOMATION_STATUS: READY\n"
        )
        result = codex_maid_loop.CodexRunResult(
            args=["codex"],
            returncode=0,
            session_id="session-1",
            final_message=final_message,
            stdout_jsonl_path=Path(".codex-automation/run.jsonl"),
            stderr_path=Path(".codex-automation/run.stderr.log"),
            final_message_path=Path(".codex-automation/run.final.md"),
        )

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch.object(codex_maid_loop, "git_status_short", return_value=""),
            mock.patch.object(
                codex_maid_loop,
                "find_implementable_drafts",
                side_effect=[
                    [Path("manifests/drafts/017-01-example.manifest.yaml")],
                    [],
                ],
            ) as drafts,
            mock.patch.object(
                codex_maid_loop,
                "run_codex_json_command",
                return_value=result,
            ) as run_codex,
            mock.patch.object(
                codex_maid_loop, "ask_commit_approval", return_value=True
            ),
            mock.patch.object(codex_maid_loop, "commit_ready_changes", return_value=0),
        ):
            args.log_dir = temp_dir
            code = codex_maid_loop.run_loop(args)

        self.assertEqual(0, code)
        self.assertEqual(2, drafts.call_count)
        run_codex.assert_called_once()

    def test_parser_documents_auto_commit_and_default_prompt(self) -> None:
        help_text = codex_maid_loop.build_parser().format_help()

        self.assertIn(
            "Run fresh-session Codex MAID draft implementation passes", help_text
        )
        self.assertIn("typed commit approval", help_text)
        self.assertIn("--auto-commit", help_text)
        self.assertIn("without prompting", help_text)

    def test_parser_keeps_commit_approval_explicit(self) -> None:
        parser = codex_maid_loop.build_parser()
        args = parser.parse_args([])
        help_text = parser.format_help()

        self.assertFalse(args.auto_commit)
        self.assertIn("typed commit approval", help_text)
        self.assertIn("--auto-commit", help_text)

    def test_parser_documents_explicit_batch_size(self) -> None:
        parser = codex_maid_loop.build_parser()
        help_text = parser.format_help()

        self.assertIn("--batch-size", help_text)
        self.assertEqual(1, parser.parse_args([]).batch_size)
        self.assertEqual(2, parser.parse_args(["--batch-size", "2"]).batch_size)

    def test_main_accepts_auto_commit_flag(self) -> None:
        with mock.patch.object(codex_maid_loop, "run_loop", return_value=0) as run_loop:
            code = codex_maid_loop.main(["--once", "--auto-commit", "--color", "never"])

        self.assertEqual(0, code)
        run_loop.assert_called_once()
        self.assertTrue(run_loop.call_args.args[0].auto_commit)


class TestCodexMaidLoopRepoWiring(unittest.TestCase):
    def test_package_script_exposes_codex_loop(self) -> None:
        maid_codex_loop_script = "maid:codex-loop"
        package_json = (Path(__file__).resolve().parents[2] / "package.json").read_text(
            encoding="utf-8"
        )

        self.assertIn(f'"{maid_codex_loop_script}"', package_json)
        self.assertIn("tools/codex_maid_loop.py", package_json)

    def test_gitignore_excludes_codex_automation_logs(self) -> None:
        codex_automation_ignore = ".codex-automation/"
        gitignore = (Path(__file__).resolve().parents[2] / ".gitignore").read_text(
            encoding="utf-8"
        )

        self.assertIn(codex_automation_ignore, gitignore)

    def test_draft_implement_skill_requires_review_loop_guidance(self) -> None:
        maid_runner_draft_implement_skill_guidance = [
            "maid-implementer",
            "maid-plan-review",
            "maid-implementation-review",
            "fork_context=false",
            "agent_type=explorer",
            "close_agent",
            "AUTOMATION_STATUS: READY",
        ]
        skill = (
            Path(__file__).resolve().parents[2]
            / ".codex/skills/maid-runner-draft-implement/SKILL.md"
        ).read_text(encoding="utf-8")

        for expected_text in maid_runner_draft_implement_skill_guidance:
            self.assertIn(expected_text, skill)

    def test_draft_manifest_workflow_docs_preserve_lifecycle_contract(self) -> None:
        root = Path(__file__).resolve().parents[2]
        workflow = (root / "docs/draft-manifest-workflow.md").read_text(
            encoding="utf-8"
        )
        readme = (root / "README.md").read_text(encoding="utf-8")
        contributing = (root / "CONTRIBUTING.md").read_text(encoding="utf-8")
        drafts_readme = (root / "manifests/drafts/README.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("Draft manifests are MAID planning inventory", workflow)
        self.assertIn("Promoted manifests are active\ncontracts", workflow)
        self.assertIn("Promote one implementation-sized draft", workflow)
        self.assertIn("Use the loop script's explicit batch option", workflow)
        self.assertIn(
            "[Draft Manifest Workflow](docs/draft-manifest-workflow.md)", readme
        )
        self.assertIn("planning inventory in `manifests/drafts/`", readme)
        self.assertNotIn("child contracts in `manifests/drafts/`", readme)
        self.assertIn(
            "[docs/draft-manifest-workflow.md](docs/draft-manifest-workflow.md)",
            contributing,
        )
        self.assertIn("../../docs/draft-manifest-workflow.md", drafts_readme)
        self.assertIn("Draft manifests are planning inventory", drafts_readme)
        self.assertNotIn("Draft manifests are planning contracts", drafts_readme)

    def test_draft_implement_skill_requires_selected_scope_guidance(self) -> None:
        selected_scope_guidance = [
            "automation-selected draft manifest",
            "Do not promote unselected draft manifests",
        ]
        skill = (
            Path(__file__).resolve().parents[2]
            / ".codex/skills/maid-runner-draft-implement/SKILL.md"
        ).read_text(encoding="utf-8")

        for expected_text in selected_scope_guidance:
            self.assertIn(expected_text, skill)


if __name__ == "__main__":
    unittest.main()
