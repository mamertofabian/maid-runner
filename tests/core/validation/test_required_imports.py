"""Focused characterization tests for required import validation."""

import pytest

from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine


@pytest.fixture()
def project(tmp_path):
    """Create a temporary project directory."""
    (tmp_path / "src").mkdir()
    (tmp_path / "manifests").mkdir()
    (tmp_path / "tests").mkdir()
    return tmp_path


def write_manifest(project_dir, name, content):
    path = project_dir / "manifests" / name
    path.write_text(content)
    return path


def write_source(project_dir, rel_path, content):
    path = project_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def missing_import_errors(result):
    return [
        error
        for error in result.errors
        if error.code == ErrorCode.MISSING_REQUIRED_IMPORT
    ]


def test_python_required_import_present_has_no_e320(project):
    manifest_path = write_manifest(
        project,
        "add-page.manifest.yaml",
        """schema: "2"
goal: "Add page"
files:
  create:
    - path: src/pages/budget.py
      artifacts:
        - kind: function
          name: BudgetPage
      imports:
        - src.api.budgets
  read:
    - tests/test_budget.py
validate:
  - pytest tests/test_budget.py -v
""",
    )
    write_source(
        project,
        "src/pages/budget.py",
        "from src.api.budgets import list_budgets\n\n"
        "def BudgetPage():\n"
        "    return list_budgets()\n",
    )
    write_source(
        project,
        "tests/test_budget.py",
        "from src.pages.budget import BudgetPage\n\n"
        "def test_budget_page():\n"
        "    assert BudgetPage is not None\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert missing_import_errors(result) == []


def test_python_missing_required_import_reports_e320(project):
    manifest_path = write_manifest(
        project,
        "add-page.manifest.yaml",
        """schema: "2"
goal: "Add page"
files:
  create:
    - path: src/pages/budget.py
      artifacts:
        - kind: function
          name: BudgetPage
      imports:
        - src.api.budgets
  read:
    - tests/test_budget.py
validate:
  - pytest tests/test_budget.py -v
""",
    )
    write_source(
        project,
        "src/pages/budget.py",
        "def BudgetPage():\n" "    return 'placeholder'\n",
    )
    write_source(
        project,
        "tests/test_budget.py",
        "from src.pages.budget import BudgetPage\n\n"
        "def test_budget_page():\n"
        "    assert BudgetPage is not None\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
    import_errors = missing_import_errors(result)

    assert len(import_errors) == 1
    assert "src.api.budgets" in import_errors[0].message


def test_multiple_missing_required_imports_report_individual_e320_errors(project):
    manifest_path = write_manifest(
        project,
        "add-service.manifest.yaml",
        """schema: "2"
goal: "Add service"
files:
  create:
    - path: src/service.py
      artifacts:
        - kind: function
          name: run_service
      imports:
        - some.module
        - another.module
  read:
    - tests/test_service.py
validate:
  - pytest tests/test_service.py -v
""",
    )
    write_source(project, "src/service.py", "def run_service():\n    return 'ok'\n")
    write_source(
        project,
        "tests/test_service.py",
        "from src.service import run_service\n\n"
        "def test_run_service():\n"
        "    assert run_service() == 'ok'\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
    import_errors = missing_import_errors(result)

    assert len(import_errors) == 2
    assert {error.message.split("'")[1] for error in import_errors} == {
        "some.module",
        "another.module",
    }


def test_partial_required_imports_report_only_missing_entries(project):
    manifest_path = write_manifest(
        project,
        "add-service.manifest.yaml",
        """schema: "2"
goal: "Add service"
files:
  create:
    - path: src/service.py
      artifacts:
        - kind: function
          name: run_service
      imports:
        - os
        - missing_module
  read:
    - tests/test_service.py
validate:
  - pytest tests/test_service.py -v
""",
    )
    write_source(
        project,
        "src/service.py",
        "import os\n\n" "def run_service():\n" "    return os.getcwd()\n",
    )
    write_source(
        project,
        "tests/test_service.py",
        "from src.service import run_service\n\n"
        "def test_run_service():\n"
        "    assert run_service is not None\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
    import_errors = missing_import_errors(result)

    assert len(import_errors) == 1
    assert "missing_module" in import_errors[0].message
    assert "os" not in import_errors[0].message


def test_python_path_style_required_import_matches_dotted_import(project):
    manifest_path = write_manifest(
        project,
        "add-user-routes.manifest.yaml",
        """schema: "2"
goal: "Add user routes"
files:
  create:
    - path: src/routes/users.py
      artifacts:
        - kind: function
          name: list_users
      imports:
        - src/models/user.py
  read:
    - tests/test_users.py
validate:
  - pytest tests/test_users.py -v
""",
    )
    write_source(
        project,
        "src/routes/users.py",
        "from src.models.user import User\n\n"
        "def list_users():\n"
        "    return User.all()\n",
    )
    write_source(
        project,
        "tests/test_users.py",
        "from src.routes.users import list_users\n\n"
        "def test_list_users():\n"
        "    assert list_users is not None\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert missing_import_errors(result) == []


def test_typescript_relative_import_satisfies_manifest_path(project):
    manifest_path = write_manifest(
        project,
        "add-budget-page.manifest.yaml",
        """schema: "2"
goal: "Add budget page"
files:
  create:
    - path: src/pages/BudgetPage.ts
      artifacts:
        - kind: function
          name: BudgetPage
      imports:
        - src/models/Budget
validate:
  - pytest tests/ -v
""",
    )
    write_source(
        project,
        "src/pages/BudgetPage.ts",
        'import { Budget } from "../models/Budget";\n\n'
        "export function BudgetPage() { return new Budget(); }\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert missing_import_errors(result) == []


def test_commonjs_relative_require_satisfies_manifest_path(project):
    manifest_path = write_manifest(
        project,
        "add-api-service.manifest.yaml",
        """schema: "2"
goal: "Add API service"
files:
  create:
    - path: src/services/api.js
      artifacts:
        - kind: function
          name: callApi
      imports:
        - src/models/Budget
validate:
  - pytest tests/ -v
""",
    )
    write_source(
        project,
        "src/services/api.js",
        'const Budget = require("../models/Budget");\n\n'
        "function callApi() { return new Budget(); }\n"
        "module.exports = { callApi };\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert missing_import_errors(result) == []
