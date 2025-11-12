"""Schema command for MAID CLI.

Outputs the manifest JSON schema for agent consumption.
"""

import json
import sys
from pathlib import Path


def run_schema() -> None:
    """Output the manifest JSON schema to stdout.

    This command reads the manifest.schema.json file and outputs it
    as pretty-printed JSON for consumption by MAID agents and tools.
    """
    # Get the schema file path relative to this module
    schema_path = (
        Path(__file__).parent.parent / "validators" / "schemas" / "manifest.schema.json"
    )

    if not schema_path.exists():
        print(f"Error: Schema file not found at {schema_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(schema_path, "r") as f:
            schema_data = json.load(f)

        # Output as pretty-printed JSON
        print(json.dumps(schema_data, indent=2))

    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in schema file: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading schema: {e}", file=sys.stderr)
        sys.exit(1)
