# Agent Retry Protocol

This protocol defines how MAID-aware agent loop tools retry failed gates with a
self-contained failure packet. It is a loop contract for reference tools under
`tools/`, not a new orchestrator product.

## Loop Contract

1. Run the gate with `--packet`, for example:

   ```bash
   uv run maid verify --packet .maid/last-failure-packet.json
   ```

2. If the gate passes, stop. A passing packet-aware gate removes stale packet
   state, so the loop must not replay an older packet.

3. If the gate fails, read the packet from `.maid/last-failure-packet.json` or
   the configured packet path.

4. Pass the parsed packet to the next agent attempt. The agent applies
   `next_action`-guided fixes within the active manifest scope, then the loop
   must re-run the same gate.

5. The default 5 attempt bound prevents silent endless retry. If the gate still
   fails after the bound, stop and escalate to a human with the final packet path
   and final packet content.

The loop must not reinterpret `next_action` kinds. If a packet names
`edit-tests`, `edit-manifest`, `revise-plan`, or `escalate-human`, that action
is surfaced to the agent as the packet's explicit instruction. Contract changes
stay loud through plan revision; the loop does not silently weaken tests or
manifests to make a gate pass.

## Packet Schema

Failure packets use these eight top-level keys:

- `packet_version`: integer schema version.
- `command`: command argv list for the failed gate.
- `exit_code`: failed gate exit code.
- `project_root`: absolute project root path.
- `manifest`: failed manifest entries, including path, goal, type, declared
  files, artifact lists, and validate commands.
- `diagnostics`: ordered errors and warnings with code, message, file, line
  where available, suggestion, and `next_action`.
- `test_output`: failed validate command output with exit code and bounded tail.
- `environment`: MAID and Python version details.

The packet contains retry context, not arbitrary repository contents. File
contents and full logs stay out of the packet so it remains prompt-sized.

## Escalation

Escalation is required when the attempt bound is exhausted, when the packet
explicitly requests `escalate-human`, or when the agent cannot act within the
manifest scope. Escalation output includes the final packet path and final
packet content so a human can inspect the exact failing gate state without
rerunning discovery.
