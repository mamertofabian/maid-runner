# Parser Library Replacement Options

Date: 2026-05-06

## Context

MAID Runner currently validates source code by extracting MAID artifacts,
references, imports, test functions, and limited re-export identity from Python,
TypeScript, JavaScript, TSX, JSX, and Svelte files.

The project already uses mature parsing primitives in places:

- Python uses the standard library `ast` module.
- TypeScript/JavaScript uses `tree-sitter` with `tree-sitter-typescript`.
- Svelte declares `tree-sitter-svelte` as an optional dependency, but the current
  validator extracts `<script>` blocks with a regex and delegates to the
  TypeScript validator.

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
| Svelte parsing | Regex `<script>` extraction in `maid_runner/validators/svelte.py` | `svelte/compiler`, `tree-sitter-svelte` | Clearest wheel-reinvention area. Existing dependency declaration suggests the validator should use a real Svelte parser instead of regex. |
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

1. Svelte script extraction: replace regex extraction with a parser-backed
   implementation.
2. TypeScript re-export/import identity: replace regex and tree-sitter import
   scanning with compiler-backed symbol/module resolution.
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
- Svelte validator tests cover basic script extraction, TypeScript script
  extraction, no-script behavior, behavioral collection, delegated test body
  extraction, module path identity, import source identity, barrel matching, and
  explicit `.svelte` import identity.
- Module identity tests cover Python dotted module paths, Python relative
  imports, Python one-level `__init__.py` re-exports, TypeScript extensionless
  POSIX module paths, TypeScript relative imports, TypeScript `.svelte`
  specifier normalization, and one-level `index.ts(x)` re-exports.
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
| Svelte script extraction | Good for current behavior, but add edge cases first | Existing tests prove current single/basic script behavior. Before replacing regex, add characterization for module-context scripts, multiple `<script>` blocks, attributes with unusual spacing/order, `</script>`-like text inside strings/comments if supported by the chosen parser, and line-offset preservation for diagnostics/test bodies. |
| TypeScript import/re-export identity | Moderate | Named/default/namespace imports, aliasing, JSX references, and one-level named barrels are covered. Add characterization before compiler-backed replacement for `import type`, `export type`, `export *`, `export * as ns`, default re-exports, `index.js/mjs/cjs`, `package.json` exports if in scope, and `tsconfig` path aliases if the new library resolves them. |
| TypeScript artifact extraction | Moderate to good | Many syntax forms are covered. Add tests for overload signatures, decorators, abstract/interface method signatures, constructor parameter properties, default exported functions, type-only declarations, generic parameter/default formatting, optional/rest/destructured parameters, and source line/column behavior if the replacement reports richer positions. |
| Python validator internals | Good for current scope | Stdlib `ast` behavior is well characterized. If replacing with `astroid` or `libcst`, add tests for decorators beyond `@property`, dataclass/attrs-style fields if desired, overloaded functions, `typing.Protocol`, `__all__` re-exports, star import behavior, namespace packages, and line/column parity. |
| Required import checking in `core/validate.py` | Moderate | Existing tests cover Python imports, TS/JS relative imports, package imports, CommonJS `require`, `export from`, and namespace imports. Add tests for `import type`, dynamic `import()`, `require.resolve`, multiline imports, commented-out imports, and aliases before replacing regex extraction. |
| Graph/query parser replacement | Good enough, low priority | Query and graph behavior has dedicated coverage. A library replacement is not currently justified unless graph/query complexity grows. |

Conclusion: there is enough characterization to do an incremental in-place
replacement behind the existing validator interfaces, especially for Svelte
script extraction. There is not enough coverage for a broad TypeScript
compiler-backed replacement in one step. The safer path is to add a small set of
gap tests for the chosen slice, run them against the current implementation to
lock down intended behavior or expose intentional scope gaps, then replace only
that slice behind the same public methods.
