import unittest
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from scripts.pr import LlamaServerClient, PRCreator, build_parser


class LlamaServerClientPRContentTests(unittest.TestCase):
    @staticmethod
    def _response(content, finish_reason="stop"):
        response = Mock()
        response.json.return_value = {
            "choices": [
                {
                    "finish_reason": finish_reason,
                    "message": {"content": content},
                }
            ]
        }
        return response

    @staticmethod
    def _git_changes():
        return {
            "branch": "feat/example",
            "files": "contents/admin.py",
            "commits": "abc123 Add example",
            "diff": "+example",
        }

    @patch("scripts.pr.requests.post")
    def test_retries_when_first_response_is_truncated_json(self, post):
        post.side_effect = [
            self._response(
                '{"title":"Improve admin","description":"This response was cut off',
                finish_reason="length",
            ),
            self._response(
                '{"title":"Improve admin","description":"Populate slugs automatically."}'
            ),
        ]
        client = LlamaServerClient("http://llama-server.test/v1/chat/completions", "")

        title, description = client.generate_pr_content(self._git_changes())

        self.assertEqual(title, "Improve admin")
        self.assertEqual(description, "Populate slugs automatically.")
        self.assertEqual(post.call_count, 2)
        self.assertEqual(
            post.call_args_list[0].kwargs["json"]["chat_template_kwargs"],
            {"enable_thinking": False},
        )
        self.assertGreater(
            post.call_args_list[0].kwargs["json"]["max_tokens"],
            2000,
        )
        self.assertGreater(
            post.call_args_list[1].kwargs["json"]["max_tokens"],
            post.call_args_list[0].kwargs["json"]["max_tokens"],
        )

    @patch("scripts.pr.requests.post")
    def test_reports_clear_error_when_retry_is_still_invalid(self, post):
        post.side_effect = [
            self._response('{"title":"First","description":"cut off', "length"),
            self._response('{"title":"Second","description":"also cut off', "length"),
        ]
        client = LlamaServerClient("http://llama-server.test/v1/chat/completions", "")

        with self.assertRaisesRegex(
            ValueError,
            "invalid or truncated JSON after 2 attempts",
        ):
            client.generate_pr_content(self._git_changes())

    @patch("scripts.pr.requests.post")
    def test_disables_thinking_for_commit_message_generation(self, post):
        post.return_value = self._response("fix: improve admin slug behavior")
        client = LlamaServerClient("http://llama-server.test/v1/chat/completions", "")

        message = client.generate_commit_message("+example", "contents/admin.py")

        self.assertEqual(message, "fix: improve admin slug behavior")
        self.assertEqual(
            post.call_args.kwargs["json"]["chat_template_kwargs"],
            {"enable_thinking": False},
        )


class ReleaseWorkflowTests(unittest.TestCase):
    @staticmethod
    def _creator(bypass_confirm=True):
        args = SimpleNamespace(
            api_url=None,
            model="",
            bypass_confirm=bypass_confirm,
            commit=False,
            apply=False,
            release=True,
            dry_run=False,
        )
        return PRCreator(args)

    def test_parser_exposes_explicit_release_mode(self):
        args = build_parser().parse_args(["--release", "--bypass-confirm"])

        self.assertTrue(args.release)
        self.assertTrue(args.bypass_confirm)

    def test_parser_exposes_dry_run_mode(self):
        args = build_parser().parse_args(["--dry-run"])

        self.assertTrue(args.dry_run)

    @patch("scripts.pr.run_command", return_value=("feat/example", 0))
    def test_dry_run_prints_generated_pr_without_creating_it(self, _command):
        args = SimpleNamespace(
            api_url=None,
            model="",
            bypass_confirm=False,
            commit=False,
            apply=False,
            release=False,
            dry_run=True,
        )
        creator = PRCreator(args)
        creator.get_git_changes = Mock(
            return_value={
                "branch": "feat/example",
                "files": "example.py",
                "commits": "abc123 feat: add example",
                "diff": "+example",
            }
        )
        creator.llama_server.generate_pr_content = Mock(
            return_value=("Add example", "Explain the example in detail.")
        )
        creator.handle_pr = Mock()

        output = StringIO()
        with redirect_stdout(output):
            result = creator.run()

        self.assertEqual(result, 0)
        self.assertIn("PR Title:\nAdd example", output.getvalue())
        self.assertIn(
            "PR Description:\nExplain the example in detail.", output.getvalue()
        )
        self.assertIn(
            "*This PR was created via the automated PR script.*", output.getvalue()
        )
        creator.handle_pr.assert_not_called()
        _command.assert_called_once_with(["git", "branch", "--show-current"])

    @patch("scripts.pr.run_command", return_value=("release/v2.next", 0))
    def test_release_dry_run_prints_content_without_publishing(self, _command):
        creator = self._creator()
        creator.args.dry_run = True
        creator.ensure_release_ready = Mock()
        creator.get_head_sha = Mock(return_value="head123")
        creator.get_release_version = Mock(return_value="2.21.2")
        creator.get_git_changes = Mock(
            return_value={
                "branch": "release/v2.next",
                "files": "CHANGELOG.md\npyproject.toml",
                "commits": "abc123 release: bump maid-runner to v2.21.2",
                "diff": "+version = 2.21.2",
            }
        )
        creator.ensure_reviewed_head_unchanged = Mock()
        creator.handle_release = Mock()

        output = StringIO()
        with redirect_stdout(output):
            result = creator.run()

        self.assertEqual(result, 0)
        self.assertIn("PR Title:\nrelease: merge v2.21.2", output.getvalue())
        self.assertIn("PR Description:\nMerge the validated", output.getvalue())
        self.assertIn(
            "*This PR was created via the automated PR script.*", output.getvalue()
        )
        creator.handle_release.assert_not_called()
        _command.assert_called_once_with(["git", "branch", "--show-current"])

    def test_commit_and_release_modes_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["--commit", "--release"])

    @patch("scripts.pr.run_command")
    def test_dry_run_is_rejected_in_commit_mode(self, command):
        args = SimpleNamespace(
            api_url=None,
            model="",
            bypass_confirm=False,
            commit=True,
            apply=True,
            release=False,
            dry_run=True,
        )
        creator = PRCreator(args)

        self.assertEqual(creator.run(), 1)
        command.assert_not_called()

    @patch("scripts.pr.run_command")
    def test_apply_requires_commit_mode(self, command):
        args = SimpleNamespace(
            api_url=None,
            model="",
            bypass_confirm=False,
            commit=False,
            apply=True,
            release=False,
            dry_run=False,
        )
        creator = PRCreator(args)

        self.assertEqual(creator.run(), 1)
        command.assert_not_called()

    def test_release_pr_content_is_deterministic(self):
        creator = self._creator()
        git_changes = {
            "branch": "release/v2.next",
            "files": "CHANGELOG.md\npyproject.toml",
            "commits": "abc123 release: bump maid-runner to v2.21.2",
            "diff": "+version = 2.21.2",
        }

        title, description = creator.build_release_pr_content(git_changes, "2.21.2")

        self.assertEqual(title, "release: merge v2.21.2")
        self.assertIn("validated v2.21.2 release batch", description)
        self.assertIn("abc123 release: bump maid-runner to v2.21.2", description)
        self.assertIn("annotated tag `v2.21.2`", description)

    @patch("scripts.pr.run_command")
    def test_branch_push_uses_the_immutable_reviewed_sha(self, command):
        command.side_effect = [
            ("pushed", 0),
            ("head123\trefs/heads/release/v2.next", 0),
        ]
        creator = self._creator()

        creator.push_branch("release/v2.next", "head123")

        self.assertEqual(
            command.call_args_list,
            [
                call(
                    [
                        "git",
                        "push",
                        "origin",
                        "head123:refs/heads/release/v2.next",
                    ],
                    check=False,
                ),
                call(
                    [
                        "git",
                        "ls-remote",
                        "origin",
                        "refs/heads/release/v2.next",
                    ],
                    check=False,
                ),
            ],
        )

    @patch("scripts.pr.run_command")
    def test_merge_waits_for_checks_and_pins_the_reviewed_head(self, command):
        command.side_effect = [
            ("all checks passed", 0),
            ("merged", 0),
            ("MERGED\tmerge123", 0),
        ]
        creator = self._creator()

        merge_commit = creator.merge_pr(
            "owner/repo",
            "42",
            "head123",
            "release: merge v2.21.2",
            "Merge the validated release batch.",
        )

        self.assertEqual(merge_commit, "merge123")
        self.assertEqual(
            command.call_args_list,
            [
                call(
                    [
                        "gh",
                        "pr",
                        "checks",
                        "42",
                        "--repo",
                        "owner/repo",
                        "--watch",
                        "--fail-fast",
                    ],
                    check=False,
                ),
                call(
                    [
                        "gh",
                        "pr",
                        "merge",
                        "42",
                        "--repo",
                        "owner/repo",
                        "--merge",
                        "--match-head-commit",
                        "head123",
                        "--subject",
                        "release: merge v2.21.2",
                        "--body",
                        "Merge the validated release batch.",
                    ],
                    check=False,
                ),
                call(
                    [
                        "gh",
                        "pr",
                        "view",
                        "42",
                        "--repo",
                        "owner/repo",
                        "--json",
                        "state,mergeCommit",
                        "--jq",
                        "[.state, .mergeCommit.oid] | @tsv",
                    ],
                    check=False,
                ),
            ],
        )

    @patch("scripts.pr.run_command")
    def test_failed_pr_checks_stop_before_merge(self, command):
        command.return_value = ("MAID Validation failed", 1)
        creator = self._creator()

        with self.assertRaisesRegex(RuntimeError, "checks did not pass"):
            creator.merge_pr(
                "owner/repo",
                "42",
                "head123",
                "release: merge v2.21.2",
                "Merge the validated release batch.",
            )

        self.assertEqual(command.call_count, 1)

    @patch("scripts.pr.run_command")
    def test_merge_state_lookup_failure_stops_before_tagging(self, command):
        command.side_effect = [
            ("all checks passed", 0),
            ("merged", 0),
            ("temporary GitHub error", 1),
        ]
        creator = self._creator()

        with self.assertRaisesRegex(RuntimeError, "verify PR merge state"):
            creator.merge_pr(
                "owner/repo",
                "42",
                "head123",
                "release: merge v2.21.2",
                "Merge the validated release batch.",
            )

        self.assertEqual(command.call_count, 3)

    @patch("scripts.pr.run_command")
    def test_release_tag_targets_verified_remote_main_and_is_pushed(self, command):
        command.side_effect = [
            ("", 0),
            ("", 0),
            ("", 0),
            ("pushed", 0),
        ]
        creator = self._creator()
        creator.inspect_local_tag = Mock(return_value=None)
        creator.inspect_remote_tag = Mock(return_value=None)

        tag = creator.create_release_tag("2.21.2", "merge123")

        self.assertEqual(tag, "v2.21.2")
        self.assertIn(
            call(
                [
                    "git",
                    "tag",
                    "-a",
                    "v2.21.2",
                    "merge123",
                    "-m",
                    "Release v2.21.2",
                ]
            ),
            command.call_args_list,
        )
        self.assertEqual(
            command.call_args_list[-1],
            call(["git", "push", "origin", "v2.21.2"]),
        )

    @patch("scripts.pr.run_command")
    def test_release_tag_refuses_remote_main_mismatch(self, command):
        command.side_effect = [("", 0), ("not-an-ancestor", 1)]
        creator = self._creator()

        with self.assertRaisesRegex(RuntimeError, "not contained in origin/main"):
            creator.create_release_tag("2.21.2", "merge123")

        self.assertEqual(command.call_count, 2)

    @patch("scripts.pr.run_command")
    def test_matching_local_tag_resumes_a_failed_push(self, command):
        command.side_effect = [("", 0), ("", 0), ("pushed", 0)]
        creator = self._creator()
        creator.inspect_local_tag = Mock(
            return_value=("tag-object", "merge123", "Release v2.21.2")
        )
        creator.inspect_remote_tag = Mock(return_value=None)

        tag = creator.create_release_tag("2.21.2", "merge123")

        self.assertEqual(tag, "v2.21.2")
        self.assertNotIn("tag", [entry.args[0][1] for entry in command.call_args_list])
        self.assertEqual(
            command.call_args_list[-1], call(["git", "push", "origin", "v2.21.2"])
        )

    @patch("scripts.pr.run_command")
    def test_conflicting_existing_tag_is_rejected(self, command):
        command.side_effect = [("", 0), ("", 0)]
        creator = self._creator()
        creator.inspect_local_tag = Mock(
            return_value=("tag-object", "different123", "Release v2.21.2")
        )
        creator.inspect_remote_tag = Mock(return_value=None)

        with self.assertRaisesRegex(RuntimeError, "does not match merge123"):
            creator.create_release_tag("2.21.2", "merge123")

        self.assertEqual(command.call_count, 2)

    @patch("scripts.pr.run_command")
    def test_matching_remote_tag_is_treated_as_completed_release(self, command):
        command.side_effect = [("", 0), ("", 0)]
        creator = self._creator()
        creator.inspect_local_tag = Mock(
            return_value=("tag-object", "merge123", "Release v2.21.2")
        )
        creator.inspect_remote_tag = Mock(return_value=("tag-object", "merge123"))

        tag = creator.create_release_tag("2.21.2", "merge123")

        self.assertEqual(tag, "v2.21.2")
        self.assertEqual(command.call_count, 2)

    def test_handle_pr_tags_only_after_successful_release_merge(self):
        creator = self._creator()
        creator.get_repository = Mock(return_value="owner/repo")
        creator.get_head_sha = Mock(return_value="head123")
        creator.push_branch = Mock()
        creator.find_existing_pr = Mock(return_value=None)
        creator.create_pr = Mock(return_value="https://github.com/owner/repo/pull/42")
        creator.ask_confirmation = Mock(return_value=True)
        events = []
        creator.merge_pr = Mock(
            side_effect=lambda *args: events.append("merge") or "merge123"
        )
        creator.create_release_tag = Mock(
            side_effect=lambda *args: events.append("tag") or "v2.21.2"
        )

        creator.handle_pr(
            "release/v2.next",
            "release: merge v2.21.2",
            "Merge the validated release batch.",
            release_version="2.21.2",
        )

        self.assertEqual(events, ["merge", "tag"])
        creator.create_release_tag.assert_called_once_with("2.21.2", "merge123")

    def test_merged_pr_without_tag_is_resumed_when_branch_has_no_diff(self):
        creator = self._creator()
        creator.get_git_changes = Mock(
            return_value={
                "branch": "release/v2.next",
                "files": "",
                "commits": "",
                "diff": "",
            }
        )
        creator.get_release_version = Mock(return_value="2.21.2")
        creator.ensure_reviewed_head_unchanged = Mock()
        creator.get_repository = Mock(return_value="owner/repo")
        creator.push_branch = Mock()
        creator.find_release_pr = Mock(
            return_value={
                "url": "https://github.com/owner/repo/pull/42",
                "state": "MERGED",
                "head_sha": "head123",
                "merge_commit": "merge123",
            }
        )
        creator.create_release_tag = Mock(return_value="v2.21.2")

        result = creator.handle_release("release/v2.next", "head123")

        self.assertEqual(result, "https://github.com/owner/repo/pull/42")
        creator.create_release_tag.assert_called_once_with("2.21.2", "merge123")

    def test_existing_version_tag_blocks_a_new_unmerged_release(self):
        creator = self._creator()
        creator.get_git_changes = Mock(
            return_value={
                "branch": "release/v2.next",
                "files": "pyproject.toml",
                "commits": "abc123 release: reuse v2.21.2",
                "diff": "+change",
            }
        )
        creator.get_release_version = Mock(return_value="2.21.2")
        creator.ensure_reviewed_head_unchanged = Mock()
        creator.get_repository = Mock(return_value="owner/repo")
        creator.push_branch = Mock()
        creator.find_release_pr = Mock(return_value=None)
        creator.inspect_local_tag = Mock(return_value=None)
        creator.inspect_remote_tag = Mock(return_value=("tag-object", "old-merge"))
        creator.create_pr = Mock()

        with self.assertRaisesRegex(RuntimeError, "no matching merged PR"):
            creator.handle_release("release/v2.next", "head123")

        creator.create_pr.assert_not_called()

    @patch("scripts.pr.run_command")
    def test_release_metadata_is_read_from_the_pinned_head(self, command):
        command.side_effect = [
            ('[project]\nversion = "2.21.2"', 0),
            ("# Changelog\n\n## [2.21.2] - 2026-07-15\n", 0),
        ]
        creator = self._creator()

        version = creator.get_release_version("head123")

        self.assertEqual(version, "2.21.2")
        self.assertEqual(
            command.call_args_list,
            [
                call(["git", "show", "head123:pyproject.toml"], check=False),
                call(["git", "show", "head123:CHANGELOG.md"], check=False),
            ],
        )

    @patch("scripts.pr.run_command")
    def test_release_metadata_rejects_non_exact_changelog_heading(self, command):
        command.side_effect = [
            ('[project]\nversion = "2.21.2"', 0),
            ("# Example: ## [2.21.2] - someday\n", 0),
        ]
        creator = self._creator()

        with self.assertRaisesRegex(RuntimeError, "exact release heading"):
            creator.get_release_version("head123")

    def test_release_stops_if_head_changes_after_metadata_read(self):
        creator = self._creator()
        creator.get_head_sha = Mock(return_value="different123")

        with self.assertRaisesRegex(RuntimeError, "HEAD changed"):
            creator.ensure_reviewed_head_unchanged("head123")


if __name__ == "__main__":
    unittest.main()
