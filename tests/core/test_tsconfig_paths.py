"""Behavioral tests for TypeScript tsconfig path helpers."""

from __future__ import annotations

import json
from pathlib import Path

from maid_runner.core._tsconfig_paths import (
    load_tsconfig,
    resolve_paths_alias,
    strip_jsonc_trivia,
)


def test_strip_jsonc_trivia_preserves_valid_json_with_comments_and_trailing_commas() -> None:
    source = r'''
{
  // TypeScript accepts comments in tsconfig files.
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"], /* and trailing commas */
    },
    "literal": "https://example.test//not-a-comment",
  },
}
'''

    parsed = json.loads(strip_jsonc_trivia(source))

    assert parsed["compilerOptions"]["paths"]["@/*"] == ["src/*"]
    assert parsed["compilerOptions"]["literal"] == "https://example.test//not-a-comment"


def test_load_tsconfig_merges_relative_extends_before_child_options(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tsconfig.base.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "baseUrl": ".",
                    "paths": {"@/*": ["src/*"]},
                    "strict": True,
                }
            }
        )
    )
    (tmp_path / "tsconfig.json").write_text(
        json.dumps(
            {
                "extends": "./tsconfig.base.json",
                "compilerOptions": {
                    "baseUrl": "src",
                    "jsx": "react-jsx",
                },
            }
        )
    )

    config = load_tsconfig(tmp_path)

    assert config is not None
    assert config["compilerOptions"]["paths"] == {"@/*": ["src/*"]}
    assert config["compilerOptions"]["strict"] is True
    assert config["compilerOptions"]["jsx"] == "react-jsx"
    assert config["compilerOptions"]["baseUrl"] == str(tmp_path / "src")


def test_resolve_paths_alias_preserves_best_pattern_priority(tmp_path: Path) -> None:
    generated = tmp_path / "src" / "generated" / "models"
    generated.mkdir(parents=True)
    (generated / "Foo.ts").write_text("export class Foo {}\n")
    models = tmp_path / "src" / "models"
    models.mkdir(parents=True)
    (models / "Foo.ts").write_text("export class Foo {}\n")
    compiler_options = {
        "baseUrl": ".",
        "paths": {
            "@/*": ["src/generated/*"],
            "@/models/*": ["src/models/*"],
        },
    }

    assert (
        resolve_paths_alias("@/models/Foo", tmp_path, compiler_options)
        == "src/models/Foo"
    )


def test_resolve_paths_alias_returns_existing_index_module(tmp_path: Path) -> None:
    components = tmp_path / "src" / "components"
    components.mkdir(parents=True)
    (components / "index.ts").write_text("export function Button() {}\n")
    compiler_options = {
        "baseUrl": ".",
        "paths": {"@components": ["src/components"]},
    }

    assert (
        resolve_paths_alias("@components", tmp_path, compiler_options)
        == "src/components"
    )
