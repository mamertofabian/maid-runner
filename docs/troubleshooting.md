# Troubleshooting

Use this guide when MAID Runner validation, testing, manifest chains, or agent
workflows fail. Each entry gives the symptom, likely cause, and a concrete fix.
For machine-readable output, rerun the failing command with `--json` when the
command supports it.

## Common Issues

### 1. Manifest file is missing (`E001`)

Symptom: `maid validate manifests/task.manifest.yaml` reports `E001`.

Likely cause: The path passed to `maid validate`, `maid test --manifest`, or
another command does not exist from the current working directory.

Fix: Check the filename under `manifests/`, then rerun with the exact path. For
all active manifests, run `maid validate` without a manifest argument.

### 2. Manifest cannot be parsed (`E003`)

Symptom: Validation reports `E003` before any artifact checks run.

Likely cause: The YAML or JSON manifest is malformed, often because of
indentation, a missing quote, or an invalid list item.

Fix: Open the reported file and fix the syntax. Then run
`maid validate <manifest> --mode schema` before running behavioral or
implementation validation.

### 3. Manifest schema validation fails (`E004`)

Symptom: `maid validate --mode schema` reports `E004`.

Likely cause: A required field is missing, a field has the wrong type, or an
artifact declaration omits required details such as `args`, `returns`, `of`, or
`type`.

Fix: Compare the manifest with the v2 schema using `maid schema`. Keep public
function and method artifacts explicit, including zero-argument `args: []`.

### 4. A superseded manifest is missing (`E102`)

Symptom: Chain validation reports `E102`.

Likely cause: A manifest lists a slug in `supersedes`, but that older manifest
file is not present in the manifest directory.

Fix: Restore the superseded manifest, correct the slug, or remove the invalid
supersession link if the relationship was never intended. Use `maid chain log`
to inspect the visible manifest history.

### 5. Manifest supersession is circular (`E103`)

Symptom: `maid validate` or `maid chain log` reports `E103`.

Likely cause: Two or more manifests supersede each other in a cycle, so MAID
Runner cannot determine the active chain.

Fix: Break the cycle by keeping supersession one-way and chronological. Rerun
`maid chain log --active` to confirm only the intended manifests remain active.

### 6. No active manifests are found (`E112`)

Symptom: `maid validate` reports `E112`.

Likely cause: The manifest directory is empty, every manifest is inactive or
superseded, or the command is running from the wrong project root.

Fix: Run from the repository root, check `manifests/`, and verify that at least
one active manifest exists. For a new project, run `maid init` and add a
manifest before using full-repository validation.

### 7. A manifest path escapes the project (`E113`)

Symptom: A CLI command rejects a manifest path with `E113`.

Likely cause: The path points outside the project root through `..` segments or
an absolute path that is not under the repository.

Fix: Keep manifest paths inside the project. From the repository root, pass a
relative path such as `manifests/add-auth.manifest.yaml`.

### 8. Worktree scope fails (`E114`)

Symptom: `maid verify --worktree-scope` or `maid validate --worktree-scope`
reports `E114`.

Likely cause: A changed file is not declared by the active manifest chain as a
writable or tracked file for the current task.

Fix: Either add the file to the approved manifest scope before editing it, or
remove unrelated local changes from the task branch. Use `files.scope` when the
changed file is intentionally writable but has no stable public artifact
contract, such as Svelte route wiring covered through behavioral tests instead
of route-local state or private handlers. Use `maid files` to inspect file
tracking status.

### 9. Changed-scope baseline is required (`E115`)

Symptom: `maid verify --changed-scope` reports `E115`.

Likely cause: The command needs a baseline through `metadata.maid_task_base`,
`--since`, or `--base-ref` so it can compare the current task safely.

Fix: Add the correct baseline metadata to the manifest, or rerun
`maid verify --changed-scope --base-ref <ref>` for the intended comparison.

### 10. Changed-scope baseline is invalid (`E116`)

Symptom: `maid validate --changed-scope` reports `E116`.

Likely cause: The requested base ref does not exist, cannot be resolved, or is
not usable in the current Git checkout.

Fix: Fetch the missing ref if needed, then pass a valid branch, tag, or commit
to `--base-ref`.

### 11. Active manifest is marked inactive (`E117`)

Symptom: Full validation reports `E117` for a manifest that still participates
in the active chain.

Likely cause: The manifest has inactive lifecycle metadata but has not been
properly superseded or archived out of the active set.

Fix: Either remove the inactive status from the active manifest or create the
correct superseding manifest so the old one is no longer active.

### 12. Artifact is not used by behavioral tests (`E200`)

Symptom: `maid validate --mode behavioral` reports `E200`.

Likely cause: The manifest declares a public artifact, but the declared tests
do not reference that exact identifier.

Fix: Add or update behavioral tests so they exercise the public artifact by
name. Do not satisfy `E200` by importing private helpers or by weakening the
manifest declaration.

### 13. Declared test file is missing (`E201`)

Symptom: Behavioral validation reports `E201`.

Likely cause: A test path listed in the manifest does not exist.

Fix: Create the test file or correct the path in the manifest. Then rerun
`maid validate <manifest> --mode behavioral`.

### 14. Test file is not listed as read-only (`E202`)

Symptom: Behavioral validation reports `E202`.

Likely cause: The manifest validate command runs a test file that is not
declared in the manifest's test/read scope.

Fix: Add the test file to the manifest's contextual scope or adjust the validate
command to run only declared behavioral tests.

### 15. Tests have no assertions (`E210`)

Symptom: Validation or `maid verify` reports `E210`.

Likely cause: A behavioral test references artifacts but does not assert
observable behavior.

Fix: Add assertions for the user-visible or API-visible behavior. Prefer direct
behavior checks over private state or incidental implementation details.

### 16. No test files are declared (`E220`)

Symptom: Behavioral or implementation coverage reports `E220`.

Likely cause: The manifest declares production artifacts but has no associated
test files.

Fix: Add focused tests and include them in the manifest scope and `validate`
commands. Then run `maid validate --mode behavioral`.

### 17. Validate command does not run tests (`E230`)

Symptom: `maid test --manifest <manifest>` or behavioral validation reports
`E230`.

Likely cause: A command in `validate:` does not invoke a recognized test runner
or omits the contextual test files declared by the manifest.

Fix: Use a real test command such as `uv run python -m pytest -q <tests>`.
Include every contextual behavioral test file in the manifest's validate
command.

### 18. Declared artifact is not defined (`E300`)

Symptom: `maid validate --mode implementation` reports `E300`.

Likely cause: The implementation does not define the public function, class,
method, type, or attribute declared by the manifest.

Fix: Implement the declared artifact with the exact name and parent context, or
correct the manifest if the approved plan used the wrong public API.

### 19. Unexpected artifact is present (`E301`)

Symptom: Implementation validation reports `E301`.

Likely cause: A file in create mode or strict chain mode contains an undeclared
public symbol.

Fix: Remove the accidental public API, make the helper private if appropriate,
or evolve the manifest before intentionally adding a new public artifact.

### 20. Signature does not match (`E303`)

Symptom: Implementation validation reports `E303`.

Likely cause: A function or method has different arguments than the manifest
declares.

Fix: Align the implementation signature with the manifest, including argument
names. If the signature change is intentional, evolve the manifest first.

### 21. Declared file should be present (`E306`)

Symptom: Implementation validation reports `E306`.

Likely cause: A file listed under `files.create` or `files.edit` is missing.

Fix: Create or restore the file, then rerun
`maid validate <manifest> --mode implementation`.

### 22. No validator is available (`E307`)

Symptom: Validation reports `E307` for a file such as documentation or an
unsupported extension.

Likely cause: MAID Runner has no language validator for that file type.

Fix: For documentation files, treat the diagnostic as a visibility signal and
cover behavior through tests that read the markdown. For code files, install the
needed optional dependency or keep the file out of contracted artifact scope.

### 23. Source cannot be parsed (`E308`)

Symptom: Implementation or behavioral validation reports `E308`.

Likely cause: The source file has syntax that the configured parser cannot
parse, or an optional parser dependency is missing or incompatible.

Fix: Run the language's normal syntax check, install the relevant optional
extra such as `maid-runner[typescript]`, and rerun `maid validate`.

### 24. Stub implementation is detected (`E310`)

Symptom: `maid validate --mode implementation --check-stubs` or `maid verify`
reports `E310`.

Likely cause: A declared artifact still contains a placeholder body such as
`pass`, `TODO`, or `NotImplementedError`.

Fix: Replace the placeholder with real behavior that passes the declared tests.
If the artifact is intentionally abstract, make sure it uses supported abstract
method conventions.

### 25. Removed artifact still exists (`E311`)

Symptom: Validation reports `E311`.

Likely cause: The manifest says an artifact was intentionally removed, but the
symbol is still present in the source file.

Fix: Delete the artifact from the source or correct the manifest if removal was
not intended.

### 26. Required import is missing (`E320`)

Symptom: Implementation validation reports `E320`.

Likely cause: A manifest declares required imports, but the source file does not
import the dependency through a recognized path.

Fix: Add the required import in code, preserving module identity. For complex
TypeScript projects, confirm `tsconfig` paths and package exports resolve as
expected.

### 27. Artifact is not executed by tests (`E710`)

Symptom: `maid validate --artifact-coverage` or
`maid verify --artifact-coverage` reports
`E710 ARTIFACT_NOT_EXECUTED_BY_TESTS`.

Likely cause: The behavioral tests never execute the artifact body. Importing,
mentioning, or indirectly referencing a declared function or method is not
runtime evidence that the artifact behavior is constrained.

Fix: Write or update a focused behavioral test that calls the declared artifact
through its normal public path and asserts observable behavior. Install
`maid-runner[quality]` when artifact coverage is requested in an environment
that does not include the optional coverage dependency.

### 28. Knockout is not detected by tests (`E711`)

Symptom: `maid verify --knockout` reports
`E711 ARTIFACT_KNOCKOUT_NOT_DETECTED` for a declared artifact.

Likely cause: The tests do not constrain the artifact behavior. MAID replaced
the artifact body with `raise NotImplementedError("maid-knockout")`, but every
validate command still exited 0.

Fix: Strengthen the behavioral assertions so breaking the named artifact makes
at least one declared validate command fail. Keep the gate opt-in and scoped to
Python public function and method artifacts.

### 29. Knockout harness failed (`E712`)

Symptom: `maid verify --knockout` reports
`E712 KNOCKOUT_HARNESS_FAILURE`.

Likely cause: The knockout harness could not safely complete the rewrite,
validate, or restore cycle for the named file. Common causes include parse
failures, command spawn failures, dirty target files when
`--knockout-allow-dirty` was not supplied, or a restore hash mismatch.

Fix: Check the named file and rerun after correcting the harness failure. If a
restore failure leaves the file dirty, recover it with
`git checkout -- <file>`, then inspect the diff before retrying.

### 30. Coherence diagnostics appear

Symptom: `maid validate --coherence` reports coherence issues by severity and
message.

Likely cause: The manifest graph has duplicate declarations, conflicting
signatures, boundary violations, naming issues, or missing dependencies.

Fix: Inspect the specific diagnostic, then use `maid graph query` or
`maid coherence --json` to find the related manifests and artifacts before
editing the contract.

### 31. Acceptance test file is missing (`E500`)

Symptom: Validation reports `E500`.

Likely cause: The manifest references an acceptance test path that is absent
from the repository.

Fix: Restore the acceptance test or correct the manifest reference. Acceptance
tests should represent the external behavior expected from the task.

### 32. Test function behavior mismatch (`E610`)

Symptom: Validation warns that a declared test function's behavior does not
match its manifest description.

Likely cause: The test declaration says it calls or verifies one thing, but the
test body does not reference that public artifact or behavior.

Fix: Update the behavioral test to exercise the declared public artifact by
exact identifier, or revise the manifest before approval if the declaration is
wrong.

### 33. Outcome recall is stale or empty

Symptom: `maid recall` returns no useful results for a topic that should have
prior outcomes.

Likely cause: The deterministic Outcome index has not been refreshed since
recent manifest outcomes were added.

Fix: Run `maid learn` to refresh the index, then rerun `maid recall --text
"<topic>"`. Use explicit filters such as `--path`, `--artifact`, or
`--manifest-slug` when the result set is noisy.

## FAQ

### FAQ: Should I run `maid validate`, `maid test`, or `maid verify`?

Use `maid validate` to check manifest structure and artifact alignment. Use
`maid test` to run the commands declared by manifests. Use `maid verify` as the
combined done gate when you want validation, tests, scope checks, and warning
policy in one command.

### FAQ: Why does behavioral validation fail before implementation exists?

Behavioral validation checks whether tests reference declared artifacts. It can
pass before implementation if the tests are correctly written. The tests
themselves should still fail in the red phase until implementation is added.

### FAQ: Can I fix validation by editing the manifest after approval?

Only if the plan is wrong and the manifest is intentionally revised. Normal
implementation work should change code and documentation within the approved
scope, then run `maid validate --mode implementation` and the declared tests.

### FAQ: What should I do when `maid test --manifest` reports `E230`?

Check the manifest `validate:` commands. They must invoke a recognized test
runner and include the contextual test files declared by the manifest.

### FAQ: How do I inspect chain history?

Run `maid chain log` for full history, `maid chain log --active` for active
manifests, and `maid chain replay` to preview effective artifacts at a point in
time.

### FAQ: How do I investigate supersession drift?

Run `maid audit supersessions` to inspect supersession artifact preservation.
Use the reported manifest slugs and artifact names to decide whether to restore,
seal, or intentionally supersede the contract.

### FAQ: How do I use past lessons from completed work?

Run `maid learn` after outcomes are added, then search with `maid recall`.
Outcome records are planning evidence only; they do not replace behavioral
tests, declared scope, validation, or implementation review.
