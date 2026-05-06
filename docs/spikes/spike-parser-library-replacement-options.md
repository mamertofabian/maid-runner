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

## Characterization Test Assessment

Assessment date: 2026-05-06

Focused parser/replacement characterization coverage is substantial:

- Python validator tests cover class/function/method/attribute extraction,
  signature extraction, bases, property handling, class/module attributes,
  private detection, package `__init__.py` re-exports, behavioral references,
  keyword arguments, dotted imports, tuple assignment, syntax-error handling,
  stub detection, identity fields, relative imports, alias handling, and
  attribute-chain module identity.
- TypeScript validator tests cover interfaces, classes, methods, abstract
  method signatures, arrow functions, class fields, private `#` members,
  constructor parameter properties, defaulted/optional/rest/destructured
  parameters, object property arrow exclusion, enums, namespaces, constructors,
  getters/setters, generator functions, export statements, inheritance,
  interface members, member-expression behavioral references, namespace import
  identity, JSX/TSX references, object/JSX props, test-function label detection,
  stub detection, module path identity, named/star/default-as barrel re-export
  matching, namespace re-export non-equivalence, recursive barrel boundary
  behavior, `index.mjs` barrel identity, tsconfig alias identity, tsconfig
  `extends` identity, package import pass-through behavior, and cross-module
  collision rejection.
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
  pass-through behavior, and workspace package pass-through behavior.
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
| TypeScript import/re-export identity | Good for current path-based scope | Named/default/namespace imports, aliasing, JSX references, one-level named/type/star/default-as barrels, namespace re-export non-equivalence, recursive barrel one-level boundaries, JavaScript-family barrels including `index.mjs` and narrow `index.cjs`, tsconfig `baseUrl`/`paths` aliases, local tsconfig `extends` chains, package import pass-through behavior, and workspace package pass-through behavior are covered. Add characterization before broader replacement for package.json exports resolution, node_modules lookup, package-style tsconfig `extends`, or recursive barrel traversal if those become in scope. |
| TypeScript artifact extraction | Good for current tree-sitter scope | Edge-case coverage now includes abstract method signatures, constructor parameter properties, and defaulted/optional/rest/destructured parameters. Add tests before any broader replacement for overload signature ordering, decorators with emitted metadata, default anonymous exports, type-only declarations, generic parameter/default formatting, computed property names, and source line/column parity if the replacement reports richer positions. |
| Python validator internals | Good for current scope | Stdlib `ast` behavior is well characterized. If replacing with `astroid` or `libcst`, add tests for decorators beyond `@property`, dataclass/attrs-style fields if desired, overloaded functions, `typing.Protocol`, `__all__` re-exports, star import behavior, namespace packages, and line/column parity. |
| Required import checking in `core/validate.py` | Completed for current parser-backed scanner | Python remains stdlib-`ast` backed. TS/JS required import discovery now uses tree-sitter when available and covers relative imports, package imports, CommonJS `require`, `export from`, namespace imports, `import type`, dynamic `import()`, `require.resolve`, multiline imports, commented-out imports, and aliases. Future work should only add tsconfig/package resolution under an explicit manifest. |
| Graph/query parser replacement | Good enough, low priority | Query and graph behavior has dedicated coverage. A library replacement is not currently justified unless graph/query complexity grows. |

Conclusion: the incremental replacement slices now cover Svelte script
extraction, TypeScript barrel identity, TypeScript artifact extraction edge
cases, tsconfig alias identity, local tsconfig `extends` identity, package and
workspace package boundary behavior, parser-backed TS/JS required import
checking, namespace re-export boundaries, recursive barrel boundaries, and
`index.mjs`/narrow `index.cjs` barrel identity behind the existing validator
interface. There is still not enough dependency design for a broad TypeScript
compiler-backed replacement in one step. The next safe path is to add targeted
characterization for whichever broader behavior is selected next:
package exports resolution, node_modules lookup, package-style tsconfig
`extends`, recursive barrel traversal, or deeper artifact extraction gaps such
as overloads, decorators, default anonymous exports, generic formatting,
computed property names, and line/column parity.
