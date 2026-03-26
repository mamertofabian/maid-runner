# Ecosystem Update Prompts

These prompts update the 3 ecosystem tools to use maid-runner v2's library API
instead of subprocess wrapping. Run each in a separate Claude Code session in
the respective project directory.

## maid-lsp

```
maid-runner v2.0.0 has been published to PyPI with a library-first API.
Update this project to use direct library imports instead of subprocess calls.

Current state: maid_lsp/validation/runner.py uses asyncio.create_subprocess_exec
to call `maid validate` and `maid manifests` CLI commands, then parses JSON stdout.

What to change:

1. Update pyproject.toml: change maid-runner dependency to >=2.0.0

2. Replace subprocess calls in maid_lsp/validation/runner.py:

   Before:
     process = await asyncio.create_subprocess_exec(
         self.maid_runner_path, "validate", str(manifest_path),
         "--validation-mode", mode.value, "--use-manifest-chain", "--json-output", ...
     )
     stdout, _ = await process.communicate()
     result = json.loads(stdout)

   After:
     from maid_runner import validate, ValidationMode
     result = validate(
         str(manifest_path),
         mode=ValidationMode(mode.value),
         use_chain=True,
     )
     # result is already a ValidationResult object — no JSON parsing needed
     # result.success, result.errors, result.warnings, result.to_dict()

   For the manifests listing:
     from maid_runner import ManifestChain
     chain = ManifestChain(manifest_dir)
     manifests = chain.manifests_for_file(str(file_path))

3. Since maid-runner's validate() is synchronous but maid-lsp is async,
   wrap calls with asyncio.to_thread():
     result = await asyncio.to_thread(validate, str(manifest_path), ...)

4. Remove the maid_runner_path config (no longer needed — it's a library import).

5. Update tests to assert against ValidationResult objects instead of
   mocking subprocess calls.

6. Run the existing test suite to verify nothing breaks.
```

## maid-runner-mcp

```
maid-runner v2.0.0 has been published to PyPI with a library-first API.
Update this project to use direct library imports instead of subprocess calls.

Current state: All tool files in src/maid_runner_mcp/tools/ use subprocess.run
to call maid CLI commands (validate, snapshot, manifests, files, init).

What to change:

1. Update pyproject.toml: change maid-runner dependency to >=2.0.0

2. Replace subprocess calls in each tool file:

   tools/validate.py:
     Before: subprocess.run(["maid", "validate", ...], capture_output=True, text=True)
     After:
       from maid_runner import validate, validate_all, ValidationMode
       result = validate(manifest_path, mode=ValidationMode.IMPLEMENTATION, use_chain=True)
       return result.to_dict()  # MCP tools return JSON-serializable dicts

   tools/snapshot.py:
     Before: subprocess.run(["maid", "snapshot", file_path, ...])
     After:
       from maid_runner import generate_snapshot, save_manifest
       manifest = generate_snapshot(file_path)
       path = save_manifest(manifest, output_dir=output_dir)

   tools/manifests.py:
     Before: subprocess.run(["maid", "manifests", file_path, "--json-output", ...])
     After:
       from maid_runner import ManifestChain
       chain = ManifestChain(manifest_dir)
       manifests = chain.manifests_for_file(file_path)
       return [{"slug": m.slug, "goal": m.goal, "path": m.source_path} for m in manifests]

   tools/files.py:
     Before: subprocess.run(["maid", "files", ...])
     After:
       from maid_runner import ValidationEngine, ManifestChain
       chain = ManifestChain(manifest_dir)
       engine = ValidationEngine(project_root=cwd)
       report = engine.run_file_tracking(chain)
       return {"undeclared": [...], "registered": [...], "tracked": [...]}

   tools/init.py:
     Keep as subprocess — maid init is interactive/file-generating, harder to
     convert to library calls. This one can stay as subprocess.

3. Since MCP tools run in an async event loop, wrap synchronous maid-runner
   calls with asyncio.get_event_loop().run_in_executor():
     result = await asyncio.get_event_loop().run_in_executor(
         None, lambda: validate(manifest_path, ...)
     )

4. Update tests to assert against library return types instead of mocking
   subprocess.

5. The prompt templates (prompts/*.py) reference CLI commands like
   `maid validate`. These are USER-FACING instructions (telling AI agents
   what CLI to run), so they should KEEP the CLI command references.
   Only change the TOOL implementations.

6. Run the existing test suite to verify nothing breaks.
```

## maid-agents

```
maid-runner v2.0.0 has been published to PyPI with a library-first API.
Update this project to use direct library imports where appropriate.

Current state:
- maid_agents/core/validation_runner.py: subprocess.run for maid validate/test
- maid_agents/agents/manifest_architect.py: subprocess.run for maid validate
- maid_agents/core/orchestrator.py: subprocess.run for maid validate

What to change:

1. Update pyproject.toml: change maid-runner dependency to >=2.0.0

2. Replace validation_runner.py subprocess calls:

   Before:
     result = subprocess.run(command, capture_output=True, text=True, timeout=...)
     # Parse stdout for pass/fail

   After:
     from maid_runner import validate, validate_all, ValidationMode
     result = validate(manifest_path, mode=ValidationMode.IMPLEMENTATION, use_chain=True)
     # Use result.success, result.errors directly — no stdout parsing

3. Replace manifest_architect.py validation call:

   Before:
     result = subprocess.run(["maid", "validate", manifest_path, ...])

   After:
     from maid_runner import validate
     result = validate(manifest_path, use_chain=True)

4. Keep the Claude CLI wrapper (claude/cli_wrapper.py) as subprocess —
   that wraps Claude Code CLI, not maid-runner.

5. Keep orchestrator.py subprocess calls for `maid test` (running actual
   test commands) as subprocess — those execute pytest/vitest, not
   maid-runner library code.

6. Update tests. The validation_runner tests likely mock subprocess.run —
   update to mock or directly call the maid_runner library.

7. Run the existing test suite to verify nothing breaks.
```
