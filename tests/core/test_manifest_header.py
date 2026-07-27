"""Behavioral tests for the self-describing manifest header banner.

The banner imports are function-local, matching tests/cli/test_manifest_cmd.py,
so the module still collects before the artifacts exist and the red phase is a
genuine assertion failure rather than a collection error.
"""

from __future__ import annotations

from pathlib import Path

from maid_runner.core.chain import _has_leading_inactive_marker_comment
from maid_runner.core.plan_lock import compute_manifest_contract_hash


_MANIFEST_BODY = 'schema: "2"\ngoal: "Example"\ntype: feature\n'


class TestManifestHeaderComment:
    def test_every_line_is_a_flush_left_comment(self):
        """Marker detection reads raw lines, so no banner line may be indented."""
        from maid_runner.core.manifest import MANIFEST_HEADER_COMMENT

        lines = MANIFEST_HEADER_COMMENT.splitlines()

        assert lines
        for line in lines:
            assert line.startswith("#"), f"banner line not flush-left: {line!r}"

    def test_banner_is_ascii_only(self):
        """Writers call write_text without an encoding, so non-ASCII can crash."""
        from maid_runner.core.manifest import MANIFEST_HEADER_COMMENT

        assert MANIFEST_HEADER_COMMENT.isascii()

    def test_banner_points_readers_at_the_project(self):
        """A curious reader needs somewhere to go."""
        from maid_runner.core.manifest import MANIFEST_HEADER_COMMENT

        assert "github.com/mamertofabian/maid-runner" in MANIFEST_HEADER_COMMENT

    def test_banner_says_it_is_not_required_to_build(self):
        """The first unasked question is whether the file is a build input."""
        from maid_runner.core.manifest import MANIFEST_HEADER_COMMENT

        assert "safe to ignore" in MANIFEST_HEADER_COMMENT.lower()


class TestPrependManifestHeader:
    def test_banner_goes_above_the_first_yaml_key(self):
        from maid_runner.core.manifest import (
            MANIFEST_HEADER_COMMENT,
            prepend_manifest_header,
        )

        result = prepend_manifest_header(_MANIFEST_BODY)

        assert result.startswith(MANIFEST_HEADER_COMMENT)
        assert result.endswith(_MANIFEST_BODY)

    def test_draft_kind_marker_keeps_line_one(self):
        """Existing drafts and drafts/README.md put the marker on line 1."""
        from maid_runner.core.manifest import (
            MANIFEST_HEADER_COMMENT,
            prepend_manifest_header,
        )

        source = f"# draft-kind: implementation\n{_MANIFEST_BODY}"

        result = prepend_manifest_header(source)

        assert result.splitlines()[0] == "# draft-kind: implementation"
        assert MANIFEST_HEADER_COMMENT.splitlines()[0] in result

    def test_archive_kind_marker_keeps_line_one(self):
        from maid_runner.core.manifest import prepend_manifest_header

        source = f"# archive-kind: consumed-draft-epic\n{_MANIFEST_BODY}"

        result = prepend_manifest_header(source)

        assert result.splitlines()[0] == "# archive-kind: consumed-draft-epic"

    def test_marker_detection_survives_the_banner(self):
        """chain.py bails at the first non-comment line; banner must be transparent."""
        from maid_runner.core.manifest import prepend_manifest_header

        source = f"# draft-kind: epic\n{_MANIFEST_BODY}"

        result = prepend_manifest_header(source)

        assert _has_leading_inactive_marker_comment(result) is True

    def test_applying_twice_matches_applying_once(self):
        from maid_runner.core.manifest import prepend_manifest_header

        once = prepend_manifest_header(_MANIFEST_BODY)

        twice = prepend_manifest_header(once)

        assert twice == once

    def test_body_quoting_the_banner_still_gets_a_banner(self):
        """Idempotency must key on the leading comment block, not the whole
        document, or a manifest that documents the banner silently loses it."""
        from maid_runner.core.manifest import (
            MANIFEST_HEADER_COMMENT,
            prepend_manifest_header,
        )

        quoted = MANIFEST_HEADER_COMMENT.splitlines()[0]
        body = f'schema: "2"\ndescription: |\n  The banner reads: {quoted}\n'

        result = prepend_manifest_header(body)

        assert result.startswith(MANIFEST_HEADER_COMMENT)
        assert result.endswith(body)

    def test_trailing_whitespace_on_a_banner_line_does_not_stack_a_banner(self):
        """Backfilling reads manifests an editor or formatter may have touched,
        so recognition must tolerate trailing whitespace on a banner line."""
        from maid_runner.core.manifest import (
            MANIFEST_HEADER_COMMENT,
            prepend_manifest_header,
        )

        lines = MANIFEST_HEADER_COMMENT.splitlines()
        # Build the scuffed banner without literal trailing spaces in this file.
        scuffed = "\n".join([lines[0] + "  ", *lines[1:]]) + "\n" + _MANIFEST_BODY

        result = prepend_manifest_header(scuffed)

        assert result == scuffed

    def test_only_prepends_and_leaves_body_bytes_untouched(self):
        from maid_runner.core.manifest import (
            MANIFEST_HEADER_COMMENT,
            prepend_manifest_header,
        )

        body = 'schema: "2"\n\n# an author comment\ngoal: "Keep me"\n'

        result = prepend_manifest_header(body)

        assert result.removeprefix(MANIFEST_HEADER_COMMENT) == body

    def test_banner_does_not_change_the_contract_hash(self, tmp_path: Path):
        """Comment-blind hashing is what makes backfill onto locked manifests safe."""
        from maid_runner.core.manifest import prepend_manifest_header

        plain = tmp_path / "plain.manifest.yaml"
        headed = tmp_path / "headed.manifest.yaml"
        plain.write_text(_MANIFEST_BODY)
        headed.write_text(prepend_manifest_header(_MANIFEST_BODY))

        assert compute_manifest_contract_hash(headed) == compute_manifest_contract_hash(
            plain
        )
