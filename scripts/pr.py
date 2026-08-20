#!/usr/bin/env python3
"""Developer-facing pull-request and release automation for this repository.

This script is a maintainer convenience tool, not part of maid-runner's runtime,
CLI, or MAID validation behavior. It gathers the current branch's committed
changes relative to ``origin/main``, generates pull-request content, pushes the
reviewed branch, and can create and merge the pull request. Release mode adds
the safeguards needed to promote ``release/v2.next`` and publish an annotated
version tag. Dry-run mode prints the exact generated title and body without
pushing, creating a pull request, merging, or tagging.

Normal PR content and commit-message generation require a running local LLM
server with an OpenAI-compatible chat-completions endpoint. By default the
script connects to ``http://localhost:1234/v1/chat/completions``; override this
with ``LLAMA_SERVER_API_URL`` or ``--api-url``. Release PR content is generated
deterministically and does not require the local LLM.

Usage:
    scripts/pr                       # Create a PR from the current branch
    scripts/pr --dry-run             # Print PR content without creating it
    scripts/pr --release             # PR, merge, tag, and publish a release
    scripts/pr --release --dry-run   # Print release PR content only
    scripts/pr --bypass-confirm      # Skip confirmation prompts
    scripts/pr --commit              # Generate a commit message
    scripts/pr --commit --apply      # Generate and apply a commit message
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib


RELEASE_BRANCH = "release/v2.next"
SEMANTIC_VERSION = re.compile(r"\d+\.\d+\.\d+")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Colors:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    BLUE = "\033[0;34m"
    YELLOW = "\033[1;33m"
    NC = "\033[0m"


def print_status(msg: str):
    print(f"{Colors.BLUE}[INFO]{Colors.NC} {msg}")


def print_success(msg: str):
    print(f"{Colors.GREEN}[SUCCESS]{Colors.NC} {msg}")


def print_warning(msg: str):
    print(f"{Colors.YELLOW}[WARNING]{Colors.NC} {msg}")


def print_error(msg: str):
    print(f"{Colors.RED}[ERROR]{Colors.NC} {msg}", file=sys.stderr)


def run_command(cmd: list, check: bool = True) -> Tuple[str, int]:
    """Run a command and return output and exit code."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=check)
        if result.returncode != 0:
            return result.stderr.strip() or result.stdout.strip(), result.returncode
        return result.stdout.strip(), result.returncode
    except subprocess.CalledProcessError as e:
        return e.stderr.strip() or e.stdout.strip(), e.returncode


def enter_project_root() -> None:
    """Anchor all Git and metadata operations to this script's repository."""

    if (
        not (PROJECT_ROOT / ".git").exists()
        or not (PROJECT_ROOT / "pyproject.toml").is_file()
    ):
        raise RuntimeError(f"Could not validate project root {PROJECT_ROOT}")
    os.chdir(PROJECT_ROOT)


class LlamaServerClient:
    """Client for the llama.cpp OpenAI-compatible API."""

    PR_GENERATION_ATTEMPTS = 2
    PR_MAX_TOKENS = 4000

    def __init__(self, api_url: str, model: str):
        self.api_url = api_url
        self.model = model

    def generate_pr_content(self, git_changes: Dict[str, str]) -> Tuple[str, str]:
        """Generate PR title and description."""

        context = f"""You are a code reviewer and PR writer. Based on the following git changes, generate a concise PR title and a detailed description.

Branch: {git_changes['branch']}

Changed files:
{git_changes['files']}

Commit messages:
{git_changes['commits']}

Code changes (first 2000 characters):
{git_changes['diff'][:2000]}

CRITICAL INSTRUCTIONS:
1. TITLE: Concise (max 100 chars)
   - Focus on WHAT changed
   - Keep it SHORT

2. DESCRIPTION: Detailed explanation
   - WHY the change was needed
   - HOW it was implemented
   - Include context and details

You MUST return BOTH fields in valid JSON format:
{{
    "title": "short concise title here",
    "description": "detailed description here"
}}"""

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a code reviewer. Return ONLY valid JSON with 'title' and 'description' fields.",
                },
                {"role": "user", "content": context},
            ],
            "temperature": 0.3,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "pr_content",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                        },
                        "required": ["title", "description"],
                        "additionalProperties": False,
                    },
                },
            },
        }

        model_info = self.model if self.model else "currently loaded model"
        print_status(f"Generating PR content with {model_info}...")
        last_error = None
        last_finish_reason = "unknown"
        for attempt in range(self.PR_GENERATION_ATTEMPTS):
            request_payload = {
                **payload,
                "max_tokens": self.PR_MAX_TOKENS + (attempt * 2000),
            }
            response = requests.post(self.api_url, json=request_payload, timeout=60)
            response.raise_for_status()

            try:
                result = response.json()
                choice = result["choices"][0]
                last_finish_reason = choice.get("finish_reason", "unknown")
                content = choice["message"]["content"].strip()
                data = json.loads(content)
                title = data["title"].strip()
                description = data["description"].strip()
                if not title or not description:
                    raise ValueError("title and description must not be empty")
                break
            except (
                json.JSONDecodeError,
                KeyError,
                TypeError,
                AttributeError,
                ValueError,
            ) as error:
                last_error = error
                if attempt + 1 < self.PR_GENERATION_ATTEMPTS:
                    print_warning(
                        "Llama Server returned invalid or truncated JSON; retrying "
                        "with a larger token budget"
                    )
        else:
            raise ValueError(
                "Llama Server returned invalid or truncated JSON after "
                f"{self.PR_GENERATION_ATTEMPTS} attempts "
                f"(last finish_reason={last_finish_reason}): {last_error}"
            ) from last_error

        if len(title) > 100:
            print_warning(f"Title too long ({len(title)} > 100), truncating")
            title = title[:97] + "..."

        if len(title) > 256:  # GitHub limit
            print_warning("Title exceeds GitHub limit, truncating to 256 chars")
            title = title[:253] + "..."

        return title, description

    def generate_commit_message(self, staged_diff: str, files: str) -> str:
        """Generate commit message for staged changes."""

        context = f"""Generate a concise git commit message for these changes.

Changed files:
{files}

Diff (first 2000 characters):
{staged_diff[:2000]}

Follow conventional commit format: <type>: <description>
Types: feat, fix, docs, style, refactor, test, chore

Return ONLY the commit message (max 72 characters), nothing else."""

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a git commit message generator. Return only the message.",
                },
                {"role": "user", "content": context},
            ],
            "temperature": 0.3,
            "max_tokens": 100,
            "chat_template_kwargs": {"enable_thinking": False},
        }

        model_info = self.model if self.model else "currently loaded model"
        print_status(f"Generating commit message with {model_info}...")
        response = requests.post(self.api_url, json=payload, timeout=30)
        response.raise_for_status()

        result = response.json()
        message = result["choices"][0]["message"]["content"].strip()

        if len(message) > 72:
            message = message[:72]

        return message


class PRCreator:
    """Main PR creation orchestrator."""

    def __init__(self, args):
        self.args = args
        self.api_url = args.api_url or os.getenv(
            "LLAMA_SERVER_API_URL", "http://localhost:1234/v1/chat/completions"
        )
        self.llama_server = LlamaServerClient(self.api_url, args.model)

    def get_git_changes(self, head_ref: str = "HEAD") -> Dict[str, str]:
        """Get git changes for current branch vs main."""

        output, exit_code = run_command(
            ["git", "fetch", "origin", "main", "--quiet"], check=False
        )
        if exit_code != 0:
            raise RuntimeError(f"Failed to fetch origin/main: {output}")

        branch, exit_code = run_command(["git", "branch", "--show-current"])
        if exit_code != 0 or not branch:
            raise RuntimeError(f"Could not determine current branch: {branch}")
        base_ref = "origin/main"

        diff, exit_code = run_command(
            ["git", "diff", f"{base_ref}..{head_ref}"], check=False
        )
        if exit_code != 0:
            raise RuntimeError(f"Could not inspect branch diff: {diff}")

        commits, exit_code = run_command(
            ["git", "log", "--oneline", f"{base_ref}..{head_ref}"], check=False
        )
        if exit_code != 0:
            raise RuntimeError(f"Could not inspect branch commits: {commits}")

        files, exit_code = run_command(
            ["git", "diff", "--name-only", f"{base_ref}..{head_ref}"], check=False
        )
        if exit_code != 0:
            raise RuntimeError(f"Could not inspect changed files: {files}")

        return {"branch": branch, "diff": diff, "commits": commits, "files": files}

    def get_repository(self) -> str:
        """Return the GitHub owner/repository slug for the current checkout."""

        output, exit_code = run_command(
            [
                "gh",
                "repo",
                "view",
                "--json",
                "nameWithOwner",
                "--jq",
                ".nameWithOwner",
            ],
            check=False,
        )
        if exit_code != 0 or not output:
            raise RuntimeError(f"Could not determine GitHub repository: {output}")
        return output

    def get_head_sha(self) -> str:
        """Return the full commit SHA currently checked out."""

        output, exit_code = run_command(["git", "rev-parse", "HEAD"], check=False)
        if exit_code != 0 or not output:
            raise RuntimeError(f"Could not resolve HEAD: {output}")
        return output

    def push_branch(self, branch_name: str, head_sha: str) -> None:
        """Push a branch and verify that the remote ref matches its reviewed head."""

        output, exit_code = run_command(
            [
                "git",
                "push",
                "origin",
                f"{head_sha}:refs/heads/{branch_name}",
            ],
            check=False,
        )
        if exit_code != 0:
            raise RuntimeError(f"Failed to push {branch_name}: {output}")

        remote_ref, exit_code = run_command(
            ["git", "ls-remote", "origin", f"refs/heads/{branch_name}"],
            check=False,
        )
        remote_sha = remote_ref.partition("\t")[0]
        if exit_code != 0 or remote_sha != head_sha:
            raise RuntimeError(
                f"origin/{branch_name} does not match the reviewed HEAD {head_sha}"
            )

    def find_existing_pr(self, repo: str, head: str, base: str) -> Optional[str]:
        """Return an existing open PR URL for the same head/base pair."""

        output, exit_code = run_command(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                repo,
                "--head",
                head,
                "--base",
                base,
                "--state",
                "open",
                "--json",
                "url",
                "--jq",
                ".[0].url // empty",
            ],
            check=False,
        )
        if exit_code != 0:
            raise RuntimeError(f"Could not query existing pull requests: {output}")
        return output or None

    def find_release_pr(
        self, repo: str, head: str, base: str, head_sha: str
    ) -> Optional[Dict[str, str]]:
        """Find an open or merged release PR for the exact reviewed head."""

        query = (
            f'.[] | select(.headRefOid == "{head_sha}") | '
            'select(.state == "OPEN" or .state == "MERGED") | '
            '[.url, .state, .headRefOid, (.mergeCommit.oid // "")] | @tsv'
        )
        output, exit_code = run_command(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                repo,
                "--head",
                head,
                "--base",
                base,
                "--state",
                "all",
                "--limit",
                "100",
                "--json",
                "url,state,headRefOid,mergeCommit",
                "--jq",
                query,
            ],
            check=False,
        )
        if exit_code != 0:
            raise RuntimeError(f"Could not query release pull requests: {output}")
        if not output:
            return None

        candidates = []
        for line in output.splitlines():
            fields = line.split("\t")
            if len(fields) == 3 and fields[1] == "OPEN":
                url, state, pr_head_sha = fields
                merge_commit = ""
            elif len(fields) == 4:
                url, state, pr_head_sha, merge_commit = fields
            else:
                raise RuntimeError(
                    "Malformed release PR record from GitHub: "
                    f"expected 3 or 4 fields, got {len(fields)}"
                )
            candidates.append(
                {
                    "url": url,
                    "state": state,
                    "head_sha": pr_head_sha,
                    "merge_commit": merge_commit,
                }
            )
        return next(
            (candidate for candidate in candidates if candidate["state"] == "MERGED"),
            candidates[0],
        )

    def get_release_version(self, head_sha: str) -> str:
        """Read exact release metadata from the pinned release commit."""

        pyproject_text, exit_code = run_command(
            ["git", "show", f"{head_sha}:pyproject.toml"], check=False
        )
        if exit_code != 0:
            raise RuntimeError(
                f"Could not read pyproject.toml from {head_sha}: {pyproject_text}"
            )
        try:
            version = tomllib.loads(pyproject_text)["project"]["version"]
        except (KeyError, TypeError, tomllib.TOMLDecodeError) as error:
            raise RuntimeError(f"Could not read project version: {error}") from error

        if not isinstance(version, str) or not SEMANTIC_VERSION.fullmatch(version):
            raise RuntimeError(
                f"Project version must be an exact semantic version, got {version!r}"
            )

        changelog, exit_code = run_command(
            ["git", "show", f"{head_sha}:CHANGELOG.md"], check=False
        )
        if exit_code != 0:
            raise RuntimeError(
                f"Could not read CHANGELOG.md from {head_sha}: {changelog}"
            )
        heading = re.compile(
            rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$", re.MULTILINE
        )
        if not heading.search(changelog):
            raise RuntimeError(
                f"CHANGELOG.md has no exact release heading for {version}"
            )
        return version

    def ensure_release_ready(self, branch_name: str) -> None:
        """Fail closed unless release automation starts from a clean release branch."""

        if branch_name != RELEASE_BRANCH:
            raise RuntimeError(
                f"Release mode must run from {RELEASE_BRANCH}, not {branch_name}"
            )

        status, exit_code = run_command(["git", "status", "--porcelain"], check=False)
        if exit_code != 0:
            raise RuntimeError(f"Could not inspect worktree status: {status}")
        if status:
            raise RuntimeError(
                "Release mode requires a clean worktree; commit or stash changes first"
            )

    def ensure_reviewed_head_unchanged(self, head_sha: str) -> None:
        """Ensure metadata, push, and merge all use the same clean commit."""

        current_head = self.get_head_sha()
        if current_head != head_sha:
            raise RuntimeError(
                f"HEAD changed from reviewed commit {head_sha} to {current_head}"
            )
        status, exit_code = run_command(["git", "status", "--porcelain"], check=False)
        if exit_code != 0 or status:
            raise RuntimeError("Worktree changed after release metadata was inspected")

    def build_release_pr_content(
        self, git_changes: Dict[str, str], version: str
    ) -> Tuple[str, str]:
        """Build deterministic release PR content without requiring an AI service."""

        title = f"release: merge v{version}"
        commits = git_changes["commits"] or "(no commit summary available)"
        files = git_changes["files"] or "(no changed files reported)"
        description = f"""Merge the validated v{version} release batch from `{RELEASE_BRANCH}` into `main`.

## Included commits

```text
{commits}
```

## Changed files

```text
{files}
```

## Release safeguards

- Wait for pull-request checks before merging.
- Pin the merge to the reviewed release-branch HEAD.
- Create and push annotated tag `v{version}` only after `origin/main` matches the merge commit.
"""
        return title, description

    @staticmethod
    def build_pr_body(description: str) -> str:
        """Return the exact body sent to GitHub for a generated PR."""

        return f"""{description}

---
*This PR was created via the automated PR script.*
"""

    @classmethod
    def print_pr_preview(cls, title: str, description: str) -> None:
        """Print complete PR content without performing remote write operations."""

        print()
        print("PR Title:")
        print(title)
        print()
        print("PR Description:")
        print(cls.build_pr_body(description))

    def create_pr(
        self, repo: str, head: str, base: str, title: str, description: str
    ) -> str:
        """Create a PR using gh CLI."""

        full_description = self.build_pr_body(description)

        cmd = [
            "gh",
            "pr",
            "create",
            "--repo",
            repo,
            "--head",
            head,
            "--base",
            base,
            "--title",
            title,
            "--body",
            full_description,
        ]

        output, exit_code = run_command(cmd, check=False)

        if exit_code != 0:
            if "No commits between" in output:
                raise Exception(
                    f"No changes to create PR: {base} and {head} are already in sync"
                )
            elif "already exists" in output:
                raise Exception(f"PR already exists between {head} and {base}")
            elif "permission" in output.lower() or "forbidden" in output.lower():
                raise Exception(
                    f"Permission denied: Check your GitHub access to {repo}"
                )
            else:
                raise Exception(f"Failed to create PR: {output}")

        return output.strip()

    def merge_pr(
        self,
        repo: str,
        pr_number: str,
        head_sha: str,
        subject: str,
        body: str,
    ) -> str:
        """Wait for checks, merge the reviewed head, and return its merge commit."""

        checks_output, exit_code = run_command(
            [
                "gh",
                "pr",
                "checks",
                pr_number,
                "--repo",
                repo,
                "--watch",
                "--fail-fast",
            ],
            check=False,
        )
        if exit_code != 0:
            raise RuntimeError(f"Pull-request checks did not pass: {checks_output}")

        merge_output, exit_code = run_command(
            [
                "gh",
                "pr",
                "merge",
                pr_number,
                "--repo",
                repo,
                "--merge",
                "--match-head-commit",
                head_sha,
                "--subject",
                subject,
                "--body",
                body,
            ],
            check=False,
        )
        if exit_code != 0:
            raise RuntimeError(f"Failed to merge PR #{pr_number}: {merge_output}")

        view_output, exit_code = run_command(
            [
                "gh",
                "pr",
                "view",
                pr_number,
                "--repo",
                repo,
                "--json",
                "state,mergeCommit",
                "--jq",
                "[.state, .mergeCommit.oid] | @tsv",
            ],
            check=False,
        )
        if exit_code != 0:
            raise RuntimeError(f"Could not verify PR merge state: {view_output}")

        state, separator, merge_commit = view_output.partition("\t")
        if state != "MERGED" or not separator or not merge_commit:
            raise RuntimeError(
                f"PR #{pr_number} is not confirmed merged; refusing to tag"
            )
        return merge_commit

    def inspect_local_tag(self, tag: str) -> Optional[Tuple[str, str, str]]:
        """Return annotated tag object, target commit, and subject when present."""

        _, exit_code = run_command(
            ["git", "show-ref", "--verify", "--quiet", f"refs/tags/{tag}"],
            check=False,
        )
        if exit_code == 1:
            return None
        if exit_code != 0:
            raise RuntimeError(f"Could not inspect local tag {tag}")

        object_type, exit_code = run_command(
            ["git", "cat-file", "-t", tag], check=False
        )
        if exit_code != 0 or object_type != "tag":
            raise RuntimeError(f"Local tag {tag} is not an annotated tag")
        tag_object, exit_code = run_command(["git", "rev-parse", tag], check=False)
        if exit_code != 0:
            raise RuntimeError(f"Could not resolve local tag object {tag}")
        target, exit_code = run_command(
            ["git", "rev-parse", f"{tag}^{{}}"], check=False
        )
        if exit_code != 0:
            raise RuntimeError(f"Could not resolve local tag target {tag}")
        subject, exit_code = run_command(
            [
                "git",
                "for-each-ref",
                f"refs/tags/{tag}",
                "--format=%(contents:subject)",
            ],
            check=False,
        )
        if exit_code != 0:
            raise RuntimeError(f"Could not read local tag message {tag}")
        return tag_object, target, subject

    def inspect_remote_tag(self, tag: str) -> Optional[Tuple[str, str]]:
        """Return remote annotated tag object and peeled target when present."""

        output, exit_code = run_command(
            [
                "git",
                "ls-remote",
                "--tags",
                "origin",
                f"refs/tags/{tag}",
                f"refs/tags/{tag}^{{}}",
            ],
            check=False,
        )
        if exit_code != 0:
            raise RuntimeError(f"Could not inspect remote tag {tag}: {output}")
        if not output:
            return None

        refs = {}
        for line in output.splitlines():
            object_id, separator, ref = line.partition("\t")
            if separator:
                refs[ref] = object_id
        tag_object = refs.get(f"refs/tags/{tag}")
        target = refs.get(f"refs/tags/{tag}^{{}}")
        if not tag_object or not target:
            raise RuntimeError(f"Remote tag {tag} is not an annotated tag")
        return tag_object, target

    @staticmethod
    def validate_release_tag(
        tag: str,
        tag_info: Tuple[str, str, str],
        merge_commit: str,
    ) -> None:
        """Validate that an annotated release tag has the expected target/message."""

        _, target, subject = tag_info
        if target != merge_commit:
            raise RuntimeError(
                f"Existing tag {tag} target {target} does not match {merge_commit}"
            )
        expected_subject = f"Release {tag}"
        if subject != expected_subject:
            raise RuntimeError(
                f"Existing tag {tag} message {subject!r} does not match "
                f"{expected_subject!r}"
            )

    def create_release_tag(self, version: str, merge_commit: str) -> str:
        """Create and push an annotated tag after verifying remote main."""

        tag = f"v{version}"
        output, exit_code = run_command(
            ["git", "fetch", "origin", "main", "--quiet"], check=False
        )
        if exit_code != 0:
            raise RuntimeError(f"Failed to refresh origin/main: {output}")

        _, exit_code = run_command(
            ["git", "merge-base", "--is-ancestor", merge_commit, "origin/main"],
            check=False,
        )
        if exit_code != 0:
            raise RuntimeError(
                f"Confirmed merge {merge_commit} is not contained in origin/main; "
                "refusing to tag"
            )

        local_tag = self.inspect_local_tag(tag)
        remote_tag = self.inspect_remote_tag(tag)

        if remote_tag:
            remote_object, remote_target = remote_tag
            if remote_target != merge_commit:
                raise RuntimeError(
                    f"Remote tag {tag} target {remote_target} does not match "
                    f"{merge_commit}"
                )
            if local_tag is None:
                output, exit_code = run_command(
                    [
                        "git",
                        "fetch",
                        "origin",
                        f"refs/tags/{tag}:refs/tags/{tag}",
                        "--quiet",
                    ],
                    check=False,
                )
                if exit_code != 0:
                    raise RuntimeError(f"Could not fetch remote tag {tag}: {output}")
                local_tag = self.inspect_local_tag(tag)
            if local_tag is None or local_tag[0] != remote_object:
                raise RuntimeError(f"Remote tag object for {tag} does not match local")
            self.validate_release_tag(tag, local_tag, merge_commit)
            print_success(f"Release tag {tag} is already published")
            return tag

        if local_tag:
            self.validate_release_tag(tag, local_tag, merge_commit)
        else:
            output, exit_code = run_command(
                ["git", "tag", "-a", tag, merge_commit, "-m", f"Release {tag}"]
            )
            if exit_code != 0:
                raise RuntimeError(f"Failed to create annotated tag {tag}: {output}")

        output, exit_code = run_command(["git", "push", "origin", tag])
        if exit_code != 0:
            raise RuntimeError(
                f"Created local tag {tag}, but failed to push it: {output}"
            )
        print_success(f"Created and pushed release tag {tag}")
        return tag

    def ask_confirmation(self, message: str, pr_url: Optional[str] = None) -> bool:
        """Ask user for confirmation."""
        if self.args.bypass_confirm:
            print_status("Auto-proceeding (--bypass-confirm enabled)")
            return True

        print()
        print_warning(message)
        if pr_url:
            print(f"PR: {pr_url}")
        print()

        response = input("Continue? (y/N): ").strip().lower()
        return response == "y"

    def handle_commit_message(self):
        """Generate and optionally apply commit message."""

        staged_diff, _ = run_command(["git", "diff", "--cached"])
        if not staged_diff:
            print_error("No staged changes to commit")
            return 1

        files, _ = run_command(["git", "diff", "--cached", "--name-only"])

        try:
            message = self.llama_server.generate_commit_message(staged_diff, files)
            print_success(f"Generated: {message}")

            if self.args.apply:
                output, exit_code = run_command(
                    ["git", "commit", "-m", message], check=False
                )
                if exit_code != 0:
                    raise RuntimeError(f"Failed to commit staged changes: {output}")
                print_success("Changes committed")

            return 0
        except Exception as e:
            print_error(f"Failed to generate commit message: {e}")
            return 1

    def handle_release(self, branch_name: str, head_sha: str) -> str:
        """Create, merge, or resume the release for an exact branch commit."""

        version = self.get_release_version(head_sha)
        git_changes = self.get_git_changes(head_sha)
        self.ensure_reviewed_head_unchanged(head_sha)

        repo = self.get_repository()
        self.push_branch(branch_name, head_sha)
        release_pr = self.find_release_pr(repo, branch_name, "main", head_sha)

        if release_pr and release_pr["state"] == "MERGED":
            merge_commit = release_pr["merge_commit"]
            if not merge_commit:
                raise RuntimeError("Merged release PR has no merge commit")
            print_status(f"Resuming merged release PR: {release_pr['url']}")
            self.create_release_tag(version, merge_commit)
            return release_pr["url"]

        tag = f"v{version}"
        if self.inspect_local_tag(tag) or self.inspect_remote_tag(tag):
            raise RuntimeError(
                f"Release tag {tag} already exists, but reviewed head {head_sha} "
                "has no matching merged PR to resume"
            )

        if not git_changes["commits"] and not git_changes["diff"]:
            raise RuntimeError(
                "Release branch has no changes and no matching merged PR to resume"
            )

        title, description = self.build_release_pr_content(git_changes, version)
        print_success(f"Title: {title}")
        print_success(f"Description: {len(description)} chars")

        if release_pr and release_pr["state"] == "OPEN":
            pr_url = release_pr["url"]
            print_status(f"Reusing existing release PR: {pr_url}")
        else:
            pr_url = self.create_pr(repo, branch_name, "main", title, description)
            print_success(f"Created release PR: {pr_url}")

        pr_number = pr_url.split("/")[-1]
        if not self.ask_confirmation(
            f"Do you want to merge PR #{pr_number} and publish v{version} now?",
            pr_url,
        ):
            return pr_url

        merge_body = (
            f"Merge the validated v{version} release batch from {RELEASE_BRANCH} "
            "into the stable main branch."
        )
        merge_commit = self.merge_pr(
            repo,
            pr_number,
            head_sha,
            title,
            merge_body,
        )
        print_success(f"Merged PR #{pr_number} at {merge_commit}")
        self.create_release_tag(version, merge_commit)
        return pr_url

    def handle_pr(
        self,
        branch_name: str,
        title: str,
        description: str,
        release_version: Optional[str] = None,
    ) -> Optional[str]:
        """Create a PR and optionally finish a release after its merge."""

        print_status(f"Creating PR: {branch_name} -> main")
        print_status(f"Title: {title}")

        repo = self.get_repository()
        head_sha = self.get_head_sha()
        self.push_branch(branch_name, head_sha)

        pr_url = self.find_existing_pr(repo, branch_name, "main")
        if pr_url:
            print_status(f"Reusing existing PR: {pr_url}")
        else:
            pr_url = self.create_pr(repo, branch_name, "main", title, description)
            print_success(f"Created PR: {pr_url}")

        pr_number = pr_url.split("/")[-1]
        action = f"merge PR #{pr_number}"
        if release_version:
            action += f" and publish v{release_version}"
        if not self.ask_confirmation(f"Do you want to {action} now?", pr_url):
            return pr_url

        print_status(f"Waiting for checks and merging PR #{pr_number}...")
        merge_body = description
        if release_version:
            merge_body = (
                f"Merge the validated v{release_version} release batch from "
                f"{RELEASE_BRANCH} into the stable main branch."
            )
        merge_commit = self.merge_pr(
            repo,
            pr_number,
            head_sha,
            title,
            merge_body,
        )
        print_success(f"Merged PR #{pr_number} at {merge_commit}")

        if release_version:
            self.create_release_tag(release_version, merge_commit)

        return pr_url

    def run(self):
        """Main execution."""

        if self.args.commit and self.args.release:
            print_error("--commit and --release cannot be used together")
            return 1
        if self.args.commit and self.args.dry_run:
            print_error(
                "--dry-run previews PR content and cannot be used with --commit"
            )
            return 1
        if self.args.apply and not self.args.commit:
            print_error("--apply requires --commit")
            return 1

        if self.args.commit:
            return self.handle_commit_message()

        branch_name, exit_code = run_command(["git", "branch", "--show-current"])
        if exit_code != 0 or not branch_name:
            print_error("Could not determine the current branch")
            return 1

        if branch_name == "main":
            print_error(
                "Cannot create PR from main branch. Switch to a feature branch."
            )
            return 1

        print_status(f"{'='*60}")
        print_status(f"PR: {branch_name} -> main")
        print_status(f"{'='*60}")

        try:
            if self.args.release:
                self.ensure_release_ready(branch_name)
                head_sha = self.get_head_sha()
                if self.args.dry_run:
                    version = self.get_release_version(head_sha)
                    git_changes = self.get_git_changes(head_sha)
                    self.ensure_reviewed_head_unchanged(head_sha)
                    if not git_changes["commits"] and not git_changes["diff"]:
                        raise RuntimeError(
                            "Release branch has no changes to describe in a PR"
                        )
                    title, description = self.build_release_pr_content(
                        git_changes, version
                    )
                    self.print_pr_preview(title, description)
                    print_success("\nDry run complete; no PR was created.")
                    return 0
                self.handle_release(branch_name, head_sha)
                print_success("\nDone!")
                return 0

            git_changes = self.get_git_changes()

            if not git_changes["commits"] and not git_changes["diff"]:
                print_warning("No changes detected - branch is in sync with main")
                return 0

            title, description = self.llama_server.generate_pr_content(git_changes)
            print_success(f"Title: {title}")
            print_success(f"Description: {len(description)} chars")

            if self.args.dry_run:
                self.print_pr_preview(title, description)
                print_success("\nDry run complete; no PR was created.")
                return 0

            self.handle_pr(branch_name, title, description)

        except Exception as e:
            print_error(f"Failed: {e}")
            return 1

        print_success("\nDone!")
        return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for PR and release automation."""

    parser = argparse.ArgumentParser(
        description="Create pull requests and safely publish validated releases"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--commit",
        action="store_true",
        help="Generate commit message for staged changes",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the generated commit message (use with --commit)",
    )
    parser.add_argument(
        "--bypass-confirm",
        action="store_true",
        help="Auto-merge and, in release mode, publish without confirmation",
    )
    mode.add_argument(
        "--release",
        action="store_true",
        help=(
            "Create a release PR from release/v2.next, wait for checks, merge, "
            "and push the annotated project-version tag"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generated PR title and description without creating a PR",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Llama Server model (default: use currently loaded model)",
    )
    parser.add_argument(
        "--api-url",
        help="Llama Server API URL (default: http://localhost:1234/v1/chat/completions)",
    )

    return parser


def main():
    try:
        enter_project_root()
    except RuntimeError as error:
        print_error(str(error))
        sys.exit(1)

    args = build_parser().parse_args()

    creator = PRCreator(args)
    sys.exit(creator.run())


if __name__ == "__main__":
    main()
