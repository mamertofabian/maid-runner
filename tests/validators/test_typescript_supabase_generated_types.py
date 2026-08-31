"""Regressions for generated Supabase TypeScript database types."""

from __future__ import annotations

from maid_runner.core.types import ArtifactKind
from maid_runner.validators._typescript_parse import parse_typescript_source
from maid_runner.validators.typescript import TypeScriptValidator


def _parse(source: str):
    validator = TypeScriptValidator()
    return parse_typescript_source(
        source,
        "src/integrations/supabase/types.ts",
        validator._ts_parser,
        validator._tsx_parser,
    )


def test_nested_in_prefixed_supabase_fields_parse_and_preserve_source() -> None:
    source = """export type Database = {
  public: {
    Tables: {
      ticket_messages: {
        Row: {
          id: string
          in_reply_to: string | null
        }
        Insert: {
          id?: string
          in_reply_to?: string | null
        }
        Update: {
          id?: string
          in_reply_to?: string | null
        }
        Relationships: []
      }
    }
  }
}
"""

    session = _parse(source)
    collected = TypeScriptValidator().collect_implementation_artifacts(
        source,
        "src/integrations/supabase/types.ts",
    )

    assert session.parse_errors == []
    assert session.source_bytes == source.encode("utf-8")
    assert [(artifact.kind, artifact.name) for artifact in collected.artifacts] == [
        (ArtifactKind.TYPE, "Database")
    ]
    assert collected.errors == []


def test_nested_in_prefixed_sanitizer_preserves_unrelated_syntax_errors() -> None:
    source = """export type Database = {
  public: {
    Tables: {
      ticket_messages: {
        Row: {
          in_reply_to: string | null
          broken_field string
        }
      }
    }
  }
}
"""

    session = _parse(source)

    assert session.parse_errors == ["Syntax error near line 7"]
