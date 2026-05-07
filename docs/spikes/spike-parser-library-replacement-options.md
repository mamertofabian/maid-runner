# Parser Library Replacement Options

Date: 2026-05-06

## Context

MAID Runner currently validates source code by extracting MAID artifacts,
references, imports, test functions, and limited re-export identity from Python,
TypeScript, JavaScript, TSX, JSX, and Svelte files.

The project already uses mature parsing primitives in places:

- Python uses the standard library `ast` module.
- TypeScript/JavaScript uses `tree-sitter` with `tree-sitter-typescript`.
- Svelte uses `tree-sitter-svelte` to identify real `<script>` blocks and
  delegates the extracted script bodies to the TypeScript validator.

The custom logic is not just syntax parsing. It maps language constructs into
MAID-specific `FoundArtifact` records, preserving module identity, import source,
aliases, signatures, stub status, and test references.

## Candidate Libraries

| Area | Current Manual Code | Candidate Libraries | Assessment |
| --- | --- | --- | --- |
| Python import graph | `maid_runner/core/module_paths.py`, behavioral import tracking in `maid_runner/validators/python.py` | `grimp`, `import-linter`, `pydeps` | Strong candidates for package/module dependency graph behavior. Less useful for artifact-level MAID extraction. |
| Python semantic AST | Custom `ast.NodeVisitor` collectors in `maid_runner/validators/python.py` | `astroid`, `libcst`, `jedi`, `rope` | `astroid` can add inference. `libcst` is useful if exact source preservation matters. Stdlib `ast` remains reasonable for current artifact extraction. |
| TypeScript symbols/imports | Custom tree-sitter walking in `maid_runner/validators/typescript.py`; regex re-export parsing in `maid_runner/core/ts_module_paths.py` | `typescript` compiler API, `ts-morph`, `@typescript-eslint/typescript-estree` | Highest-value replacement area. Compiler-backed tooling can resolve exports, aliases, symbols, signatures, and `tsconfig` paths more reliably than tree-sitter-only traversal. |
| JavaScript/TypeScript dependency graph | Custom module path and import resolution | `dependency-cruiser`, `madge`, `eslint-plugin-import` | Good candidates for file/module dependency graph extraction. Less aligned with MAID artifact signatures. |
| Svelte parsing | `tree-sitter-svelte` script block extraction in `maid_runner/validators/svelte.py` | `svelte/compiler`, `tree-sitter-svelte` | First replacement slice completed with existing Python dependency stack. Keep using parser-backed script discovery unless a later manifest needs deeper Svelte semantics. |
| Graph algorithms | Custom traversal and cycle detection in `maid_runner/graph/query.py` | `networkx`, `rustworkx` | Could reduce hand-rolled graph logic if the graph module grows. Not urgent for parser replacement. |
| Natural query parsing | Regex query parser in `maid_runner/graph/query.py` | `lark`, `pyparsing` | Current logic is small. Replace only if the query language becomes a real grammar. |

Registry metadata checked on 2026-05-06:

- PyPI: `grimp 3.14`, `import-linter 2.11`, `pydeps 3.0.6`,
  `astroid 4.1.2`, `jedi 0.20.0`, `rope 1.14.0`, `libcst 1.8.6`,
  `redbaron 0.9.2`, `parso 0.8.7`, `tree-sitter-languages 1.10.2`,
  `networkx 3.6.1`, `rustworkx 0.17.1`, `lark 1.3.1`, `pyparsing 3.3.2`.
- npm: `typescript 6.0.3`, `ts-morph 28.0.0`,
  `@typescript-eslint/typescript-estree 8.59.2`,
  `dependency-cruiser 17.4.0`, `madge 8.0.0`,
  `eslint-plugin-import 2.32.0`, `svelte 5.55.5`,
  `tree-sitter-svelte 0.11.0`, `tree-sitter-typescript 0.23.2`.

## Recommended Migration Shape

Do not replace the MAID validator policy layer. Preserve the current public
validator interface:

- `collect_implementation_artifacts`
- `collect_behavioral_artifacts`
- `get_test_function_bodies`
- `module_path`
- `resolve_reexport`

The safer migration is to replace language-analysis internals behind that
interface, one language slice at a time.

Recommended order:

1. Svelte script extraction: completed on 2026-05-06 with
   `tree-sitter-svelte` behind the existing `SvelteValidator` interface.
2. TypeScript re-export identity: completed on 2026-05-06 for one-level
   named barrel re-exports with parser-backed `tree-sitter-typescript`
   scanning behind `resolve_reexport`.
3. TypeScript artifact extraction edge cases: completed on 2026-05-06 for
   abstract method signatures, constructor parameter properties, and richer
   parameter signatures while preserving the existing `TypeScriptValidator`
   interface.
4. TypeScript import identity expansion: completed on 2026-05-06 for one-level
   star/default-as barrel re-exports, tsconfig `baseUrl`/`paths` aliases, and
   package-import boundary characterization. Follow-up slices added
   `index.mjs`/`index.cjs` barrel identity and local tsconfig `extends`
   inheritance.
5. Python import graph: consider `grimp` only if package-level dependency
   queries become more important than file-local artifact extraction.

## Replacement Rule

Any replacement must be behavior-preserving against the existing validator
contract. The target is not "more complete parsing" in the abstract; it is the
same MAID-visible artifacts and references unless a manifest explicitly evolves
the contract.

## Implemented Slice: Svelte Script Extraction

Implementation date: 2026-05-06

Manifest:
`manifests/replace-svelte-regex-script-extraction.manifest.yaml`

The Svelte validator now parses `.svelte` source with `tree-sitter-svelte`,
walks `script_element` nodes, extracts their `raw_text` children in document
order, and continues to delegate the combined script text to
`TypeScriptValidator`. The public validator interface remains unchanged:

- `collect_implementation_artifacts`
- `collect_behavioral_artifacts`
- `get_test_function_bodies`
- `module_path`
- `resolve_reexport`

Added coverage locks down the parser-backed behavior for:

- commented-out `<script>` tags being ignored;
- quoted `>` characters inside script tag attributes;
- module-context plus instance scripts being combined in document order;
- delegated test body extraction ignoring commented-out scripts.

Verification run after implementation:

```bash
maid validate manifests/replace-svelte-regex-script-extraction.manifest.yaml --mode behavioral
maid validate manifests/replace-svelte-regex-script-extraction.manifest.yaml --mode implementation
uv run python -m pytest -q tests/validators/test_svelte.py tests/validators/test_typescript.py tests/core/test_ts_module_paths.py
uv run python -m pytest -q
uv run black --check maid_runner/validators/svelte.py tests/validators/test_svelte.py
uv run ruff check maid_runner/validators/svelte.py tests/validators/test_svelte.py
```

Results:

- MAID behavioral validation passed.
- MAID implementation validation passed.
- 96 focused Svelte/TypeScript/module-path tests passed.
- 1224 full-suite tests passed, 6 skipped.
- Black and Ruff checks passed on touched Python files.
- Inline Svelte smoke validation passed with commented script content,
  module-context script content, instance TypeScript script content, quoted
  `>` attributes, and Svelte markup in the same source string.

## Implemented Slice: TypeScript Re-export Identity Scanner

Implementation date: 2026-05-06

Manifest:
`manifests/replace-typescript-reexport-identity-scanner.manifest.yaml`

The TypeScript module path helper now resolves one-level named barrel
re-exports by parsing supported `index` files with `tree-sitter-typescript`
instead of stripping comments and applying a regex. Parser imports are lazy
inside `resolve_ts_reexport`, so the base `maid_runner.core.ts_module_paths`
module remains importable without optional TypeScript dependencies.

The public validator interface remains unchanged:

- `module_path`
- `resolve_reexport`

Added coverage locks down parser-backed behavior for:

- `export type { Foo } from "./types"` resolving to the defining module;
- `export { type Foo } from "./types"` resolving to the defining module;
- supported JavaScript-family `index.js` barrel files resolving named
  re-exports with extensionless module identity;
- `export * from "./module"` remaining unresolved until a future manifest
  explicitly evolves that behavior.

Intentionally still out of scope:

- `export *` and `export * as ns`;
- `tsconfig` path aliases;
- `package.json` exports;
- full TypeScript compiler or `ts-morph` subprocess integration;
- TypeScript artifact extraction.

Verification run after implementation:

```bash
maid validate manifests/replace-typescript-reexport-identity-scanner.manifest.yaml --mode behavioral
maid validate manifests/replace-typescript-reexport-identity-scanner.manifest.yaml --mode implementation
uv run python -m pytest -q tests/core/test_ts_module_paths.py tests/validators/test_typescript_identity.py
uv run black --check maid_runner/core/ts_module_paths.py tests/core/test_ts_module_paths.py
uv run ruff check maid_runner/core/ts_module_paths.py tests/core/test_ts_module_paths.py
maid validate
maid test
```

Results:

- MAID behavioral validation passed.
- MAID implementation validation passed.
- 39 focused TypeScript module-path and identity tests passed.
- Black and Ruff checks passed on touched Python files.
- Full MAID validation passed with 92 manifests: 54 passed, 0 failed,
  38 skipped as superseded.
- Full MAID test gate passed with 5 commands passed and 0 failed.
- Inline smoke validation passed against a temporary TypeScript project using
  type-only named re-exports, an aliased type re-export, an unresolved star
  export, an `index.js` barrel, and `TypeScriptValidator` identity matching.

## Implemented Slice: TypeScript Artifact Extraction Edge Cases

Implementation date: 2026-05-06

Manifest:
`manifests/close-typescript-artifact-extraction-gaps.manifest.yaml`

The TypeScript implementation collector now preserves additional MAID-visible
artifact and signature behavior behind the existing `TypeScriptValidator`
interface. This is still a targeted tree-sitter-backed closure, not a
TypeScript compiler or `ts-morph` migration.

Added coverage locks down behavior for:

- abstract class method signatures being collected as method artifacts;
- public and readonly constructor parameter properties becoming class
  attributes;
- private and protected constructor parameter properties staying out of the
  public artifact set;
- defaulted, optional, rest, and destructured parameters being preserved in
  `ArgSpec` metadata.

Intentionally still out of scope:

- replacing the full TypeScript validator with `ts-morph` or a TypeScript
  compiler API subprocess;
- changing import/re-export identity behavior;
- `tsconfig` path aliases, package exports, recursive barrel resolution, and
  star exports;
- broader source location parity work.

Verification run after implementation:

```bash
maid validate manifests/close-typescript-artifact-extraction-gaps.manifest.yaml --mode behavioral
maid validate manifests/close-typescript-artifact-extraction-gaps.manifest.yaml --mode implementation
uv run python -m pytest -q tests/validators/test_typescript_artifact_edge_cases.py tests/validators/test_typescript.py tests/validators/test_typescript_identity.py
uv run black --check maid_runner/validators/typescript.py tests/validators/test_typescript_artifact_edge_cases.py
uv run ruff check maid_runner/validators/typescript.py tests/validators/test_typescript_artifact_edge_cases.py
maid validate
maid test
maid test --manifest manifests/close-typescript-artifact-extraction-gaps.manifest.yaml
```

Results:

- MAID behavioral validation passed.
- MAID implementation validation passed.
- 75 focused TypeScript artifact and identity tests passed.
- Black and Ruff checks passed on touched Python files.
- Full MAID validation passed with 93 manifests: 55 passed, 0 failed,
  38 skipped as superseded.
- Full MAID test gate passed with 5 commands passed and 0 failed.
- Manifest-specific MAID test gate passed with 1 command passed and 0 failed.
- Inline smoke validation passed against a realistic TypeScript source string
  using an abstract class, constructor parameter properties, private/protected
  constructor parameters, destructuring, a default parameter, an optional
  parameter, and a rest parameter.

## Implemented Slice: TypeScript Artifact Extraction Edge Cases 2

Implementation date: 2026-05-06

Manifest:
`manifests/close-typescript-artifact-extraction-gaps-2.manifest.yaml`

The TypeScript implementation collector now closes a second batch of
MAID-visible artifact extraction gaps behind the existing
`TypeScriptValidator` interface. This remains a targeted tree-sitter-backed
collector improvement, not a `ts-morph` or TypeScript compiler API migration.

Added coverage locks down behavior for:

- overload signatures being collected in source order alongside the
  implementation declaration;
- decorated classes and methods remaining visible as public artifacts;
- anonymous default function exports being collected as a `default` function
  artifact;
- anonymous default class exports being collected as a `default` class artifact
  with methods attached to `default`;
- generic `extends` and `implements` base types preserving type arguments;
- computed class method names being collected from stable source text such as
  `[Symbol.iterator]`.

Intentionally still out of scope:

- replacing the full TypeScript validator with `ts-morph` or a TypeScript
  compiler API subprocess;
- changing import/re-export identity behavior;
- recursive barrel traversal, package exports, and workspace package
  resolution;
- source column parity and richer source ranges beyond the existing line
  metadata.

Verification run after implementation:

```bash
maid validate manifests/close-typescript-artifact-extraction-gaps-2.manifest.yaml --mode behavioral
maid validate manifests/close-typescript-artifact-extraction-gaps-2.manifest.yaml --mode implementation
uv run python -m pytest -q tests/validators/test_typescript_artifact_edge_cases.py tests/validators/test_typescript.py tests/validators/test_typescript_identity.py
uv run black --check maid_runner/validators/typescript.py tests/validators/test_typescript_artifact_edge_cases.py
uv run ruff check maid_runner/validators/typescript.py tests/validators/test_typescript_artifact_edge_cases.py
```

Results:

- MAID behavioral validation passed.
- MAID implementation validation passed.
- 91 focused TypeScript artifact and identity tests passed.
- Black and Ruff checks passed on touched Python files.

## Implemented Slice: TypeScript Star and Default-as Barrel Identity

Implementation date: 2026-05-06

Manifest:
`manifests/extend-typescript-barrel-reexport-identity.manifest.yaml`

The TypeScript re-export resolver now handles two additional one-level barrel
forms behind the existing `resolve_reexport` interface:

- `export * from "./module"` maps the requested artifact name to the source
  module with the same MAID-visible name;
- `export { default as Button } from "./Button"` maps the visible name
  `Button` to the source module with `Button` as the MAID-visible artifact
  name.

The resolver remains intentionally path-based and does not inspect target
modules to prove star-export membership.

Verification run after implementation:

```bash
maid validate manifests/extend-typescript-barrel-reexport-identity.manifest.yaml --mode behavioral
maid validate manifests/extend-typescript-barrel-reexport-identity.manifest.yaml --mode implementation
uv run python -m pytest -q tests/core/test_ts_module_paths.py tests/validators/test_typescript_identity.py
uv run black --check maid_runner/core/ts_module_paths.py tests/core/test_ts_module_paths.py tests/validators/test_typescript_identity.py
uv run ruff check maid_runner/core/ts_module_paths.py tests/core/test_ts_module_paths.py tests/validators/test_typescript_identity.py
maid validate
maid test
maid test --manifest manifests/extend-typescript-barrel-reexport-identity.manifest.yaml
```

Results:

- MAID behavioral validation passed.
- MAID implementation validation passed.
- 42 focused TypeScript module-path and identity tests passed.
- Black and Ruff checks passed on touched Python files.
- Full MAID validation passed with 94 manifests: 56 passed, 0 failed,
  38 skipped as superseded.
- Full MAID test gate passed with 5 commands passed and 0 failed.
- Inline smoke validation passed for star and default-as barrel matching.

## Implemented Slice: TypeScript tsconfig Alias Identity

Implementation date: 2026-05-06

Manifest:
`manifests/add-typescript-tsconfig-path-alias-identity.manifest.yaml`

The TypeScript import identity helper now resolves local `tsconfig.json`
`compilerOptions.baseUrl` and simple `compilerOptions.paths` entries to
extensionless MAID module identities. `TypeScriptValidator` behavioral import
collection uses this helper, discovering the nearest parent `tsconfig.json`
when an absolute file path is supplied.

Added coverage locks down behavior for:

- wildcard paths aliases such as `@/* -> src/*`;
- `baseUrl` resolving non-relative project imports;
- paths aliases pointing to directory barrels;
- unmatched aliases passing through unchanged;
- tsconfig aliases feeding existing barrel re-export matching.

Intentionally still out of scope:

- TypeScript compiler module resolution;
- `extends` chains in tsconfig files;
- `package.json` exports and `node_modules` resolution;
- changing TypeScript artifact extraction or barrel scanning.

Verification run after implementation:

```bash
maid validate manifests/add-typescript-tsconfig-path-alias-identity.manifest.yaml --mode behavioral
maid validate manifests/add-typescript-tsconfig-path-alias-identity.manifest.yaml --mode implementation
uv run python -m pytest -q tests/core/test_ts_module_paths.py tests/validators/test_typescript_identity.py
uv run black --check maid_runner/core/ts_module_paths.py maid_runner/validators/typescript.py tests/core/test_ts_module_paths.py tests/validators/test_typescript_identity.py
uv run ruff check maid_runner/core/ts_module_paths.py maid_runner/validators/typescript.py tests/core/test_ts_module_paths.py tests/validators/test_typescript_identity.py
maid validate
maid test
maid test --manifest manifests/add-typescript-tsconfig-path-alias-identity.manifest.yaml
```

Results:

- MAID behavioral validation passed.
- MAID implementation validation passed.
- 48 focused TypeScript module-path and identity tests passed.
- Black and Ruff checks passed on touched Python files.
- Full MAID validation passed with 95 manifests: 57 passed, 0 failed,
  38 skipped as superseded.
- Full MAID test gate passed with 5 commands passed and 0 failed.
- Inline smoke validation passed for alias-to-file and alias-to-barrel matching.

## Characterized Slice: TypeScript Package Import Boundary

Characterization date: 2026-05-06

Manifest:
`manifests/characterize-typescript-package-import-identity.manifest.yaml`

Package imports are intentionally characterized as pass-through identity. This
locks the boundary before any future package/export resolver work:

- bare package imports such as `react` remain `react`;
- scoped package imports such as `@testing-library/react` remain unchanged;
- `package.json` `exports` inside `node_modules` are not resolved;
- behavioral imports record the package specifier as `import_source`.

This prevents tsconfig alias resolution or future baseUrl work from silently
rewriting package names into local module identities.

Verification run after characterization:

```bash
maid validate manifests/characterize-typescript-package-import-identity.manifest.yaml --mode behavioral
maid validate manifests/characterize-typescript-package-import-identity.manifest.yaml --mode implementation
uv run python -m pytest -q tests/core/test_ts_module_paths.py tests/validators/test_typescript_identity.py
```

Results:

- MAID behavioral validation passed.
- MAID implementation validation passed.
- 52 focused TypeScript module-path and identity tests passed.

## Characterized Slice: TypeScript Workspace Package Boundary

Characterization date: 2026-05-06

Manifest:
`manifests/characterize-typescript-workspace-package-boundary.manifest.yaml`

Workspace package imports are intentionally characterized as pass-through
identity. Even when the project has root `package.json` workspaces and a local
workspace package with `package.json` `exports`, MAID does not resolve package
subpaths such as `@scope/ui/Button` to `packages/ui/src/Button`.

Added coverage locks down behavior for:

- workspace package `exports` not resolving through local `packages/*`
  metadata;
- behavioral imports recording the workspace package subpath as
  `import_source`.

Verification run after characterization:

```bash
maid validate manifests/characterize-typescript-workspace-package-boundary.manifest.yaml --mode behavioral
maid validate manifests/characterize-typescript-workspace-package-boundary.manifest.yaml --mode implementation
uv run python -m pytest -q tests/core/test_ts_module_paths.py tests/validators/test_typescript_identity.py
uv run black --check tests/core/test_ts_module_paths.py tests/validators/test_typescript_identity.py
uv run ruff check tests/core/test_ts_module_paths.py tests/validators/test_typescript_identity.py
```

Results:

- MAID behavioral validation passed.
- MAID implementation validation passed.
- 68 focused TypeScript module-path and identity tests passed.
- Black and Ruff checks passed on touched Python files.

This characterization was superseded by
`manifests/add-typescript-compiler-backed-identity-resolution.manifest.yaml`,
which intentionally resolves workspace package exports when the target
project's TypeScript compiler is available.

## Implemented Slice: TS/JS Required Import Scanner

Implementation date: 2026-05-06

Manifest:
`manifests/replace-ts-required-import-regex-scanner.manifest.yaml`

The implementation-mode required import check now discovers TypeScript and
JavaScript imports with parser-backed tree-sitter traversal when optional
TypeScript parser dependencies are available. The Python import branch remains
stdlib-`ast` backed, and the TS/JS branch keeps a conservative text fallback
for environments without tree-sitter.

Added coverage locks down behavior for:

- `import type` required imports;
- dynamic `import("./module")`;
- `require.resolve("./module")`;
- multiline named imports;
- named import aliases;
- commented-out import text not satisfying E320.

Intentionally still out of scope:

- TypeScript compiler module resolution;
- package exports, workspace packages, and `node_modules` lookup;
- tsconfig alias handling inside required-import checks;
- changing validator artifact extraction or identity matching.

Verification run after implementation:

```bash
maid validate manifests/replace-ts-required-import-regex-scanner.manifest.yaml --mode behavioral
maid validate manifests/replace-ts-required-import-regex-scanner.manifest.yaml --mode implementation
uv run python -m pytest -q tests/core/test_validate.py::TestImportVerification
uv run black --check maid_runner/core/validate.py tests/core/test_validate.py
uv run ruff check maid_runner/core/validate.py tests/core/test_validate.py
maid validate
maid test --manifest manifests/replace-ts-required-import-regex-scanner.manifest.yaml
maid test
```

Results:

- MAID behavioral validation passed.
- MAID implementation validation passed.
- 23 focused import-verification tests passed.
- Black and Ruff checks passed on touched Python files.
- Full MAID validation passed.
- Manifest-specific and full MAID test gates passed.

## Characterized Slice: TypeScript Namespace Re-export Boundary

Characterization date: 2026-05-06

Manifest:
`manifests/characterize-typescript-namespace-reexport-identity.manifest.yaml`

Namespace star re-exports are now characterized as distinct from direct star
barrel re-exports:

- `export * as Icons from "./icons"` does not resolve member name `Camera`;
- `export * as Icons from "./icons"` does not resolve namespace binding
  `Icons` through `resolve_ts_reexport`;
- a direct named import from the barrel does not match the final source
  artifact through a namespace re-export.

This locks the current boundary before any future resolver work that might
handle namespace-object member matching such as `Icons.Camera`.

Verification run after characterization:

```bash
maid validate manifests/characterize-typescript-namespace-reexport-identity.manifest.yaml --mode behavioral
maid validate manifests/characterize-typescript-namespace-reexport-identity.manifest.yaml --mode implementation
uv run python -m pytest -q tests/core/test_ts_module_paths.py tests/validators/test_typescript_identity.py
maid test --manifest manifests/characterize-typescript-namespace-reexport-identity.manifest.yaml
maid validate
maid test
```

Results:

- MAID behavioral validation passed.
- MAID implementation validation passed.
- Focused TypeScript module-path and identity tests passed.
- Manifest-specific and full MAID test gates passed.

## Characterized Slice: TypeScript Recursive Barrel Boundary

Characterization date: 2026-05-06

Manifest:
`manifests/characterize-typescript-recursive-barrel-identity.manifest.yaml`

Recursive barrel resolution is now characterized as unsupported by the current
one-level resolver. For a chain such as:

```text
src/components/index.ts -> export { Button } from "./nested"
src/components/nested/index.ts -> export { Button } from "./Button"
```

The resolver may expose the immediate target `src/components/nested`, but it
does not walk the second barrel to claim coverage for
`src/components/nested/Button`.

Added coverage locks down behavior for:

- recursive barrel re-exports resolving only to the immediate module;
- identity matching rejecting the final artifact when the test imports through
  the top-level barrel.

Verification run after characterization:

```bash
maid validate manifests/characterize-typescript-recursive-barrel-identity.manifest.yaml --mode behavioral
maid validate manifests/characterize-typescript-recursive-barrel-identity.manifest.yaml --mode implementation
uv run python -m pytest -q tests/core/test_ts_module_paths.py tests/validators/test_typescript_identity.py
maid test --manifest manifests/characterize-typescript-recursive-barrel-identity.manifest.yaml
maid validate
maid test
```

Results:

- MAID behavioral validation passed.
- MAID implementation validation passed.
- 57 focused TypeScript module-path and identity tests passed.
- Manifest-specific and full MAID test gates passed.

This characterization was superseded by
`manifests/add-typescript-compiler-backed-identity-resolution.manifest.yaml`,
which intentionally resolves recursive barrels through the target project's
TypeScript compiler when available.

## Implemented Slice: TypeScript MJS/CJS Barrel Identity

Implementation date: 2026-05-06

Manifest:
`manifests/add-typescript-mjs-cjs-barrel-identity.manifest.yaml`

The TypeScript module identity helper now treats `.mjs` and `.cjs` as
TypeScript-family source extensions for MAID identity. The one-level
re-export resolver also recognizes `index.mjs` ESM barrels and a narrow
CommonJS `index.cjs` named-export assignment form:

```js
exports.Foo = require("./user.cjs").Foo;
```

Added coverage locks down behavior for:

- stripping `.mjs` and `.cjs` from module identities;
- stripping `.mjs` from relative import specifiers;
- resolving one-level `index.mjs` ESM re-exports;
- resolving narrow `index.cjs` `exports.Name = require(...).Name` barrels;
- matching validator references through an `index.mjs` barrel.

Verification run after implementation:

```bash
maid validate manifests/add-typescript-mjs-cjs-barrel-identity.manifest.yaml --mode behavioral
maid validate manifests/add-typescript-mjs-cjs-barrel-identity.manifest.yaml --mode implementation
uv run python -m pytest -q tests/core/test_ts_module_paths.py tests/validators/test_typescript_identity.py
uv run black --check maid_runner/core/ts_module_paths.py tests/core/test_ts_module_paths.py tests/validators/test_typescript_identity.py
uv run ruff check maid_runner/core/ts_module_paths.py tests/core/test_ts_module_paths.py tests/validators/test_typescript_identity.py
maid validate
maid test --manifest manifests/add-typescript-mjs-cjs-barrel-identity.manifest.yaml
maid test
```

Results:

- MAID behavioral validation passed.
- MAID implementation validation passed.
- 62 focused TypeScript module-path and identity tests passed.
- Black and Ruff checks passed on touched Python files.
- Full MAID validation passed with 100 manifests: 62 passed, 0 failed,
  38 skipped as superseded.
- Manifest-specific and full MAID test gates passed.

## Implemented Slice: TypeScript tsconfig Extends Identity

Implementation date: 2026-05-06

Manifest:
`manifests/add-typescript-tsconfig-extends-identity.manifest.yaml`

The TypeScript import identity helper now follows local filesystem
`tsconfig.json` `extends` chains when resolving `compilerOptions.baseUrl` and
`compilerOptions.paths`. Inherited compiler options are merged before child
options, relative `baseUrl` values are interpreted against the config file that
declared them, and package-style `extends` specifiers remain unresolved.

Added coverage locks down behavior for:

- inherited `paths` aliases from a local `tsconfig.base.json`;
- inherited `baseUrl` from a local `tsconfig.base.json`;
- package-style `extends` not resolving through `node_modules`;
- `TypeScriptValidator.collect_behavioral_artifacts` recording import sources
  through an inherited alias.

Verification run after implementation:

```bash
maid validate manifests/add-typescript-tsconfig-extends-identity.manifest.yaml --mode behavioral
maid validate manifests/add-typescript-tsconfig-extends-identity.manifest.yaml --mode implementation
uv run python -m pytest -q tests/core/test_ts_module_paths.py tests/validators/test_typescript_identity.py
uv run black --check maid_runner/core/ts_module_paths.py tests/core/test_ts_module_paths.py tests/validators/test_typescript_identity.py
uv run ruff check maid_runner/core/ts_module_paths.py tests/core/test_ts_module_paths.py tests/validators/test_typescript_identity.py
maid validate
maid test --manifest manifests/add-typescript-tsconfig-extends-identity.manifest.yaml
maid test
```

Results:

- MAID behavioral validation passed.
- MAID implementation validation passed.
- 66 focused TypeScript module-path and identity tests passed.
- Black and Ruff checks passed on touched Python files.
- Full MAID validation passed with 101 manifests: 63 passed, 0 failed,
  38 skipped as superseded.
- Manifest-specific and full MAID test gates passed.

## Implemented Slice: Compiler-backed TypeScript Identity Resolution

Implementation date: 2026-05-06

Manifest:
`manifests/add-typescript-compiler-backed-identity-resolution.manifest.yaml`

TypeScript import and re-export identity resolution now has an opportunistic
compiler-backed path. `resolve_ts_import` and `resolve_ts_reexport` first ask a
small Node bridge to load the target project's installed `typescript` package
and resolve through the TypeScript compiler API. If Node, TypeScript, compiler
configuration, or the bridge request is unavailable, MAID falls back to the
existing path/tree-sitter implementation.

Added coverage locks down behavior for:

- workspace package exports resolving through a real `node_modules` workspace
  symlink to `packages/ui/src/Button`;
- behavioral imports recording the workspace source module instead of the
  package subpath when compiler resolution succeeds;
- recursive barrels resolving to the final declaring source module;
- identity matching accepting a final artifact imported through nested barrels;
- missing Node returning `None` from compiler helpers so current fallback
  behavior remains available.

Intentional boundaries remain:

- TypeScript artifact extraction is still tree-sitter-backed;
- direct third-party packages in `node_modules` remain package specifiers
  unless they realpath to source inside the target project;
- namespace star re-export object matching remains out of scope;
- package-style tsconfig `extends` behavior is delegated to the compiler only
  when the compiler can resolve the project configuration.

Verification run after implementation:

```bash
npm install --ignore-scripts
maid validate manifests/add-typescript-compiler-backed-identity-resolution.manifest.yaml --mode behavioral
maid validate manifests/add-typescript-compiler-backed-identity-resolution.manifest.yaml --mode implementation
uv run python -m pytest -q tests/core/test_ts_compiler_resolver.py tests/core/test_ts_module_paths.py tests/validators/test_typescript_identity.py
uv run black --check maid_runner/core/ts_compiler_resolver.py maid_runner/core/ts_module_paths.py tests/core/test_ts_compiler_resolver.py tests/core/test_ts_module_paths.py tests/validators/test_typescript_identity.py
uv run ruff check maid_runner/core/ts_compiler_resolver.py maid_runner/core/ts_module_paths.py tests/core/test_ts_compiler_resolver.py tests/core/test_ts_module_paths.py tests/validators/test_typescript_identity.py
maid validate
maid test --manifest manifests/add-typescript-compiler-backed-identity-resolution.manifest.yaml
maid test
```

Results:

- MAID behavioral validation passed.
- MAID implementation validation passed.
- 72 focused compiler, module-path, and identity tests passed.
- Black and Ruff checks passed on touched Python files.
- Full MAID validation passed with 104 manifests: 64 passed, 0 failed,
  40 skipped as superseded.
- Manifest-specific and full MAID test gates passed.

## Implemented Slice: TypeScript Type Alias Target Extraction

Implementation date: 2026-05-07

Manifest:
`manifests/add-typescript-type-alias-target-extraction.manifest.yaml`

The TypeScript implementation collector now preserves the declared target text
for `type` aliases in the existing `FoundArtifact.type_annotation` field. This
keeps the public `TypeScriptValidator.collect_implementation_artifacts`
interface unchanged while making `ArtifactKind.TYPE` records carry the same
MAID-visible `type` metadata that downstream serialization already knows how
to represent.

Added coverage locks down behavior for:

- primitive alias targets such as `type UserId = string`;
- complex source-faithful alias targets such as
  `Readonly<Record<string, User | null>>`.

Intentional boundaries remain:

- TypeScript artifact extraction is still tree-sitter-backed;
- no TypeScript type inference or normalization is performed;
- import identity, re-export identity, behavioral collection, and barrel
  behavior are unchanged.

Verification run after implementation:

```bash
maid validate manifests/add-typescript-type-alias-target-extraction.manifest.yaml --mode behavioral
maid validate manifests/add-typescript-type-alias-target-extraction.manifest.yaml --mode implementation
uv run python -m pytest -q tests/validators/test_typescript_artifact_edge_cases.py
uv run black --check maid_runner/validators/typescript.py tests/validators/test_typescript_artifact_edge_cases.py
uv run ruff check maid_runner/validators/typescript.py tests/validators/test_typescript_artifact_edge_cases.py
maid validate
maid test --manifest manifests/add-typescript-type-alias-target-extraction.manifest.yaml
maid test
```

Results:

- MAID behavioral validation passed.
- MAID implementation validation passed.
- 12 focused TypeScript artifact edge-case tests passed.
- Black and Ruff checks passed on touched Python files.
- Full MAID validation passed with 105 manifests: 65 passed, 0 failed,
  40 skipped as superseded.
- Manifest-specific and full MAID test gates passed.

## Implemented Slice: TypeScript Computed Property Artifact Extraction

Implementation date: 2026-05-07

Manifest:
`manifests/add-typescript-computed-property-artifact-extraction.manifest.yaml`

The TypeScript implementation collector now preserves computed property names
for class fields, class arrow-function fields, and interface members. Computed
class method definitions were already collected from source text; this slice
extends the same source-faithful name behavior to related property forms while
keeping `TypeScriptValidator.collect_implementation_artifacts` unchanged.

Added coverage locks down behavior for:

- computed class fields such as `[TOKEN]: string` being collected as
  `ArtifactKind.ATTRIBUTE` with type metadata;
- computed class arrow-function fields such as `[Symbol.iterator] = () => ...`
  being collected as `ArtifactKind.METHOD`;
- computed interface properties and method signatures being collected with
  exact bracketed source names.

Intentional boundaries remain:

- TypeScript artifact extraction is still tree-sitter-backed;
- computed names are preserved from source text rather than normalized;
- private and protected computed class fields remain excluded by the existing
  accessibility filter;
- import identity, re-export identity, behavioral collection, and barrel
  behavior are unchanged.

Verification run after implementation:

```bash
maid validate manifests/add-typescript-computed-property-artifact-extraction.manifest.yaml --mode behavioral
maid validate manifests/add-typescript-computed-property-artifact-extraction.manifest.yaml --mode implementation
uv run python -m pytest -q tests/validators/test_typescript_artifact_edge_cases.py
uv run black --check maid_runner/validators/typescript.py tests/validators/test_typescript_artifact_edge_cases.py
uv run ruff check maid_runner/validators/typescript.py tests/validators/test_typescript_artifact_edge_cases.py
maid validate
maid test --manifest manifests/add-typescript-computed-property-artifact-extraction.manifest.yaml
maid test
```

Results:

- MAID behavioral validation passed.
- MAID implementation validation passed.
- 15 focused TypeScript artifact edge-case tests passed.
- Black and Ruff checks passed on touched Python files.
- Full MAID validation passed with 106 manifests: 66 passed, 0 failed,
  40 skipped as superseded.
- Manifest-specific and full MAID test gates passed.

## Implemented Slice: TypeScript Annotated Function Return Extraction

Implementation date: 2026-05-07

Manifest:
`manifests/add-typescript-annotated-function-return-extraction.manifest.yaml`

The TypeScript implementation collector now extracts trailing return type text
from annotated function types on function-valued declarations when the runtime
function expression does not declare its own return type. This closes the
residual gap left after declaration-site generic parameter storage:

```ts
export const id: <T>(x: T) => T = (x) => x;
```

The collected `FoundArtifact` now preserves `type_parameters == ("T",)` and
records `returns == "T"` instead of treating the whole annotation
`<T>(x: T) => T` as the return type. The change remains tree-sitter-backed and
keeps `TypeScriptValidator.collect_implementation_artifacts` unchanged.

Added coverage locks down behavior for:

- module-level typed const arrow functions extracting the annotated trailing
  return type;
- parenthesized annotated function types extracting the same trailing return
  type;
- class field arrow methods extracting the annotated trailing return type;
- union and intersection annotations that contain nested function types
  preserving the full annotation instead of peeling one nested return type;
- existing declaration-site generic parameter extraction continuing to work.

Intentional boundaries remain:

- explicit return annotations on the function expression itself still take
  precedence over annotation fallback;
- only effective top-level function type annotations are peeled, with
  parentheses treated as transparent wrappers;
- no TypeScript type inference or normalization is performed;
- argument extraction, import identity, re-export identity, behavioral
  collection, and barrel behavior are unchanged.

Verification run after implementation:

```bash
maid validate manifests/add-typescript-annotated-function-return-extraction.manifest.yaml --mode behavioral
maid validate manifests/add-typescript-annotated-function-return-extraction.manifest.yaml --mode implementation
uv run python -m pytest -q tests/validators/test_typescript_artifact_edge_cases.py
uv run black --check maid_runner/validators/typescript.py tests/validators/test_typescript_artifact_edge_cases.py
uv run ruff check maid_runner/validators/typescript.py tests/validators/test_typescript_artifact_edge_cases.py
maid validate
maid test --manifest manifests/add-typescript-annotated-function-return-extraction.manifest.yaml
maid test
```

Results:

- MAID behavioral validation passed.
- MAID implementation validation passed with one expected markdown-validator
  warning for the spike doc.
- 24 focused TypeScript artifact edge-case tests passed.
- Black and Ruff checks passed on touched Python files.
- Full MAID validation passed with 110 manifests: 70 passed, 0 failed,
  40 skipped as superseded.
- Manifest-specific and full MAID test gates passed.

## Characterization Test Assessment

Assessment date: 2026-05-07

Focused parser/replacement characterization coverage is substantial:

- Python validator tests cover class/function/method/attribute extraction,
  signature extraction, bases, property handling, class/module attributes,
  private detection, package `__init__.py` re-exports, behavioral references,
  keyword arguments, dotted imports, tuple assignment, syntax-error handling,
  stub detection, identity fields, relative imports, alias handling, and
  attribute-chain module identity.
- TypeScript validator tests cover interfaces, classes, methods, abstract
  method signatures, overload signatures, arrow functions, class fields,
  private `#` members, constructor parameter properties,
  defaulted/optional/rest/destructured parameters, decorated declarations,
  anonymous default exports, generic base type formatting, computed class
  method names, computed class fields, computed class arrow-function fields,
  computed interface members, annotated function-type return extraction,
  object property arrow exclusion, enums, namespaces, constructors,
  getters/setters, generator functions, export statements, inheritance,
  interface members, member-expression behavioral references,
  namespace import identity, JSX/TSX references, object/JSX props,
  test-function label detection, stub detection, module path identity,
  named/star/default-as barrel re-export matching, namespace re-export
  non-equivalence, compiler-backed recursive barrel matching, `index.mjs`
  barrel identity, tsconfig alias identity, tsconfig `extends` identity,
  package import pass-through behavior, compiler-backed workspace package
  import identity, and cross-module collision rejection.
- Svelte validator tests cover parser-backed script extraction, TypeScript
  script extraction, ignored scripts inside comments, quoted `>` attributes,
  module-context plus instance script ordering, no-script behavior, behavioral
  collection, delegated test body extraction, module path identity, import
  source identity, barrel matching, and explicit `.svelte` import identity.
- Module identity tests cover Python dotted module paths, Python relative
  imports, Python one-level `__init__.py` re-exports, TypeScript extensionless
  POSIX module paths, TypeScript relative imports, TypeScript `.svelte`
  specifier normalization, one-level `index.ts(x)` re-exports, type-only
  TypeScript named re-exports, `index.js` TypeScript-family barrel re-exports,
  `index.mjs` ESM barrels, narrow `index.cjs` CommonJS export-assignment
  barrels, one-level star/default-as barrel re-exports, namespace star
  re-export non-equivalence, recursive barrel one-level boundaries, tsconfig
  `baseUrl`/`paths` aliases, local tsconfig `extends` chains, package import
  pass-through behavior, compiler-backed workspace package exports, and
  compiler-backed recursive barrel resolution.
- Validation/integration tests cover parser error surfacing, required import
  checks, JS/TS relative import normalization, CommonJS `require`, `export from`,
  namespace imports, parser-backed TS/JS required import edge cases, Svelte
  validation, test coverage behavior, and public library API expectations.

Commands run:

```bash
uv run python -m pytest --collect-only -q tests/validators tests/core/test_identity_matching.py tests/core/test_ts_module_paths.py tests/core/test_validate_test_functions.py tests/graph/test_graph_v2.py
uv run python -m pytest -q tests/validators tests/core/test_identity_matching.py tests/core/test_ts_module_paths.py tests/core/test_validate_test_functions.py tests/graph/test_graph_v2.py
uv run python -m pytest -q tests/core/test_validate.py tests/integration/test_full_workflow.py tests/integration/test_library_api.py
```

Results:

- 338 focused parser/identity/graph tests collected.
- 338 focused parser/identity/graph tests passed.
- 153 validation and integration tests passed.

Readiness by replacement slice:

| Slice | Readiness | Notes |
| --- | --- | --- |
| Svelte script extraction | Completed for current behavior | Parser-backed extraction now covers real script nodes, comments, quoted attributes, and module/instance scripts while preserving TypeScript delegation. Future work should only evolve line/column parity or deeper Svelte semantics under a new manifest. |
| TypeScript import/re-export identity | Compiler-backed for selected project-local cases | Named/default/namespace imports, aliasing, JSX references, one-level named/type/star/default-as barrels, namespace re-export non-equivalence, JavaScript-family barrels including `index.mjs` and narrow `index.cjs`, tsconfig `baseUrl`/`paths` aliases, local tsconfig `extends` chains, package import pass-through behavior, compiler-backed workspace package exports, and compiler-backed recursive barrels are covered. The compiler bridge falls back to current path/tree-sitter behavior when Node or TypeScript is unavailable. |
| TypeScript artifact extraction | Good for current tree-sitter scope | Edge-case coverage now includes abstract method signatures, constructor parameter properties, defaulted/optional/rest/destructured parameters, overload signatures, decorated declarations, anonymous default exports, generic base type formatting, declaration-site generic type parameter storage, computed class method names, computed class fields, computed class arrow-function fields, computed interface members, annotated function-type return extraction, and type alias target text. Add tests before any broader replacement for decorator metadata semantics, computed property cases outside the covered class/interface forms, and source column/range parity if the replacement reports richer positions. |
| Python validator internals | Good for current scope | Stdlib `ast` behavior is well characterized. If replacing with `astroid` or `libcst`, add tests for decorators beyond `@property`, dataclass/attrs-style fields if desired, overloaded functions, `typing.Protocol`, `__all__` re-exports, star import behavior, namespace packages, and line/column parity. |
| Required import checking in `core/validate.py` | Completed for current parser-backed scanner | Python remains stdlib-`ast` backed. TS/JS required import discovery now uses tree-sitter when available and covers relative imports, package imports, CommonJS `require`, `export from`, namespace imports, `import type`, dynamic `import()`, `require.resolve`, multiline imports, commented-out imports, and aliases. Future work should only add tsconfig/package resolution under an explicit manifest. |
| Graph/query parser replacement | Good enough, low priority | Query and graph behavior has dedicated coverage. A library replacement is not currently justified unless graph/query complexity grows. |

## Forward Implementation Queue

Status: planning notes only. These items do not change MAID validation behavior
or public validator functionality until a future manifest explicitly evolves
the contract, adds behavioral tests, and passes validation.

1. Characterize package-style `tsconfig` `extends` edge cases not already
   handled by the TypeScript compiler bridge. The current bridge delegates
   valid package-style config inheritance to the compiler when the compiler can
   resolve the project configuration.
2. Characterize package export shapes before adding code. Conditional exports,
   `types`/`import`/`require` branches, wildcard exports, and package subpath
   variants may already resolve through the compiler when they point to
   project-local source.
3. Preserve the third-party package boundary. Direct dependencies in
   `node_modules` should continue to remain package specifiers unless compiler
   resolution realpaths them to source inside the target project or workspace.
4. Continue TypeScript artifact-extraction slices separately from identity
   resolution. Prefer the smallest tree-sitter-backed closure when the current
   parser already exposes the needed source text; reserve compiler-backed
   extraction for behavior that requires TypeScript semantics.
5. For future artifact-extraction work, characterize decorator metadata
   semantics, computed property cases outside the covered class/interface
   forms, and source column/range parity.
6. Consider compiler-backed required-import resolution only under a dedicated
   manifest. The current scanner remains parser-backed and should keep its
   existing behavior until that contract is intentionally evolved.
7. Keep Python parser replacement low priority unless package-level dependency
   graph queries become more important than current file-local artifact
   extraction.
8. Keep graph/query parser replacement low priority unless the query language
   grows into a real grammar.

These items remain aligned with MAID's goal and philosophy because they improve
observable artifact/reference identity and reduce hand-rolled language
semantics while preserving manifest-driven, behavior-first change control. Each
slice should keep the public validator interface stable unless its manifest
explicitly declares an interface evolution.

Conclusion: the incremental replacement slices now cover Svelte script
extraction, TypeScript barrel identity, two TypeScript artifact extraction
edge-case batches, tsconfig alias identity, local tsconfig `extends` identity,
parser-backed TS/JS required import checking, namespace re-export boundaries,
`index.mjs`/narrow `index.cjs` barrel identity, and compiler-backed TypeScript
identity for workspace package exports and recursive barrels, and TypeScript
type alias target extraction, and TypeScript computed property artifact
extraction, TypeScript declaration-site generic type parameter storage, and
TypeScript annotated function-type return extraction behind the existing
validator interface. The next safe path is
characterization-first: identify any package-style `tsconfig` `extends` or
package export shapes that the compiler bridge does not already resolve, or
continue separate artifact-extraction slices for decorator metadata semantics,
computed property boundary cases outside the covered class/interface forms,
and source column/range parity.
