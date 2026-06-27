"""Version metadata for MAID init-installed instruction payloads."""

from __future__ import annotations

from maid_runner.__version__ import __version__


INSTRUCTION_PAYLOAD_VERSION = "2026.06.27.1"


def instruction_payload_metadata() -> dict[str, str]:
    return {
        "maid_runner_version": __version__,
        "instruction_payload_version": INSTRUCTION_PAYLOAD_VERSION,
    }
