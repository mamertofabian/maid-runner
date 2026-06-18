# Validator Plugin Authoring

Third-party validator plugins let a separate package add language support to
MAID Runner without adding that parser to this repository. A plugin owns parser
quality for its language; MAID Runner owns the validator contract, discovery,
diagnostics, and validation semantics.

Language requests against this repository should use the validator plugin path.
Reference validators, such as a minimal Rust validator, belong in separate
repositories rather than in tree.

## Public Contract

The public validator plugin contract is deliberately small:

- `BaseValidator`
- `CollectionResult`
- `FoundArtifact` values returned inside `CollectionResult.artifacts`
- `ValidatorRegistry.register()` registration semantics
- the entry-point discovery rules documented here

This surface carries semver discipline. Any breaking change to the public
validator surface, including `BaseValidator`, `CollectionResult`, or
registration semantics, requires a major version of MAID Runner. Everything else under `maid_runner/validators/` is internal; it can change without plugin compatibility guarantees.

## Validator Class

A plugin exposes a `BaseValidator` subclass. The class declares the extensions
it handles and implements separate collectors for implementation files and
behavioral test files.

```python
from pathlib import Path

from maid_runner.core.types import ArtifactKind
from maid_runner.validators.base import BaseValidator, CollectionResult, FoundArtifact


class RustValidator(BaseValidator):
    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".rs",)

    def collect_implementation_artifacts(
        self,
        source: str,
        file_path: str | Path,
    ) -> CollectionResult:
        try:
            artifacts = parse_rust_definitions(source)
        except RustParseError as exc:
            return CollectionResult(
                artifacts=[],
                language="rust",
                file_path=str(file_path),
                errors=[str(exc)],
            )
        return CollectionResult(
            artifacts=artifacts,
            language="rust",
            file_path=str(file_path),
        )

    def collect_behavioral_artifacts(
        self,
        source: str,
        file_path: str | Path,
    ) -> CollectionResult:
        try:
            artifacts = parse_rust_test_references(source)
        except RustParseError as exc:
            return CollectionResult(
                artifacts=[],
                language="rust",
                file_path=str(file_path),
                errors=[str(exc)],
            )
        return CollectionResult(
            artifacts=artifacts,
            language="rust",
            file_path=str(file_path),
        )
```

Implementation collection returns artifact definitions from source files.
Behavioral collection returns references from test files to the artifacts they
exercise. Artifact identity must be exact enough for MAID's strict and
permissive validation modes: kind, name, optional `of` parent, arguments,
return types, async state, module identity, and alias information where the
language supports those concepts.

Parse errors must return a `CollectionResult` with no artifacts and a non-empty
`errors` list. A parser exception should not escape from the collector for
ordinary invalid language syntax. Empty files should return no artifacts and no
errors.

Private artifacts must be marked private by name or parent name. The shared
`FoundArtifact.is_private` rule treats names beginning with `_` or `#` as
private, including methods or attributes whose `of` parent begins that way.
Private artifacts must not appear in `generate_snapshot()` output.

## Entry-Point Packaging

Plugins register under the `maid_runner.validators` entry-point group. After a
user runs `pip install <plugin>`, `maid validate` can handle the plugin's
extensions in the installed environment.

```toml
[project]
name = "maid-validator-rust"
version = "0.1.0"
dependencies = ["maid-runner>=2,<3"]

[project.entry-points."maid_runner.validators"]
rust = "maid_validator_rust:RustValidator"
```

Each entry point must resolve to a `BaseValidator` subclass. Discovery happens
once when `ValidatorRegistry.with_builtin_validators()` constructs the registry.
Entry points are loaded in deterministic order by distribution name and then
entry-point name; discovery never depends on import side-effect timing.

Manual `ValidatorRegistry.register()` remains an explicit in-process API. It is
not a replacement for packaging a plugin distribution, and it does not apply the
plugin conflict rules used for entry-point discovery.

## Precedence And Diagnostics

MAID Runner uses a built-in-wins rule. If a plugin claims an extension already
claimed by a built-in validator, the built-in stays active for that extension.
The plugin record is inactive for the conflicting extension and validation
reports E903 `VALIDATOR_PLUGIN_CONFLICT` as warning severity.

If a plugin import, entry-point load, or registration check fails, MAID Runner
isolates that failure to the plugin. Built-in validators and other plugins stay
functional, and validation reports E902 `VALIDATOR_PLUGIN_LOAD_FAILURE` as
warning severity naming the distribution.

Behavioral and implementation validation surface E902 and E903 diagnostics as
warnings. Schema validation remains manifest-only and does not load or report
validator plugins. Directory-wide validation reports plugin diagnostics once on
the batch result instead of repeating the same warning for every manifest.

## Kill Switch And Audit

Set `MAID_DISABLE_VALIDATOR_PLUGINS=1` to disable plugin discovery entirely.
When the kill switch is set, plugin entry points are listed from metadata but
not imported, and `maid validators` shows them with status `disabled`.

Use `maid validators` to audit which code parses files in the current
environment:

```bash
maid validators
maid validators --json
```

The text table and `--json` output have parity. Both expose the same rows with
name, claimed extensions, source, status, and detail. Built-ins are listed
first, then plugins by distribution name. Status values are `active`,
`conflict`, `error`, and `disabled`.

## Conformance Kit

Passing the conformance kit is the evidence bar for a validator plugin. It
proves the collector cannot create false-green validation for its language by
checking both normal and adversarial cases through the public contract.

Import the public kit and fixture containers:

```python
from maid_runner.core.types import ArtifactKind
from maid_runner.testing.validator_conformance import (
    ConformanceArtifactSample,
    ConformanceFixtures,
    make_conformance_suite,
)

from maid_validator_rust import RustValidator


fixtures = ConformanceFixtures(
    extension=".rs",
    artifact_samples={
        ArtifactKind.CLASS.value: ConformanceArtifactSample(
            source="pub struct Widget;",
            expected_name="Widget",
        ),
        ArtifactKind.FUNCTION.value: ConformanceArtifactSample(
            source="pub fn render() {}",
            expected_name="render",
        ),
        ArtifactKind.METHOD.value: ConformanceArtifactSample(
            source="impl Widget { pub fn draw(&self) {} }",
            expected_name="draw",
            expected_of="Widget",
        ),
        ArtifactKind.ATTRIBUTE.value: ConformanceArtifactSample(
            source="pub struct Widget { pub id: String }",
            expected_name="id",
            expected_of="Widget",
        ),
    },
    private_artifact_source="fn _helper() {}",
    behavioral_target_kind=ArtifactKind.FUNCTION.value,
    behavioral_target_name="render",
    behavioral_target_of=None,
    behavioral_correct_source="#[test]\nfn test_render() { render(); }",
    behavioral_wrong_identity_source="#[test]\nfn test_other() { other(); }",
    unparseable_source="pub fn {",
    empty_source="",
)

TestRustValidatorConformance = make_conformance_suite(RustValidator, fixtures)
```

The fixture contract requires all of the following per language:

- one source sample per supported artifact kind
- private artifact sample
- behavioral test sample with correct identity
- wrong identity behavioral sample
- unparseable source sample
- empty file
- `behavioral_target_kind`
- `behavioral_target_name`
- `behavioral_target_of`

The returned class is pytest material. Assign it to a module-level name so
pytest can collect the parametrized tests.

The kit verifies that implementation samples produce exact artifact kinds and
identity fields, repeated collection is deterministic, private artifacts stay
private and out of snapshots, the correct behavioral sample references the
declared target, the wrong identity sample does not match that target, parse
errors return `CollectionResult(errors=[...], artifacts=[])`, and empty files
return no artifacts or errors.

Do not treat the kit as optional guidance. A plugin that cannot pass it has not
shown that its collector preserves MAID validation semantics.

## Support Boundary

Plugins own parser quality; MAID Runner owns the contract. Plugin maintainers
are responsible for their parser dependency, language version coverage, edge
cases, and release cadence. MAID Runner maintains the public contract,
entry-point discovery, conflict isolation, E902/E903 diagnostics, the
`maid validators` audit surface, and the conformance kit.

For a new language, publish an external plugin package and run the conformance
kit in that package's test suite. Do not add a new in-tree validator to this
repository unless a separate approved MAID plan changes the support boundary.
