# Parser Replacement Manifest Roadmap

This file is the alignment map for parser replacement manifests derived from
`docs/spikes/spike-parser-library-replacement-options.md`. The parser
replacement track is complete for current behavior; remaining ideas are parked
notes to revisit only when a concrete project need appears.

## Canonical Sources

- Parser replacement spike:
  `docs/spikes/spike-parser-library-replacement-options.md`
- TypeScript identity helpers:
  `maid_runner/core/ts_module_paths.py`
- TypeScript compiler bridge:
  `maid_runner/core/ts_compiler_resolver.py`
- TypeScript validator:
  `maid_runner/validators/typescript.py`
- Python validator:
  `maid_runner/validators/python.py`
- Required import validation:
  `maid_runner/core/validate.py`
- Graph query parser:
  `maid_runner/graph/query.py`

## Shared Boundaries

- Preserve the public validator interface unless a child manifest explicitly
  evolves it.
- Prefer characterization-first drafts for package export, tsconfig, Python,
  and graph/query parser work.
- Keep TypeScript artifact extraction separate from import/re-export identity
  resolution.
- Keep direct third-party package imports as package specifiers unless compiler
  resolution realpaths them to project-local source.
- Treat compiler-backed resolution as an opportunistic path, not a hard runtime
  dependency.
- Avoid widening default validation latency. Compiler-backed work should be
  cached, bounded, or opt-in when the behavior can remain parser/path backed.

## Promoted Manifests

1. `017-01-characterize-package-tsconfig-extends.manifest.yaml` - characterize
   package-style `tsconfig` extends behavior without making compiler
   availability required.
2. `017-02-characterize-package-export-shapes.manifest.yaml` - characterize
   conditional, wildcard, and subpath package exports that resolve to
   project-local source.
3. `017-03-preserve-third-party-package-boundary.manifest.yaml` - keep direct
   dependencies in `node_modules` as package specifiers.
4. `017-04-typescript-decorator-metadata-boundary.manifest.yaml` - lock
   decorator behavior before any richer metadata extraction is considered.
5. `017-05-typescript-computed-and-source-location-boundaries.manifest.yaml` -
   lock computed member and source-location behavior outside the already
   implemented class/interface cases.
6. `017-06-compiler-backed-required-import-resolution.manifest.yaml` - plan any
   required-import compiler resolver behind the public `ValidationEngine`
   contract while protecting validation performance.
7. `017-07-python-parser-replacement-boundaries.manifest.yaml` - keep Python
   parser replacement low priority and characterize file-local AST behavior
   before considering `astroid`, `libcst`, or package graph tooling.
8. `017-08-graph-query-parser-replacement-boundary.manifest.yaml` - keep
   graph/query parser replacement low priority and characterize current query
   intent behavior before considering a grammar library.

## Parked Follow-ups

- Treat additional parser replacement work as demand-driven. Start a new
  manifest only when a project exposes behavior that the current validators do
  not represent well.
- Keep future TypeScript identity work separate from TypeScript artifact
  extraction work.
- Keep compiler-backed required-import resolution behind a dedicated manifest
  with explicit performance and fallback assertions.
- Keep Python parser and graph/query parser replacements low priority unless
  their current behavior becomes a real blocker.
