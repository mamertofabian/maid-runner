from pathlib import Path
from types import SimpleNamespace

from maid_runner.cli.commands.howto import cmd_howto


ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs/validator-plugin-authoring.md"
README = ROOT / "README.md"
HOWTO = ROOT / "maid_runner/cli/commands/howto.py"
ROADMAP = ROOT / "docs/ROADMAP.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_validator_plugin_authoring_guide_documents_contract_and_runtime_rules() -> (
    None
):
    guide = _read(GUIDE)

    for required in (
        "BaseValidator",
        "CollectionResult",
        "registration semantics",
        "maid_runner.validators",
        "built-in-wins",
        "E902",
        "VALIDATOR_PLUGIN_LOAD_FAILURE",
        "E903",
        "VALIDATOR_PLUGIN_CONFLICT",
        "warning",
        "MAID_DISABLE_VALIDATOR_PLUGINS",
        "maid validators",
        "--json",
        "make_conformance_suite",
        "behavioral_target_kind",
        "behavioral_target_name",
        "behavioral_target_of",
    ):
        assert required in guide

    for fixture_requirement in (
        "one source sample per supported artifact kind",
        "private artifact sample",
        "behavioral test sample with correct identity",
        "wrong identity",
        "unparseable source sample",
        "empty file",
    ):
        assert fixture_requirement in guide

    assert "validation" in guide
    assert "warnings" in guide


def test_validator_plugin_authoring_guide_states_support_boundary_and_semver() -> None:
    guide = _read(GUIDE)

    assert "Plugins own parser quality; MAID Runner owns the contract" in guide
    assert "semver discipline" in guide
    assert "breaking" in guide
    assert "major version" in guide
    assert "Everything else under `maid_runner/validators/` is internal" in guide


def test_language_support_entrypoints_route_requests_to_plugin_path(capsys) -> None:
    readme = _read(README)
    howto = _read(HOWTO)
    roadmap = _read(ROADMAP)
    result = cmd_howto(SimpleNamespace(topic="commands"))
    howto_output = capsys.readouterr().out

    for content in (readme, howto, roadmap):
        assert "docs/validator-plugin-authoring.md" in content
        assert "validator plugin" in content

    assert result == 0
    assert "docs/validator-plugin-authoring.md" in howto_output
    assert "validator plugin" in howto_output
    assert "language requests" in readme
    assert "new language support" in howto_output
    assert "plugin path" in roadmap
