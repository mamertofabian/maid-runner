"""CLI handler for deterministic gaming-incident records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from maid_runner.core.incidents import (
    capture_incident,
    list_incidents,
    update_incident,
)


def cmd_incident(args: argparse.Namespace) -> int:
    try:
        if args.incident_command == "capture":
            path = capture_incident(
                ".maid/incidents",
                manifest=args.manifest,
                packet=_read_json_file(args.packet),
                rejected_diff=_read_text_file(args.rejected_diff),
                pattern_tags=_split_tags(args.tags),
                notes=args.notes,
            )
            print(path)
            return 0
        if args.incident_command == "update":
            update_incident(
                args.incident_path,
                chosen_diff=_read_text_file(args.chosen_diff),
            )
            print(args.incident_path)
            return 0
        if args.incident_command == "list":
            incidents = list_incidents(".maid/incidents", tag=args.tag)
            if args.json:
                print(json.dumps([_stored_to_dict(item) for item in incidents]))
            else:
                for incident in incidents:
                    print(incident.path)
            return 0
        print("Usage: maid incident {capture,update,list} ...", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


def _read_json_file(path: str) -> dict:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{source}: malformed JSON packet: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"{source}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{source}: packet JSON must be an object")
    return payload


def _read_text_file(path: str) -> str:
    source = Path(path)
    try:
        return source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"{source}: {exc}") from exc


def _split_tags(tags: str) -> tuple[str, ...]:
    return tuple(tag.strip() for tag in tags.split(",") if tag.strip())


def _stored_to_dict(stored) -> dict:
    record = stored.record
    return {
        "path": stored.path,
        "incident_version": record.incident_version,
        "created": record.created,
        "manifest": record.manifest,
        "gates": list(record.gates),
        "packet": record.packet,
        "rejected_diff": record.rejected_diff,
        "chosen_diff": record.chosen_diff,
        "pattern_tags": list(record.pattern_tags),
        "notes": record.notes,
    }
