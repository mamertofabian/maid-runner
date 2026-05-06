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
3. TypeScript artifact extraction: consider `ts-morph` or a TypeScript compiler
   API subprocess/adapter if signatures and declarations keep accumulating edge
   cases.
4. Python import graph: consider `grimp` only if package-level dependency
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

## Characterization Test Assessment

Assessment date: 2026-05-06

Focused parser/replacement characterization coverage is substantial:

- Python validator tests cover class/function/method/attribute extraction,
  signature extraction, bases, property handling, class/module attributes,
  private detection, package `__init__.py` re-exports, behavioral references,
  keyword arguments, dotted imports, tuple assignment, syntax-error handling,
  stub detection, identity fields, relative imports, alias handling, and
  attribute-chain module identity.
- TypeScript validator tests cover interfaces, classes, methods, arrow
  functions, class fields, private `#` members, object property arrow exclusion,
  enums, namespaces, constructors, getters/setters, generator functions,
  export statements, inheritance, interface members, member-expression
  behavioral references, namespace import identity, JSX/TSX references,
  object/JSX props, test-function label detection, stub detection, module path
  identity, barrel re-export matching, and cross-module collision rejection.
- Svelte validator tests cover parser-backed script extraction, TypeScript
  script extraction, ignored scripts inside comments, quoted `>` attributes,
  module-context plus instance script ordering, no-script behavior, behavioral
  collection, delegated test body extraction, module path identity, import
  source identity, barrel matching, and explicit `.svelte` import identity.
- Module identity tests cover Python dotted module paths, Python relative
  imports, Python one-level `__init__.py` re-exports, TypeScript extensionless
  POSIX module paths, TypeScript relative imports, TypeScript `.svelte`
  specifier normalization, one-level `index.ts(x)` re-exports, type-only
  TypeScript named re-exports, and `index.js` TypeScript-family barrel
  re-exports.
- Validation/integration tests cover parser error surfacing, required import
  checks, JS/TS relative import normalization, CommonJS `require`, `export from`,
  namespace imports, Svelte validation, test coverage behavior, and public
  library API expectations.

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
| TypeScript import/re-export identity | Partially completed | Named/default/namespace imports, aliasing, JSX references, one-level named barrels, type-only named barrel re-exports, and `index.js` barrels are covered. Parser-backed `resolve_ts_reexport` is complete for the current one-level named barrel contract. Add characterization before broader replacement for `export *`, `export * as ns`, default re-exports, `index.mjs/cjs`, `package.json` exports if in scope, and `tsconfig` path aliases if the new library resolves them. |
| TypeScript artifact extraction | Moderate to good | Many syntax forms are covered. Add tests for overload signatures, decorators, abstract/interface method signatures, constructor parameter properties, default exported functions, type-only declarations, generic parameter/default formatting, optional/rest/destructured parameters, and source line/column behavior if the replacement reports richer positions. |
| Python validator internals | Good for current scope | Stdlib `ast` behavior is well characterized. If replacing with `astroid` or `libcst`, add tests for decorators beyond `@property`, dataclass/attrs-style fields if desired, overloaded functions, `typing.Protocol`, `__all__` re-exports, star import behavior, namespace packages, and line/column parity. |
| Required import checking in `core/validate.py` | Moderate | Existing tests cover Python imports, TS/JS relative imports, package imports, CommonJS `require`, `export from`, and namespace imports. Add tests for `import type`, dynamic `import()`, `require.resolve`, multiline imports, commented-out imports, and aliases before replacing regex extraction. |
| Graph/query parser replacement | Good enough, low priority | Query and graph behavior has dedicated coverage. A library replacement is not currently justified unless graph/query complexity grows. |

Conclusion: the first two incremental replacement slices are complete behind
the existing validator interface: Svelte script extraction and TypeScript
one-level named barrel re-export identity. There is still not enough coverage
or dependency design for a broad TypeScript compiler-backed replacement in one
step. The next safe path is to add targeted characterization for the remaining
TypeScript import/export identity gaps, especially star exports, default
re-exports, package exports, and tsconfig path aliases, before replacing any
broader slice behind the same public methods.
