"""CLI handler for deterministic Outcome enrichment support."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile

from maid_runner.core.outcome_enrichment import (
    build_enrichment_request,
    digest_is_stale,
    read_enrichment_digest,
    render_digest_markdown,
    validate_enrichment_digest,
)
from maid_runner.core.outcomes import OutcomeIndex, outcome_index_is_stale
from maid_runner.core.outcomes import read_outcome_index


def cmd_enrich(args: argparse.Namespace) -> int:
    subcommand = getattr(args, "enrich_command", None)
    if subcommand not in {"prompt", "validate", "render"}:
        return _error("maid enrich requires one of: prompt, validate, render", args)

    try:
        index = _read_usable_index(args)
        if subcommand == "prompt":
            return _cmd_prompt(args, index)
        if subcommand == "validate":
            digest = _read_valid_digest(args, index)
            _emit_validate_success(args, digest_path=Path(args.digest))
            return 0
        digest = _read_valid_digest(args, index)
        markdown = render_digest_markdown(digest)
        _write_text_atomic(Path(args.md_output), markdown)
    except Exception as exc:
        return _error(str(exc), args)

    if getattr(args, "json", False):
        print(json.dumps({"md_output": str(Path(args.md_output)), "rendered": True}))
    else:
        print(f"Enrichment digest rendered: {Path(args.md_output)}")
    return 0


def _cmd_prompt(args: argparse.Namespace, index: OutcomeIndex) -> int:
    request = build_enrichment_request(index)
    payload = {
        "known_lesson_types": list(request.known_lesson_types),
        "known_manifest_slugs": list(request.known_manifest_slugs),
        "system_prompt": request.system_prompt,
        "user_prompt": request.user_prompt,
        "validation_universe": {
            "known_lesson_types": list(request.known_lesson_types),
            "known_manifest_slugs": list(request.known_manifest_slugs),
        },
    }
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    output = getattr(args, "output", None)
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


def _read_usable_index(args: argparse.Namespace) -> OutcomeIndex:
    index_path = Path(args.index)
    if not index_path.exists():
        raise ValueError(f"Outcome index not found: {index_path}")
    index = read_outcome_index(index_path)
    project_root = (
        args.project_root if args.project_root is not None else index.project_root
    )
    manifest_dir = (
        args.manifest_dir
        if args.manifest_dir is not None
        else _index_manifest_dir(index.manifest_dir, project_root)
    )
    if not getattr(args, "allow_stale_index", False):
        try:
            stale = outcome_index_is_stale(index_path, manifest_dir, project_root)
        except Exception as exc:
            raise ValueError(f"Outcome index staleness check failed: {exc}") from exc
        if stale:
            raise ValueError(
                "Outcome index is stale; run `maid learn` or pass "
                "--allow-stale-index"
            )
    return index


def _read_valid_digest(args: argparse.Namespace, index: OutcomeIndex):
    digest_path = Path(args.digest)
    if not digest_path.exists():
        raise ValueError(f"Enrichment digest not found: {digest_path}")
    digest = read_enrichment_digest(digest_path)
    validate_enrichment_digest(digest, index)
    if digest_is_stale(digest, index) and not getattr(args, "allow_stale_index", False):
        raise ValueError(
            "Enrichment digest is stale; regenerate it from the current Outcome "
            "index or pass --allow-stale-index"
        )
    return digest


def _emit_validate_success(args: argparse.Namespace, *, digest_path: Path) -> None:
    if getattr(args, "json", False):
        print(json.dumps({"digest": str(digest_path), "valid": True}))
    else:
        print(f"Enrichment digest valid: {digest_path}")


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(text)
            temp_file.flush()
        temp_path.replace(path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def _error(message: str, args: argparse.Namespace) -> int:
    if getattr(args, "json", False):
        print(json.dumps({"error": message}, sort_keys=True))
    else:
        print(f"Error: {message}", file=sys.stderr)
    return 2


def _index_manifest_dir(manifest_dir: str, project_root: str) -> str:
    path = Path(manifest_dir)
    if path.is_absolute():
        return str(path)
    return str(Path(project_root) / path)
