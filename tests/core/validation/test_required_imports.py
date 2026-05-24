"""Focused characterization tests for required import validation."""

import json
import sys

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


def test_missing_imports_field_skips_required_import_check(project):
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
        "    assert BudgetPage() == 'placeholder'\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    assert missing_import_errors(result) == []


def test_python_required_import_can_match_imported_symbol_name(project):
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
        - list_budgets
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

    assert result.success is True
    assert missing_import_errors(result) == []


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


def test_python_path_style_without_extension_matches_dotted_import(project):
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
        - src/models/user
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


def test_python_dotted_required_import_matches_dotted_import(project):
    manifest_path = write_manifest(
        project,
        "add-user-views.manifest.yaml",
        """schema: "2"
goal: "Add user views"
files:
  create:
    - path: src/views/users.py
      artifacts:
        - kind: function
          name: show_users
      imports:
        - src.models.user
  read:
    - tests/test_users.py
validate:
  - pytest tests/test_users.py -v
""",
    )
    write_source(
        project,
        "src/views/users.py",
        "from src.models.user import User\n\n"
        "def show_users():\n"
        "    return User.all()\n",
    )
    write_source(
        project,
        "tests/test_users.py",
        "from src.views.users import show_users\n\n"
        "def test_show_users():\n"
        "    assert show_users is not None\n",
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


def test_typescript_deep_relative_import_satisfies_manifest_path(project):
    manifest_path = write_manifest(
        project,
        "add-test.manifest.yaml",
        """schema: "2"
goal: "Add test"
files:
  create:
    - path: tests/pages/test_budget.ts
      artifacts:
        - kind: function
          name: testBudget
      imports:
        - src/models/Budget
validate:
  - pytest tests/ -v
""",
    )
    write_source(
        project,
        "tests/pages/test_budget.ts",
        'import { Budget } from "../../src/models/Budget";\n\n'
        "export function testBudget() { return new Budget(); }\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert missing_import_errors(result) == []


def test_typescript_dot_slash_import_satisfies_sibling_manifest_path(project):
    manifest_path = write_manifest(
        project,
        "add-page.manifest.yaml",
        """schema: "2"
goal: "Add page"
files:
  create:
    - path: src/pages/BudgetPage.ts
      artifacts:
        - kind: function
          name: BudgetPage
      imports:
        - src/pages/utils
validate:
  - pytest tests/ -v
""",
    )
    write_source(
        project,
        "src/pages/BudgetPage.ts",
        'import { helper } from "./utils";\n\n'
        "export function BudgetPage() { return helper(); }\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert missing_import_errors(result) == []


def test_typescript_package_import_matches_exact_required_import(project):
    manifest_path = write_manifest(
        project,
        "add-page.manifest.yaml",
        """schema: "2"
goal: "Add page"
files:
  create:
    - path: src/pages/BudgetPage.ts
      artifacts:
        - kind: function
          name: BudgetPage
      imports:
        - react
validate:
  - pytest tests/ -v
""",
    )
    write_source(
        project,
        "src/pages/BudgetPage.ts",
        'import React from "react";\n\n'
        'export function BudgetPage() { return React.createElement("div"); }\n',
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert missing_import_errors(result) == []


def test_typescript_relative_import_with_extension_matches_extensionless_manifest_path(
    project,
):
    manifest_path = write_manifest(
        project,
        "add-page.manifest.yaml",
        """schema: "2"
goal: "Add page"
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
        'import { Budget } from "../models/Budget.ts";\n\n'
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


def test_commonjs_package_require_matches_exact_required_import(project):
    manifest_path = write_manifest(
        project,
        "add-util.manifest.yaml",
        """schema: "2"
goal: "Add util"
files:
  create:
    - path: src/utils/helper.js
      artifacts:
        - kind: function
          name: helper
      imports:
        - lodash
validate:
  - pytest tests/ -v
""",
    )
    write_source(
        project,
        "src/utils/helper.js",
        'const _ = require("lodash");\n\n'
        'function helper() { return _.get({}, "a"); }\n'
        "module.exports = { helper };\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert missing_import_errors(result) == []


def test_typescript_reexport_from_satisfies_manifest_path(project):
    manifest_path = write_manifest(
        project,
        "add-index.manifest.yaml",
        """schema: "2"
goal: "Add barrel export"
files:
  create:
    - path: src/index.ts
      artifacts:
        - kind: function
          name: barrel
      imports:
        - src/utils
validate:
  - pytest tests/ -v
""",
    )
    write_source(
        project,
        "src/index.ts",
        'export { helper } from "./utils";\n\n' "export function barrel() {}\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert missing_import_errors(result) == []


def test_typescript_namespace_import_matches_local_binding_name(project):
    manifest_path = write_manifest(
        project,
        "add-page.manifest.yaml",
        """schema: "2"
goal: "Add page"
files:
  create:
    - path: src/pages/BudgetPage.ts
      artifacts:
        - kind: function
          name: BudgetPage
      imports:
        - Models
validate:
  - pytest tests/ -v
""",
    )
    write_source(
        project,
        "src/pages/BudgetPage.ts",
        'import * as Models from "../models";\n\n'
        "export function BudgetPage() { return Models; }\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert missing_import_errors(result) == []


def test_typescript_multiline_named_import_text_fallback_satisfies_manifest_path(
    project, monkeypatch
):
    imports_module = sys.modules["maid_runner.core._js_ts_imports"]
    monkeypatch.setattr(
        imports_module,
        "_collect_required_imports_with_tree_sitter",
        lambda source, file_path: None,
    )
    monkeypatch.setattr(
        imports_module,
        "_collect_import_modules_with_tree_sitter",
        lambda source, file_path: None,
    )
    manifest_path = write_manifest(
        project,
        "add-page.manifest.yaml",
        """schema: "2"
goal: "Add page"
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
        'import {\n  Budget,\n} from "../models/Budget";\n\n'
        "export function BudgetPage() { return new Budget(); }\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert missing_import_errors(result) == []


def test_typescript_root_relative_escape_does_not_satisfy_project_local_import(
    project,
):
    manifest_path = write_manifest(
        project,
        "add-app.manifest.yaml",
        """schema: "2"
goal: "Add app"
files:
  create:
    - path: app.ts
      artifacts:
        - kind: function
          name: app
      imports:
        - outside/module
validate:
  - pytest tests/ -v
""",
    )
    write_source(
        project,
        "app.ts",
        'import { X } from "../outside/module";\n\n'
        "export function app() { return X; }\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
    import_errors = missing_import_errors(result)

    assert len(import_errors) == 1
    assert "outside/module" in import_errors[0].message


def test_typescript_bare_tsconfig_alias_satisfies_manifest_path(project):
    write_source(
        project,
        "tsconfig.json",
        json.dumps(
            {
                "compilerOptions": {
                    "baseUrl": ".",
                    "paths": {"models": ["src/models/index"]},
                }
            }
        ),
    )
    write_source(project, "src/models/index.ts", "export class Budget {}\n")
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
        - src/models
validate:
  - pytest tests/ -v
""",
    )
    write_source(
        project,
        "src/pages/BudgetPage.ts",
        'import { Budget } from "models";\n\n'
        "export function BudgetPage() { return new Budget(); }\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert missing_import_errors(result) == []
