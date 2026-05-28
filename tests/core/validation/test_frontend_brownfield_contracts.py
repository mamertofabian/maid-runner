"""Regression coverage for brownfield TypeScript frontend contracts."""

from tree_sitter import Language, Parser
import tree_sitter_typescript as ts_ts

from maid_runner.core._implementation_validation import ImplementationFileValidator
from maid_runner.core.chain import ManifestChain
from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine
from maid_runner.validators._typescript_behavioral import collect_behavioral_artifacts
from maid_runner.validators._typescript_implementation import (
    collect_implementation_artifacts,
)
from maid_runner.validators._typescript_parse import parse_typescript_source


def _write(project_dir, rel_path, content):
    path = project_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _write_manifest(project_dir, name, content):
    return _write(project_dir, f"manifests/{name}", content)


def _typescript_parsers():
    return (
        Parser(Language(ts_ts.language_typescript())),
        Parser(Language(ts_ts.language_tsx())),
    )


def test_import_type_object_literal_api_members_are_collectible(tmp_path):
    ts_parser, tsx_parser = _typescript_parsers()
    source = """type Result<T> = Promise<T>;

declare function fetchJson<T>(path: string, init?: RequestInit): Result<T>;

export const api = {
  fitnessGetAnalysis: (contentType: string, contentId: number) =>
    fetchJson<import('$lib/types/api.js').ExerciseAnalysis>(
      `/api/fitness/analysis/${contentType}/${contentId}`,
    ),
  fitnessResetEnrollment: (enrollmentId: string) =>
    fetchJson<{ reset: boolean; current_day: number }>(
      `/api/fitness/enrollments/${enrollmentId}/reset`,
      { method: 'POST' },
    ),
  fitnessUnenroll(enrollmentId: string): Result<{ unenrolled: boolean }> {
    return fetchJson<{ unenrolled: boolean }>(
      `/api/fitness/enrollments/${enrollmentId}/unenroll`,
      { method: 'POST' },
    );
  },
};

if (Math.random() > 2) {
  const api = {
    hiddenLocal: () => true,
  };
}
"""

    session = parse_typescript_source(
        source, "src/lib/services/api.ts", ts_parser, tsx_parser
    )
    artifacts = collect_implementation_artifacts(
        session.tree.root_node, session.source_bytes
    )

    assert session.parse_errors == []
    reset = next(
        artifact for artifact in artifacts if artifact.name == "fitnessResetEnrollment"
    )
    assert reset.kind.value == "function"
    assert [(arg.name, arg.type) for arg in reset.args] == [("enrollmentId", "string")]
    unenroll = next(
        artifact for artifact in artifacts if artifact.name == "fitnessUnenroll"
    )
    assert unenroll.kind.value == "function"
    assert [(arg.name, arg.type) for arg in unenroll.args] == [
        ("enrollmentId", "string")
    ]
    assert unenroll.returns == "Result<{ unenrolled: boolean }>"
    assert not any(artifact.name == "hiddenLocal" for artifact in artifacts)


def test_named_imported_api_object_member_reference_keeps_module_identity(tmp_path):
    project = tmp_path
    _write(project, "frontend/tsconfig.json", "{}")
    test_path = _write(
        project,
        "frontend/tests/lib/services/api.test.ts",
        """import { api } from '../../../src/lib/services/api';
import { makeClient } from '../../../src/lib/services/client';

it('posts to the fitness enrollment reset endpoint', async () => {
  await api.fitnessResetEnrollment('enrollment-1');
  await api.client.fitnessResetEnrollment('nested');
  await makeClient().fitnessResetEnrollment('factory');
});
""",
    )
    _write(
        project,
        "frontend/src/lib/services/api.ts",
        "export const api = { fitnessResetEnrollment: (id: string) => id };\n",
    )
    _write(
        project,
        "frontend/src/lib/services/client.ts",
        "export const makeClient = () => ({ fitnessResetEnrollment: (id: string) => id });\n",
    )
    ts_parser, tsx_parser = _typescript_parsers()

    session = parse_typescript_source(
        test_path.read_text(), test_path, ts_parser, tsx_parser
    )
    artifacts = collect_behavioral_artifacts(
        session.tree.root_node, session.source_bytes, test_path
    )

    assert session.parse_errors == []
    assert any(
        artifact.name == "fitnessResetEnrollment"
        and artifact.import_source == "src/lib/services/api"
        and artifact.reference_context == "access"
        for artifact in artifacts
    )
    assert not any(
        artifact.name == "fitnessResetEnrollment"
        and artifact.import_source == "src/lib/services/client"
        for artifact in artifacts
    )


def test_edit_only_manifest_chain_keeps_brownfield_files_permissive(tmp_path):
    project = tmp_path
    (project / "manifests").mkdir()
    _write_manifest(
        project,
        "add-brownfield-action.manifest.yaml",
        """schema: "2"
goal: "Add brownfield action"
type: feature
created: "2026-05-28"
files:
  edit:
    - path: src/service.py
      artifacts:
        - kind: function
          name: reset
  read:
    - tests/test_service.py
validate:
  - pytest tests/test_service.py -v
""",
    )
    _write(
        project,
        "src/service.py",
        "def existing():\n    return 'existing'\n\n"
        "def reset():\n    return 'reset'\n",
    )
    _write(
        project,
        "tests/test_service.py",
        "from src.service import reset\n\n"
        "def test_reset():\n    assert reset() == 'reset'\n",
    )

    chain = ManifestChain(project / "manifests", project_root=project)
    engine = ValidationEngine(project_root=project)
    assert ImplementationFileValidator is not None
    assert ImplementationFileValidator.validate_file_spec is not None

    result = engine.validate(
        project / "manifests/add-brownfield-action.manifest.yaml",
        mode=ValidationMode.IMPLEMENTATION,
        use_chain=True,
        chain=chain,
    )

    assert result.success is True
    assert not any(
        error.code == ErrorCode.UNEXPECTED_ARTIFACT for error in result.errors
    )
