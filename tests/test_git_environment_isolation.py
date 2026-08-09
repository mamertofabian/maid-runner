"""Behavioral coverage for Git-hook environment isolation."""

import os


def test_git_repository_pointers_are_removed_from_test_environment():
    repository_pointer_names = (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_COMMON_DIR",
        "GIT_PREFIX",
        "GIT_OBJECT_DIRECTORY",
    )

    leaked_pointers = {
        name: os.environ[name]
        for name in repository_pointer_names
        if name in os.environ
    }

    assert leaked_pointers == {}
