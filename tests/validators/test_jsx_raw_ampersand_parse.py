"""Regression contract for valid raw ampersands in JSX text and Git baselines."""

import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
from tree_sitter import Language, Parser
import tree_sitter_typescript

from maid_runner.cli.commands.assess import cmd_assess
from maid_runner.validators._typescript_parse import parse_typescript_source
from maid_runner.validators.typescript import TypeScriptValidator


def _parse(source: str, path: str = "sample.tsx"):
    return parse_typescript_source(
        source,
        path,
        Parser(Language(tree_sitter_typescript.language_typescript())),
        Parser(Language(tree_sitter_typescript.language_tsx())),
    )


@pytest.mark.parametrize("extension", ["tsx", "jsx"])
@pytest.mark.parametrize(
    "text", ["Contracts & Cancels", "A&B", "&", "A & B & C", "A && B", "🧪 & Café"]
)
@pytest.mark.parametrize("fragment", [False, True])
def test_raw_ampersands_in_jsx_text_parse_without_changing_original_bytes(
    extension, text, fragment
):
    markup = f"<span>{text}</span>"
    if fragment:
        markup = f"<>{markup}<span>Done</span></>"
    source = f"export function Title() {{ return {markup}; }}"

    session = _parse(source, f"sample.{extension}")

    assert session.parse_errors == []
    assert session.source_bytes == source.encode("utf-8")
    assert session.tree.root_node.end_byte == len(source.encode("utf-8"))


@pytest.mark.parametrize(
    "source",
    [
        "export function Title() { return <div>{value & mask}</div>; }",
        "export function Title() { return <div>{ready && <span>Ready</span>}</div>; }",
        "export function Title() { return <div title='Fish & Chips'>Ready</div>; }",
        "export function Title() { return <div>Fish &amp; Chips &#38; Dips</div>; }",
        "export function Title() { return <div>A &lt; B</div>; }",
    ],
)
def test_valid_jsx_expressions_attributes_and_entities_remain_unmodified(source):
    session = _parse(source)

    assert session.parse_errors == []
    assert session.source_bytes == source.encode("utf-8")
    assert session.tree.root_node.text == source.encode("utf-8")


@pytest.mark.parametrize(
    "source",
    [
        "export function Title() { return <div>{value&}</div>; }",
        "export function Title() { return <div>{value&&}</div>; }",
        "export function Title() { return <div &>Ready</div>; }",
        "export function Title() { return <div>Fish & Chips</span>; }",
        "export function Title() { return <div>Fish & Chips; }",
    ],
)
def test_ampersand_recovery_does_not_accept_genuine_jsx_syntax_errors(source):
    session = _parse(source)

    assert session.parse_errors
    assert session.source_bytes == source.encode("utf-8")


def test_raw_ampersand_repair_preserves_unrelated_syntax_error_locations():
    source = (
        "export function Title() { return <div>Fish & Chips</div>; }\n"
        "export const broken = ;\n"
    )

    session = _parse(source)

    assert session.parse_errors == ["Syntax error near line 2"]
    assert session.source_bytes == source.encode("utf-8")


def test_raw_ampersand_and_existing_parse_repairs_compose_without_restoring_errors():
    source = (
        "export type Row = { in_reply_to: string | null };\n"
        "vi.mock('./entry', async (importOriginal) => {\n"
        "  const original = await importOriginal<typeof import('./entry')>();\n"
        "  return original;\n"
        "});\n"
        "export function Title() { return <div>Fish & Chips</div>; }\n"
    )

    session = _parse(source)

    assert session.parse_errors == []
    assert session.source_bytes == source.encode("utf-8")


def test_collection_after_unicode_jsx_text_retains_original_names_and_lines():
    source = (
        "// 🧪 prefix\n"
        "export function Title() {\n"
        "  return <div>🧪 & Café</div>;\n"
        "}\n"
        "export function after(): number { return 1; }\n"
    )

    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "sample.tsx"
    )

    assert result.errors == []
    found = {artifact.name: artifact for artifact in result.artifacts}
    assert found["Title"].line == 2
    assert found["after"].line == 5
    assert found["after"].returns == "number"


def test_assessment_accepts_historical_raw_ampersand_baseline(
    tmp_path: Path, monkeypatch, capsys
):
    source_path = tmp_path / "src" / "Title.tsx"
    source_path.parent.mkdir()
    source_path.write_text(
        "export function Title() { return <div>Contracts & Cancels</div>; }\n"
    )
    for args in [("init", "-q"), ("add", "."), ("commit", "-qm", "baseline")]:
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=maid-test",
                "-c",
                "user.email=maid@example.test",
                *args,
            ],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
    baseline = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    source_path.write_text(
        "export function Title() { return <div>Contracts &amp; Cancels</div>; }\n"
    )
    monkeypatch.chdir(tmp_path)

    code = cmd_assess(
        SimpleNamespace(since=baseline, base_ref=None, manifest_dir=None, json=True)
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["verify_argv"][-2:] == ["--since", baseline]
    assert payload["profile"] in ("handoff", "deep")
