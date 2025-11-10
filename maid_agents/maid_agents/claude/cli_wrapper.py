"""Claude CLI Wrapper - Invokes Claude Code headless mode."""

import json
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class ClaudeResponse:
    """Response from Claude Code CLI."""

    success: bool
    result: str
    error: str
    session_id: Optional[str] = None


class ClaudeWrapper:
    """Wraps Claude Code headless CLI invocations."""

    def __init__(self, mock_mode: bool = True):
        """Initialize Claude wrapper.

        Args:
            mock_mode: If True, returns mock responses without calling Claude
        """
        self.mock_mode = mock_mode

    def generate(
        self, prompt: str, model: str = "claude-sonnet-4-5-20250929"
    ) -> ClaudeResponse:
        """Generate response using Claude Code headless mode.

        Args:
            prompt: The prompt to send to Claude
            model: Claude model to use

        Returns:
            ClaudeResponse with result or error
        """
        if self.mock_mode:
            # Return mock response for testing
            return ClaudeResponse(
                success=True,
                result=f"Mock response for prompt: {prompt[:50]}...",
                error="",
                session_id="mock-session-123",
            )

        # Real Claude invocation
        # Note: -p/--print flag is required for non-interactive output
        cmd = ["claude", "--print", prompt, "--output-format", "json"]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                # Parse JSON response
                try:
                    data = json.loads(result.stdout)
                    return ClaudeResponse(
                        success=True,
                        result=data.get("result", ""),
                        error="",
                        session_id=data.get("session_id"),
                    )
                except json.JSONDecodeError:
                    # Fallback to plain text
                    return ClaudeResponse(
                        success=True, result=result.stdout, error="", session_id=None
                    )
            else:
                return ClaudeResponse(
                    success=False, result="", error=result.stderr, session_id=None
                )

        except subprocess.TimeoutExpired:
            return ClaudeResponse(
                success=False, result="", error="Claude CLI timed out", session_id=None
            )
        except FileNotFoundError:
            return ClaudeResponse(
                success=False,
                result="",
                error="Claude CLI not found. Please install Claude Code.",
                session_id=None,
            )
        except Exception as e:
            return ClaudeResponse(
                success=False, result="", error=str(e), session_id=None
            )
