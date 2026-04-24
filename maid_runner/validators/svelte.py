"""Svelte validator for MAID Runner v2.

Extracts script blocks from .svelte files and delegates to TypeScriptValidator.
Requires tree-sitter-svelte.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Union

from maid_runner.validators.base import BaseValidator, CollectionResult

try:
    from maid_runner.validators.typescript import TypeScriptValidator

    _HAS_TS = True
except ImportError:
    _HAS_TS = False


# Regex to extract <script> content from Svelte files
_SCRIPT_RE = re.compile(
    r"<script[^>]*>(.*?)</script>",
    re.DOTALL,
)


class SvelteValidator(BaseValidator):
    def __init__(self) -> None:
        if not _HAS_TS:
            raise ImportError(
                "TypeScriptValidator is required for Svelte validation. "
                "Install tree-sitter-typescript."
            )
        self._ts_validator = TypeScriptValidator()

    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".svelte",)

    def collect_implementation_artifacts(
        self,
        source: str,
        file_path: Union[str, Path],
    ) -> CollectionResult:
        script_content = _extract_script(source)
        if not script_content:
            return CollectionResult(
                artifacts=[], language="svelte", file_path=str(file_path)
            )
        # Delegate to TypeScript validator with .ts extension
        result = self._ts_validator.collect_implementation_artifacts(
            script_content, str(file_path).replace(".svelte", ".ts")
        )
        return CollectionResult(
            artifacts=result.artifacts,
            language="svelte",
            file_path=str(file_path),
            errors=result.errors,
        )

    def collect_behavioral_artifacts(
        self,
        source: str,
        file_path: Union[str, Path],
    ) -> CollectionResult:
        script_content = _extract_script(source)
        if not script_content:
            return CollectionResult(
                artifacts=[], language="svelte", file_path=str(file_path)
            )
        result = self._ts_validator.collect_behavioral_artifacts(
            script_content, str(file_path).replace(".svelte", ".ts")
        )
        return CollectionResult(
            artifacts=result.artifacts,
            language="svelte",
            file_path=str(file_path),
            errors=result.errors,
        )

    def get_test_function_bodies(
        self,
        source: str,
        file_path: Union[str, Path],
    ) -> dict[str, str]:
        script_content = _extract_script(source)
        if not script_content:
            return {}
        return self._ts_validator.get_test_function_bodies(
            script_content, str(file_path).replace(".svelte", ".ts")
        )


def _extract_script(source: str) -> str:
    """Extract content from <script> tags."""
    matches = _SCRIPT_RE.findall(source)
    return "\n".join(matches)
