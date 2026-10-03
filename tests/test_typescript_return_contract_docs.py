"""Execute the documented compiler-return example through public APIs."""

from pathlib import Path
import json
import re

import pytest
import yaml

from maid_runner.core._implementation_validation import ImplementationFileValidator
from maid_runner.core.config import load_config
from maid_runner.core.diagnostics_registry import get_rule
from maid_runner.core.manifest import load_manifest
from maid_runner.validators.registry import ValidatorRegistry

ROOT = Path(__file__).resolve().parents[1]
HEADING = "##### **Compiler-backed TypeScript Return Contracts**"
ISSUE = "### 36. Compiler return contract is unavailable (`E309`)"


def _section():
    guide = (ROOT / "docs/maid_specs.md").read_text()
    assert (
        HEADING in guide
    ), "Compiler return configuration and executable example are not documented"
    remainder = guide.split(HEADING, 1)[1]
    return re.split(r"\n#{1,5} ", remainder, maxsplit=1)[0]


def _example(tmp_path):
    snippets = re.findall(r"```(yaml|tsx)\n(.*?)\n```", _section(), re.S)
    configs = [
        yaml.safe_load(text) for language, text in snippets if language == "yaml"
    ]
    configuration = next(
        item
        for item in configs
        if isinstance(item, dict) and "typescript_return_contracts" in item
    )
    artifacts = next(item for item in configs if isinstance(item, list))
    source = next(text for language, text in snippets if language == "tsx")
    assert len(artifacts) == 1 and artifacts[0]["name"] == "preview"
    (tmp_path / ".maidrc.yaml").write_text(yaml.safe_dump(configuration))
    (tmp_path / "tsconfig.app.json").write_text(
        json.dumps(
            {
                "compilerOptions": {"strict": True, "jsx": "preserve", "noEmit": True},
                "include": ["src"],
            }
        )
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src/Preview.tsx").write_text(source)
    (tmp_path / "example.manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Execute documented return contract",
                "type": "feature",
                "created": "2026-09-30",
                "files": {
                    "edit": [{"path": "src/Preview.tsx", "artifacts": artifacts}]
                },
                "validate": ["node --test tests/Preview.test.ts"],
            }
        )
    )
    return tmp_path


def _validate(example):
    manifest = load_manifest(example / "example.manifest.yaml")
    return ImplementationFileValidator(
        example, ValidatorRegistry.with_builtin_validators()
    ).validate_file_spec(manifest.file_spec_for("src/Preview.tsx"), manifest, None)


def test_documented_example_proves_inferred_return_without_source_edits(tmp_path):
    example = _example(tmp_path)
    configuration = load_config(example).typescript_return_contracts
    assert (
        configuration.mode == "compiler"
        and configuration.tsconfig == "tsconfig.app.json"
    )
    source = (example / "src/Preview.tsx").read_bytes()
    assert _validate(example) == []
    assert (example / "src/Preview.tsx").read_bytes() == source


def test_documented_default_syntax_mode_keeps_missing_return_warning(tmp_path):
    example = _example(tmp_path)
    (example / ".maidrc.yaml").unlink()
    errors = _validate(example)
    assert [(error.code.value, error.severity.value) for error in errors] == [
        ("E304", "warning")
    ]


@pytest.mark.parametrize(
    "change, code", [("binding", "E303"), ("return", "E302"), ("config", "E309")]
)
def test_documented_example_distinguishes_contract_and_capability_failures(
    tmp_path, change, code
):
    example = _example(tmp_path)
    path = example / "example.manifest.yaml"
    manifest = yaml.safe_load(path.read_text())
    if change == "binding":
        manifest["files"]["edit"][0]["artifacts"][0]["args"][0]["name"] = "props"
        path.write_text(yaml.safe_dump(manifest))
    elif change == "return":
        manifest["files"]["edit"][0]["artifacts"][0]["returns"] = "string"
        path.write_text(yaml.safe_dump(manifest))
    else:
        (example / "tsconfig.app.json").unlink()
    errors = _validate(example)
    assert [error.code.value for error in errors] == [code]
    assert errors[0].severity.value == "error"


def test_registered_e309_help_links_to_documented_recovery():
    guide = (ROOT / "docs/troubleshooting.md").read_text()
    assert ISSUE in guide, "E309 recovery is not documented"
    assert (
        get_rule("E309").help_uri
        == "docs/troubleshooting.md#36-compiler-return-contract-is-unavailable-e309"
    )
    section = guide.split(ISSUE, 1)[1].split("\n## ", 1)[0]
    for phrase in (
        "Symptom:",
        "Likely cause:",
        "Fix:",
        "tsconfig",
        "Node",
        "TypeScript",
        "E302",
        "E303",
        "E304",
    ):
        assert phrase in section


def test_documentation_states_compiler_boundaries_and_preserves_exact_bindings():
    section = _section()
    for phrase in (
        "syntax",
        "compiler",
        "tsconfig",
        "bidirectional",
        "strictNullChecks",
        "E302",
        "E303",
        "E304",
        "E309",
        "FoundArtifact.returns",
        "snapshots",
        "overloads",
        "methods",
        "arrow",
        ".d.ts",
        "any",
        "unknown",
        "noCheck",
        "@ts-nocheck",
        "5-second",
    ):
        assert phrase in section
    assert 'import("react/jsx-runtime").JSX.Element' in section
    assert "not a parameter named `props`" in section
