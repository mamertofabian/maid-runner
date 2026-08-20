from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts.pr import PRCreator


def _release_creator() -> PRCreator:
    return PRCreator(
        SimpleNamespace(
            api_url=None,
            model="",
            bypass_confirm=True,
            commit=False,
            apply=False,
            release=True,
            dry_run=False,
        )
    )


@patch("scripts.pr.run_command")
def test_open_release_pr_without_merge_commit_is_reused(command) -> None:
    command.return_value = (
        "https://github.com/owner/repo/pull/42\tOPEN\thead123",
        0,
    )

    release_pr = PRCreator.find_release_pr(
        _release_creator(),
        "owner/repo",
        "release/v2.next",
        "main",
        "head123",
    )

    assert release_pr == {
        "url": "https://github.com/owner/repo/pull/42",
        "state": "OPEN",
        "head_sha": "head123",
        "merge_commit": "",
    }


@patch("scripts.pr.run_command")
def test_merged_release_pr_is_preferred_and_preserves_merge_commit(command) -> None:
    command.return_value = (
        "https://github.com/owner/repo/pull/42\tOPEN\thead123\t\n"
        "https://github.com/owner/repo/pull/41\tMERGED\thead123\tmerge123",
        0,
    )

    release_pr = PRCreator.find_release_pr(
        _release_creator(),
        "owner/repo",
        "release/v2.next",
        "main",
        "head123",
    )

    assert release_pr == {
        "url": "https://github.com/owner/repo/pull/41",
        "state": "MERGED",
        "head_sha": "head123",
        "merge_commit": "merge123",
    }


@patch("scripts.pr.run_command")
def test_malformed_release_pr_record_fails_with_specific_error(command) -> None:
    command.return_value = ("https://github.com/owner/repo/pull/42\tOPEN", 0)

    with pytest.raises(RuntimeError, match="Malformed release PR record"):
        PRCreator.find_release_pr(
            _release_creator(),
            "owner/repo",
            "release/v2.next",
            "main",
            "head123",
        )


@patch("scripts.pr.run_command")
def test_merged_release_pr_without_merge_commit_fails_with_specific_error(
    command,
) -> None:
    command.return_value = (
        "https://github.com/owner/repo/pull/42\tMERGED\thead123",
        0,
    )

    with pytest.raises(RuntimeError, match="Malformed release PR record"):
        PRCreator.find_release_pr(
            _release_creator(),
            "owner/repo",
            "release/v2.next",
            "main",
            "head123",
        )
