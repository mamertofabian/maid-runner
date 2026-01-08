#!/bin/bash
# MAID validation hook - runs after Write/Edit/MultiEdit on .py and .manifest.json files
# Blocks on validation failures (exit code 2 sends stderr to Claude)

# Read JSON input from stdin
input=$(cat)

# Extract file path from tool input (different tools use different field names)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // .tool_input.file // ""')

# Only validate .py and .manifest.json files
if [[ "$file_path" == *.py ]] || [[ "$file_path" == *.manifest.json ]]; then
    cd "$CLAUDE_PROJECT_DIR"

    # Capture both stdout and stderr, and the exit code
    output=$(uv run maid validate 2>&1)
    exit_code=$?

    if [[ $exit_code -ne 0 ]]; then
        # Validation failed - output to stderr and exit with code 2 to block
        echo "MAID validation failed for: $file_path" >&2
        echo "" >&2
        echo "$output" >&2
        exit 2
    fi

    # Validation passed - exit successfully
    exit 0
fi

# For other file types, exit successfully without running validation
exit 0
