# Parser Replacement Draft Manifest Roadmap

This file is the alignment map for draft manifests derived from
`docs/spikes/spike-parser-library-replacement-options.md`. The spike is the
source of scope; child draft manifests are the executable planning units that
can later be refined, validated, approved, and promoted.

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

## Status Owners

- `017-01` owns package-style `tsconfig` extends characterization.
- `017-02` owns package export shape characterization for project-local source.
- `017-03` owns the third-party package boundary.
- `017-04` owns TypeScript decorator metadata boundary characterization.
- `017-05` owns TypeScript computed-member and source-location boundary
  characterization.
- `017-06` owns any compiler-backed required-import validation evolution.
- `017-07` owns Python parser replacement boundary characterization.
- `017-08` owns graph/query parser replacement boundary characterization.

## Draft Set

Epic planning drafts use these comments:

```yaml
# draft-kind: epic
# promotion: split-before-promote
```

1. `017-parser-library-followups.epic.yaml` - non-executable planning draft for
   the remaining parser replacement queue.
2. `017-01-characterize-package-tsconfig-extends.manifest.yaml` - characterize
   package-style `tsconfig` extends behavior without making compiler
   availability required.
3. `017-02-characterize-package-export-shapes.manifest.yaml` - characterize
   conditional, wildcard, and subpath package exports that resolve to
   project-local source.
4. `017-03-preserve-third-party-package-boundary.manifest.yaml` - keep direct
   dependencies in `node_modules` as package specifiers.
5. `017-04-typescript-decorator-metadata-boundary.manifest.yaml` - lock
   decorator behavior before any richer metadata extraction is considered.
6. `017-05-typescript-computed-and-source-location-boundaries.manifest.yaml` -
   lock computed member and source-location behavior outside the already
   implemented class/interface cases.
7. `017-06-compiler-backed-required-import-resolution.manifest.yaml` - plan any
   required-import compiler resolver behind the public `ValidationEngine`
   contract while protecting validation performance.
8. `017-07-python-parser-replacement-boundaries.manifest.yaml` - keep Python
   parser replacement low priority and characterize file-local AST behavior
   before considering `astroid`, `libcst`, or package graph tooling.
9. `017-08-graph-query-parser-replacement-boundary.manifest.yaml` - keep
   graph/query parser replacement low priority and characterize current query
   intent behavior before considering a grammar library.

## Promotion Notes

- Promote characterization drafts before behavior-evolving drafts that rely on
  the same boundary.
- Promote TypeScript identity drafts before required-import compiler work.
- Promote TypeScript artifact-extraction drafts independently from identity
  drafts.
- Do not promote `017-06` until the behavioral tests include a concrete
  assertion that compiler resolution is not invoked for simple relative imports
  and that missing compiler support falls back visibly through existing
  validation behavior.
