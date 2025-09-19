#!/usr/bin/env python3
"""
Stop hook for todo completion validation.
Uses Ollama to intelligently determine if tasks are actually completed vs just questions/permissions.
"""
import json
import sys
import os
import subprocess
import re
from typing import Dict, Any, Optional


def parse_transcript(transcript_path: str) -> Dict[str, Any]:
    """Parse the Claude Code transcript to extract conversation context."""
    transcript_data = {
        "user_messages": [],
        "assistant_messages": [],
        "tool_uses": [],
        "conversation_summary": "",
    }

    if not transcript_path or not os.path.exists(transcript_path):
        return transcript_data

    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Parse each line of JSONL
        for line in lines:
            try:
                entry = json.loads(line.strip())
                entry_type = entry.get("type", "")

                if entry_type == "user":
                    # User message - check for both old and new format
                    content = entry.get("content", "")

                    # New format: message.content array
                    if not content and "message" in entry:
                        message_content = entry["message"].get("content", [])
                        if isinstance(message_content, list):
                            text_content = []
                            for block in message_content:
                                if (
                                    isinstance(block, dict)
                                    and block.get("type") == "text"
                                ):
                                    text_content.append(block.get("text", ""))
                            content = "\n".join(text_content)

                    # Old format: direct content array
                    elif isinstance(content, list):
                        text_content = []
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text_content.append(block.get("text", ""))
                        content = "\n".join(text_content)

                    if content and len(content.strip()) > 0:
                        transcript_data["user_messages"].append(content.strip())

                elif entry_type == "assistant":
                    # Assistant message - check for both old and new format
                    content = entry.get("content", "")

                    # New format: message.content array
                    if not content and "message" in entry:
                        message_content = entry["message"].get("content", [])
                        if isinstance(message_content, list):
                            text_content = []
                            for block in message_content:
                                if isinstance(block, dict):
                                    if block.get("type") == "text":
                                        text_content.append(block.get("text", ""))
                                    elif block.get("type") == "tool_use":
                                        tool_name = block.get("name", "unknown")
                                        transcript_data["tool_uses"].append(tool_name)
                            content = "\n".join(text_content)

                    # Old format: direct content array
                    elif isinstance(content, list):
                        text_content = []
                        for block in content:
                            if isinstance(block, dict):
                                if block.get("type") == "text":
                                    text_content.append(block.get("text", ""))
                                elif block.get("type") == "tool_use":
                                    tool_name = block.get("name", "unknown")
                                    transcript_data["tool_uses"].append(tool_name)
                        content = "\n".join(text_content)

                    if content and len(content.strip()) > 0:
                        transcript_data["assistant_messages"].append(content.strip())

            except json.JSONDecodeError:
                continue

        # Create a conversation summary from recent messages
        all_messages = []
        for i, user_msg in enumerate(transcript_data["user_messages"]):
            all_messages.append(
                f"User: {user_msg[:200]}{'...' if len(user_msg) > 200 else ''}"
            )
            if i < len(transcript_data["assistant_messages"]):
                assistant_msg = transcript_data["assistant_messages"][i]
                all_messages.append(
                    f"Assistant: {assistant_msg[:200]}{'...' if len(assistant_msg) > 200 else ''}"
                )

        transcript_data["conversation_summary"] = "\n".join(
            all_messages[-10:]
        )  # Last 10 exchanges

    except Exception:
        pass

    return transcript_data


def clean_ollama_output(output: str) -> str:
    """Clean ANSI escape sequences and control characters from Ollama output."""
    # Remove ANSI escape sequences
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    cleaned = ansi_escape.sub("", output)

    # Remove other control characters but keep newlines and tabs
    cleaned = "".join(char for char in cleaned if ord(char) >= 32 or char in "\n\t")

    # Remove spinner/progress characters commonly used by Ollama
    spinner_chars = ["⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏", "⠋", "⠉", "⠈"]
    for char in spinner_chars:
        cleaned = cleaned.replace(char, "")

    # Clean up extra whitespace
    cleaned = re.sub(r"\n\s*\n", "\n", cleaned)  # Remove empty lines
    cleaned = re.sub(r" +", " ", cleaned)  # Collapse multiple spaces

    return cleaned.strip()


def get_ollama_task_analysis(
    transcript_data: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Use Ollama to analyze if tasks were actually completed or just questions/permissions asked."""
    model = "qwen2.5-coder:latest"  # Code-focused model for better accuracy

    # Build context from conversation
    context_info = []

    # Add recent conversation context
    if transcript_data["conversation_summary"]:
        context_info.append(
            f"Recent conversation:\n{transcript_data['conversation_summary']}"
        )

    # Add tool usage patterns
    if transcript_data["tool_uses"]:
        tool_summary = {}
        for tool in transcript_data["tool_uses"]:
            tool_summary[tool] = tool_summary.get(tool, 0) + 1
        top_tools = sorted(tool_summary.items(), key=lambda x: x[1], reverse=True)[:5]
        context_info.append(
            f"Tools used: {', '.join([f'{tool}({count})' for tool, count in top_tools])}"
        )

    if not context_info:
        return None

    prompt = f"""Analyze this Claude Code conversation to determine if actual work was completed or if the assistant was just asking questions or requesting permissions.

Conversation Context:
{chr(10).join(context_info)}

Determine:
1. Was actual work completed (code changes, implementations, fixes, etc.)?
2. Was the assistant mainly asking questions or requesting permissions?
3. What specific tasks or goals were mentioned by the user?
4. What was actually accomplished vs what was just discussed?

Respond with ONLY a valid JSON object containing:
- "work_completed": boolean (true if actual work was done)
- "completion_confidence": float (0.0 to 1.0)
- "task_type": string (e.g., "implementation", "question", "permission_request", "discussion")
- "summary": string (brief description of what happened)
- "user_goals": array of strings (goals mentioned by user)
- "accomplishments": array of strings (what was actually done)

Focus on distinguishing between actual work completion and just conversation/discussion. Return ONLY valid JSON, no other text."""

    try:
        # Capture stdout but suppress stderr progress indicators
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,  # Suppress progress indicators
            text=True,
            timeout=20,  # Increased timeout
        )

        if result.returncode == 0 and result.stdout.strip():
            # Clean the output of ANSI codes and control characters
            output = clean_ollama_output(result.stdout)

            # Try multiple extraction strategies
            extracted_json = None

            # Strategy 1: Try raw output first
            try:
                extracted_json = json.loads(output)
            except json.JSONDecodeError:
                pass

            # Strategy 2: Extract from markdown code blocks
            if not extracted_json and "```" in output:
                json_match = re.search(r"```(?:json)?\n?(.*?)\n?```", output, re.DOTALL)
                if json_match:
                    try:
                        extracted_json = json.loads(json_match.group(1).strip())
                    except json.JSONDecodeError:
                        pass

            # Strategy 3: Find JSON-like structure anywhere in text
            if not extracted_json:
                # Look for anything that looks like JSON object - improved regex
                json_pattern = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"
                json_matches = re.findall(json_pattern, output, re.DOTALL)
                for match in json_matches:
                    try:
                        # Try to parse each potential JSON object
                        potential_json = json.loads(match)
                        # Verify it has at least some expected fields
                        if any(
                            key in potential_json
                            for key in ["work_completed", "task_type", "summary"]
                        ):
                            extracted_json = potential_json
                            break
                    except json.JSONDecodeError:
                        continue

            # Strategy 4: Extract first complete JSON object from cleaned text
            if not extracted_json:
                # Find the first { and matching }
                lines = output.split("\n")
                json_lines = []
                brace_count = 0
                collecting = False

                for line in lines:
                    if "{" in line and not collecting:
                        collecting = True

                    if collecting:
                        json_lines.append(line)
                        brace_count += line.count("{") - line.count("}")

                        if brace_count <= 0:  # Found matching closing brace
                            break

                if json_lines:
                    try:
                        json_text = "\n".join(json_lines)
                        # Clean up common issues
                        json_text = re.sub(
                            r",\s*}", "}", json_text
                        )  # Remove trailing commas
                        json_text = re.sub(r",\s*]", "]", json_text)
                        extracted_json = json.loads(json_text)
                    except json.JSONDecodeError:
                        pass

            # If we extracted JSON, validate and use it
            if extracted_json and isinstance(extracted_json, dict):
                # Ensure required fields with defaults
                return {
                    "work_completed": extracted_json.get("work_completed", False),
                    "completion_confidence": float(
                        extracted_json.get("completion_confidence", 0.5)
                    ),
                    "task_type": extracted_json.get("task_type", "unknown"),
                    "summary": extracted_json.get("summary", "")[:500],  # Limit length
                    "user_goals": extracted_json.get("user_goals", []),
                    "accomplishments": extracted_json.get("accomplishments", []),
                }

            # Fallback: Analyze text heuristically
            text = output.lower()

            # More sophisticated heuristics
            completion_keywords = [
                "completed",
                "finished",
                "done",
                "successfully",
                "implemented",
                "fixed",
                "resolved",
                "created",
                "added",
                "updated",
                "modified",
            ]
            question_keywords = [
                "?",
                "should i",
                "would you like",
                "do you want",
                "shall i",
                "can i",
                "may i",
                "permission",
                "confirm",
                "proceed",
            ]

            completion_score = sum(1 for kw in completion_keywords if kw in text)
            question_score = sum(1 for kw in question_keywords if kw in text)

            # Determine if work was likely completed
            work_completed = completion_score > 2 and question_score < 2
            confidence = min(completion_score * 0.15, 0.9) if work_completed else 0.3

            # Guess task type from keywords
            if question_score > completion_score:
                task_type = "question"
            elif "implement" in text or "creat" in text or "add" in text:
                task_type = "implementation"
            elif "fix" in text or "resolv" in text or "debug" in text:
                task_type = "bugfix"
            elif "discuss" in text or "explain" in text:
                task_type = "discussion"
            else:
                task_type = "unknown"

            return {
                "work_completed": work_completed,
                "completion_confidence": confidence,
                "task_type": task_type,
                "summary": output[:200] if output else "No summary available",
                "user_goals": [],
                "accomplishments": [],
            }

    except subprocess.TimeoutExpired:
        # Handle timeout specifically
        pass
    except Exception:
        # Log the error for debugging (could write to a log file)
        pass

    return None


def analyze_transcript(transcript_path: str) -> Dict[str, Any]:
    """
    Analyze the conversation transcript using Ollama to understand what was accomplished.
    """
    try:
        if not os.path.exists(transcript_path):
            return {"tasks_mentioned": 0, "likely_completed": False, "analysis": None}

        # Parse transcript for better context
        transcript_data = parse_transcript(transcript_path)

        # Use Ollama for intelligent analysis
        ollama_analysis = get_ollama_task_analysis(transcript_data)

        if ollama_analysis:
            return {
                "tasks_mentioned": len(ollama_analysis.get("user_goals", [])),
                "likely_completed": ollama_analysis.get("work_completed", False),
                "completion_confidence": ollama_analysis.get(
                    "completion_confidence", 0.0
                ),
                "task_type": ollama_analysis.get("task_type", "unknown"),
                "analysis": ollama_analysis,
            }

        # Fallback to simple keyword analysis if Ollama fails
        with open(transcript_path, "r") as f:
            lines = f.readlines()

        recent_lines = lines[-50:] if len(lines) > 50 else lines
        completion_indicators = [
            "completed",
            "finished",
            "done",
            "successfully",
            "fixed",
            "implemented",
            "created",
            "updated",
        ]

        completion_count = sum(
            1
            for line in recent_lines
            for indicator in completion_indicators
            if indicator in line.lower()
        )

        return {
            "tasks_mentioned": completion_count,
            "likely_completed": completion_count > 2,
            "completion_confidence": 0.5,
            "task_type": "fallback_analysis",
            "analysis": None,
        }
    except Exception:
        return {"tasks_mentioned": 0, "likely_completed": False, "analysis": None}


def check_todo_status(stop_hook_active: bool, transcript_path: str) -> Dict[str, Any]:
    """
    Check if todos need updating based on work completed using Ollama analysis.
    """
    # Don't run recursively if we're already in a stop hook
    if stop_hook_active:
        return {"continue": True, "suppressOutput": True}

    # Analyze what was done using Ollama
    analysis = analyze_transcript(transcript_path)

    # Use Ollama analysis if available
    if analysis.get("analysis"):
        ollama_data = analysis["analysis"]
        work_completed = ollama_data.get("work_completed", False)
        confidence = ollama_data.get("completion_confidence", 0.0)
        task_type = ollama_data.get("task_type", "unknown")
        summary = ollama_data.get("summary", "")

        # Only block if we're confident work was actually completed
        if work_completed and confidence > 0.6:
            # Different messages based on task type
            if task_type in ["question", "permission_request", "discussion"]:
                return {"continue": True, "suppressOutput": True}
            else:
                return {
                    "decision": "block",
                    "reason": (
                        f"🏁 Work completed with {confidence:.0%} confidence!\n\n"
                        f"Task type: {task_type}\n"
                        f"Summary: {summary}\n\n"
                        "Please:\n"
                        "1. Update todo list to mark completed items\n"
                        "2. Review if any new tasks were discovered\n"
                        "3. Confirm all changes align with original goals\n\n"
                        "Use TodoWrite to update task status, then continue."
                    ),
                }
        elif task_type in ["question", "permission_request"]:
            # Don't block for questions or permission requests
            return {"continue": True, "suppressOutput": True}
        else:
            # Low confidence or unclear - just suppress output
            return {"continue": True, "suppressOutput": True}

    # Fallback to original logic if Ollama analysis not available
    if analysis["likely_completed"]:
        return {
            "decision": "block",
            "reason": (
                "🏁 Work appears to be completed! Please:\n"
                "1. Update todo list to mark completed items\n"
                "2. Review if any new tasks were discovered\n"
                "3. Confirm all changes align with original goals\n\n"
                "Use TodoWrite to update task status, then continue."
            ),
        }

    # Otherwise, just suppress output (no reminder needed)
    return {"continue": True, "suppressOutput": True}


def main():
    """Process Stop event."""
    try:
        # Read hook input
        data = json.load(sys.stdin)

        # Extract relevant information
        hook_event = data.get("hook_event_name", "")
        stop_hook_active = data.get("stop_hook_active", False)
        transcript_path = data.get("transcript_path", "")

        # Only process Stop events
        if hook_event != "Stop":
            sys.exit(0)

        # Check todo status
        response = check_todo_status(stop_hook_active, transcript_path)

        # Output JSON response
        print(json.dumps(response))
        sys.exit(0)

    except Exception as e:
        # On error, don't block
        print(f"Hook error: {e}", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
