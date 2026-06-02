from __future__ import annotations

import re
import runpy
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import yaml

import maid_runner


ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = ROOT / "docs" / "reference"


def _autosummary_entries(text: str) -> list[str]:
    block_match = re.search(
        r"\.\. autosummary::\n(?P<body>(?:\s+:[^\n]+\n|\s+\S[^\n]*\n|\s*\n)+)",
        text,
    )
    assert block_match, "api.rst must define an autosummary block"

    entries: list[str] = []
    for line in block_match.group("body").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(":"):
            continue
        entries.append(stripped.removeprefix("maid_runner."))
    return entries


def test_sphinx_configuration_declares_reference_build_settings() -> None:
    config = runpy.run_path(str(DOCS_ROOT / "conf.py"))

    project = config["project"]
    author = config["author"]
    extensions = config["extensions"]
    autosummary_generate = config["autosummary_generate"]
    autodoc_typehints = config["autodoc_typehints"]
    autodoc_member_order = config["autodoc_member_order"]
    intersphinx_mapping = config["intersphinx_mapping"]
    html_theme = config["html_theme"]
    html_title = config["html_title"]

    assert project == "MAID Runner"
    assert author == "Mamerto Fabian Jr."
    assert extensions == [
        "sphinx.ext.autodoc",
        "sphinx.ext.autosummary",
        "sphinx.ext.intersphinx",
    ]
    assert autosummary_generate is True
    assert autodoc_typehints == "description"
    assert autodoc_member_order == "bysource"
    assert "python" in intersphinx_mapping
    assert html_theme == "furo"
    assert html_title == "MAID Runner API Reference"

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    docs_deps = pyproject["dependency-groups"]["docs"]
    assert any(dep.startswith("sphinx>=") for dep in docs_deps)
    assert any(dep.startswith("furo>=") for dep in docs_deps)


def test_reference_index_and_public_api_page_cover_all_exported_symbols() -> None:
    index_text = (DOCS_ROOT / "index.rst").read_text()
    api_text = (DOCS_ROOT / "api.rst").read_text()

    assert "API Reference" in index_text
    assert "api" in index_text
    assert "examples" in index_text
    assert ".. automodule:: maid_runner" in api_text

    documented_exports = _autosummary_entries(api_text)
    assert documented_exports == list(maid_runner.__all__)


def test_examples_use_cross_references_for_major_public_workflows() -> None:
    examples_text = (DOCS_ROOT / "examples.rst").read_text()

    expected_refs = [
        ":func:`maid_runner.validate`",
        ":func:`maid_runner.validate_all`",
        ":func:`maid_runner.generate_snapshot`",
        ":func:`maid_runner.load_manifest`",
        ":func:`maid_runner.save_manifest`",
        ":class:`maid_runner.ValidationEngine`",
        ":class:`maid_runner.ManifestChain`",
        ":class:`maid_runner.ValidatorRegistry`",
    ]
    for reference in expected_refs:
        assert reference in examples_text

    assert examples_text.count(".. code-block:: python") >= 4
    assert "ValidationResult" in examples_text
    assert "BatchValidationResult" in examples_text
    assert "snapshot.files_snapshot[0].path" in examples_text


def test_readthedocs_configuration_builds_the_sphinx_reference() -> None:
    config = yaml.safe_load((ROOT / ".readthedocs.yaml").read_text())

    assert config["version"] == 2
    assert config["sphinx"]["configuration"] == "docs/reference/conf.py"
    assert config["build"]["os"] == "ubuntu-24.04"
    assert config["build"]["tools"]["python"] == "3.12"
    install = config["python"]["install"]
    assert {"method": "pip", "path": ".", "extra_requirements": ["all"]} in install
    assert any(
        step["requirements"] == "docs/reference/requirements.txt" for step in install
    )


def test_sphinx_reference_builds_without_warnings(tmp_path: Path) -> None:
    docs_source = tmp_path / "source"
    shutil.copytree(DOCS_ROOT, docs_source)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "sphinx",
            "-b",
            "html",
            "-W",
            "--keep-going",
            str(docs_source),
            str(tmp_path / "html"),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    assert result.returncode == 0, result.stdout
    assert (tmp_path / "html" / "index.html").exists()
    assert (tmp_path / "html" / "generated" / "maid_runner.validate.html").exists()
    assert (
        tmp_path / "html" / "generated" / "maid_runner.ValidationEngine.html"
    ).exists()
