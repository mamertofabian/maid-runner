# MAID Run Evaluation

MAID run evaluation is an after-action layer over evidence the runner already
records: plan locks, plan revisions, red-phase evidence, Outcome records,
incidents, and deterministic validation commands. It helps a human operator
review how a run behaved without turning evaluation into a workflow gate.

## Provenance

Run provenance is captured when the data is available. `maid plan lock` and
`maid plan revise` accept `--agent-model`, `--agent-provider`,
`--agent-client`, `--agent-skill`, and `--agent-instructions-fingerprint`.
The same values can come from `MAID_AGENT_MODEL`, `MAID_AGENT_PROVIDER`,
`MAID_AGENT_CLIENT`, `MAID_AGENT_SKILL`, and
`MAID_AGENT_INSTRUCTIONS_FINGERPRINT`.

Provenance is optional. Missing provenance is reported as unknown agent data in
evaluation output; it does not fail lock, revise, validate, verify, promote, or
handoff.

## Contract Deltas

Plan revisions store structured contract deltas from the previous locked
manifest to the revised manifest. Evaluation uses those deltas instead of
trusting an agent-authored reason string. A revision can be classified as
strengthening, narrowing, mixed, metadata-only, unchanged, or unclassified when
older evidence does not contain enough structure.

## Deterministic Commands

`maid evaluate run <manifest>` reports one run. It reads the manifest, its
plan lock, red evidence, Outcome record, and incidents, then prints evidence
counts and findings. Honest gaps are explicit: `unknown agent` for missing
provenance, `unclassified` for older revision evidence without deltas, and
`no-lock` when no lock evidence exists.

`maid evaluate compare` aggregates completed run evidence across manifests. It
groups by available provenance and reports per-dimension counts with run counts
visible. There are no composite scores because a single grade hides small
sample sizes, invites gaming, and hard-codes weighting policy into the runner.

## Advisory Run Review

The qualitative review pipeline is split between deterministic runner commands
and the `maid-run-review` skill:

1. `maid evaluate run <manifest>` shows the deterministic run evidence first.
2. `maid evaluate prompt <manifest> [--diff-file PATH]` writes the bounded
   review request. The runner never captures git diffs automatically; an
   operator or skill must prepare a diff file explicitly.
3. The skill sends only the bounded request to an available model. Before any
   cloud model call, it discloses what run evidence leaves the machine.
4. `maid evaluate validate <review.json> --request <request.json>` validates
   that the review cites only known evidence ids and stays inside the request's
   evidence universe.
5. `maid evaluate render <review.json> --request <request.json>` fails closed
   unless validation passes, then writes labeled advisory markdown.

The review is advisory, never a gate. It must not feed back into validate,
verify, plan lock, promote, readiness, or an implementing agent during an
active run.
