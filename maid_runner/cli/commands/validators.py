"""CLI handler for the `maid validators` audit command."""

from __future__ import annotations

import argparse
import json
from typing import Any

from maid_runner.validators.registry import ValidatorRegistry


def cmd_validators(args: argparse.Namespace) -> int:
    """List validators known to the registry in text or JSON form."""
    registry = ValidatorRegistry.with_builtin_validators()
    rows = [_validator_row(record) for record in registry.validator_records()]

    if args.json:
        print(json.dumps({"validators": rows}, indent=2))
    else:
        print(_format_validator_table(rows))
    return 0


def _validator_row(record: Any) -> dict[str, object]:
    return {
        "name": record.name,
        "extensions": sorted(record.extensions),
        "source": record.source,
        "status": record.status,
        "detail": record.detail,
    }


def _format_validator_table(rows: list[dict[str, object]]) -> str:
    columns = ("name", "extensions", "source", "status", "detail")
    rendered_rows = [
        {
            "name": str(row["name"]),
            "extensions": _format_extensions(row["extensions"]),
            "source": str(row["source"]),
            "status": str(row["status"]),
            "detail": _format_detail(row["detail"]),
        }
        for row in rows
    ]
    widths = {
        column: max(len(column), *(len(row[column]) for row in rendered_rows))
        for column in columns
    }

    lines = [
        _format_validator_table_line(columns, widths),
        _format_validator_table_line(
            tuple("-" * widths[column] for column in columns), widths
        ),
    ]
    lines.extend(
        _format_validator_table_line(tuple(row[column] for column in columns), widths)
        for row in rendered_rows
    )
    return "\n".join(lines)


def _format_validator_table_line(
    values: tuple[str, ...], widths: dict[str, int]
) -> str:
    columns = ("name", "extensions", "source", "status", "detail")
    return "  ".join(
        value.ljust(widths[column]) for value, column in zip(values, columns)
    ).rstrip()


def _format_extensions(extensions: object) -> str:
    if not extensions:
        return "-"
    return ", ".join(str(extension) for extension in extensions)


def _format_detail(detail: object) -> str:
    if detail is None or detail == "":
        return "-"
    return str(detail)
