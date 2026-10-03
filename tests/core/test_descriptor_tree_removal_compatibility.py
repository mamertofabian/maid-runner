"""Descriptor-anchored tree removal works on every supported Python version."""

import os
import pytest


@pytest.mark.skipif(os.name != "posix", reason="descriptor-relative POSIX boundary")
def test_remove_tree_at_removes_nested_payload_without_following_links(tmp_path):
    from maid_runner.core.uninstall import remove_tree_at

    parent = tmp_path / "owned"
    tree = parent / "payload"
    (tree / "nested").mkdir(parents=True)
    (tree / "nested/data").write_text("owned")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep").write_text("keep")
    (tree / "outside-dir").symlink_to(outside, target_is_directory=True)
    (tree / "outside-file").symlink_to(outside / "keep")
    descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        remove_tree_at("payload", descriptor)
    finally:
        os.close(descriptor)

    assert not tree.exists()
    assert (outside / "keep").read_text() == "keep"


@pytest.mark.skipif(os.name != "posix", reason="descriptor-relative POSIX boundary")
def test_remove_tree_at_stays_on_pinned_parent_after_path_replacement(tmp_path):
    from maid_runner.core.uninstall import remove_tree_at

    parent = tmp_path / "owned"
    (parent / "payload").mkdir(parents=True)
    (parent / "payload/data").write_text("owned")
    outside = tmp_path / "outside"
    (outside / "payload").mkdir(parents=True)
    (outside / "payload/keep").write_text("keep")
    descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    renamed = tmp_path / "pinned"
    parent.rename(renamed)
    parent.symlink_to(outside, target_is_directory=True)
    try:
        remove_tree_at("payload", descriptor)
    finally:
        os.close(descriptor)

    assert not (renamed / "payload").exists()
    assert (outside / "payload/keep").read_text() == "keep"


@pytest.mark.skipif(os.name != "posix", reason="descriptor-relative POSIX boundary")
def test_remove_tree_at_rejects_root_links_and_traversal_without_mutation(tmp_path):
    from maid_runner.core.uninstall import remove_tree_at

    parent = tmp_path / "owned"
    parent.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep").write_text("keep")
    (parent / "link").symlink_to(outside, target_is_directory=True)
    descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for name in ("link", "../outside", ".", "..", ""):
            with pytest.raises(ValueError):
                remove_tree_at(name, descriptor)
    finally:
        os.close(descriptor)

    assert (parent / "link").is_symlink()
    assert (outside / "keep").read_text() == "keep"
