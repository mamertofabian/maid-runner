"""Regression contract for generated property headers spilled into annotations."""

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


def _parse(source: str):
    return parse_typescript_source(
        source,
        "src/types.ts",
        Parser(Language(tree_sitter_typescript.language_typescript())),
        Parser(Language(tree_sitter_typescript.language_tsx())),
    )


def _database(
    optional: bool = False, newline: str = "\n", prefix: str = "in_reconciliation"
) -> str:
    fields = f"id{'?' if optional else ''}: string\n{prefix}{'?' if optional else ''}: boolean\nmatch_confidence: number | null"
    source = (
        "export type Database = { public: { Tables: { records: { Row: {\n"
        + fields
        + "\n} } } } }\n"
    )
    return source.replace("\n", newline)


@pytest.mark.parametrize("optional", [False, True])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("prefix", ["in_reconciliation", "in_reply_to", "in_progress"])
def test_spilled_in_prefixed_headers_parse_and_preserve_original_bytes(
    optional, newline, prefix
):
    source = _database(optional, newline, prefix)

    session = _parse(source)

    assert session.parse_errors == []
    assert session.source_bytes == source.encode("utf-8")
    assert session.tree.root_node.end_byte == len(source.encode("utf-8"))


def test_full_row_insert_update_shapes_preserve_original_alias_fields_and_offsets():
    source = "// 🧪 generated fixture\nexport type Database = { public: { Tables: { records: {\n"
    for shape, optional in [("Row", False), ("Insert", True), ("Update", True)]:
        fields = f"id{'?' if optional else ''}: string\nin_reconciliation{'?' if optional else ''}: boolean\nmatch_confidence{'?' if optional else ''}: number | null"
        source += shape + ": {\n" + fields + "\n}\n"
    source += "} } } }\nexport function after(): number { return 1; }\n"

    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/types.ts"
    )

    assert result.errors == []
    found = {artifact.name: artifact for artifact in result.artifacts}
    assert "in_reconciliation" in found["Database"].type_annotation
    assert "xx_reconciliation" not in found["Database"].type_annotation
    assert found["after"].line == source.count("\n")
    assert found["after"].returns == "number"


@pytest.mark.parametrize(
    "fields",
    [
        "id: string in_reconciliation: boolean\nmatch_confidence: number",
        "id: string\nin_reconciliation boolean\nmatch_confidence: number",
        "id: string\nin_reconciliation:\nmatch_confidence: number",
        "id: string\nin_reconciliation??: boolean\nmatch_confidence: number",
        "id: string\nin_reconciliation: boolean\nbroken_field string",
        "id: string\nout_reconciliation boolean\nmatch_confidence: number",
    ],
)
def test_spilled_header_recovery_preserves_malformed_or_unrelated_fields(fields):
    source = (
        "export type Database = { public: { Tables: { records: { Row: {\n"
        + fields
        + "\n} } } } }"
    )

    session = _parse(source)

    assert session.parse_errors
    assert session.source_bytes == source.encode("utf-8")


def test_spilled_header_repair_retains_the_unrelated_error_line():
    source = _database() + "export const broken = ;\n"

    session = _parse(source)

    assert session.parse_errors == [f"Syntax error near line {source.count(chr(10))}"]


def test_header_looking_literals_and_valid_semicolon_fields_remain_unmodified():
    source = (
        "export type Row = { id: string; in_reconciliation: boolean };\n"
        "export const label = 'in_reconciliation?: boolean';\n"
        "// in_reconciliation: boolean\n"
    )

    session = _parse(source)

    assert session.parse_errors == []
    assert session.tree.root_node.text == source.encode("utf-8")
    assert session.source_bytes == source.encode("utf-8")


def test_assessment_accepts_spilled_headers_in_an_immutable_generated_baseline(
    tmp_path: Path, monkeypatch, capsys
):
    target = tmp_path / "src/types.ts"
    target.parent.mkdir()
    target.write_text(_database())
    for arguments in [("init", "-q"), ("add", "."), ("commit", "-qm", "baseline")]:
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=maid-test",
                "-c",
                "user.email=maid@example.test",
                *arguments,
            ],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
    baseline = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    target.write_text(_database() + "export type Added = string;\n")
    monkeypatch.chdir(tmp_path)

    code = cmd_assess(
        SimpleNamespace(since=baseline, base_ref=None, manifest_dir=None, json=True)
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["verify_argv"][-2:] == ["--since", baseline]
