"""Angular required-import validation characterization tests."""

from __future__ import annotations

import pytest

from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine


@pytest.fixture()
def project(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    return tmp_path


def _write_manifest(manifests_dir, name, content):
    path = manifests_dir / name
    path.write_text(content)
    return path


def _write_source(project_dir, rel_path, content):
    path = project_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _write_component_test(
    project,
    component_name="UserCardComponent",
    component_module="../src/app/user-card/user-card.component",
):
    _write_source(
        project,
        "tests/user-card.component.spec.ts",
        f"""import {{ {component_name} }} from '{component_module}';

test('component can be referenced', () => {{
  expect({component_name}).toBeDefined();
}});
""",
    )


def test_angular_standalone_component_static_import_satisfies_required_import(
    project,
) -> None:
    manifest_path = _write_manifest(
        project / "manifests",
        "add-dashboard.manifest.yaml",
        """schema: "2"
goal: "Add dashboard component"
files:
  create:
    - path: src/app/dashboard/dashboard.component.ts
      artifacts:
        - kind: class
          name: DashboardComponent
      imports:
        - src/app/user-card/user-card.component
  read:
    - tests/user-card.component.spec.ts
validate:
  - pytest tests/ -v
""",
    )
    _write_source(
        project,
        "src/app/dashboard/dashboard.component.ts",
        """import { Component } from '@angular/core';
import { UserCardComponent } from '../user-card/user-card.component';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [UserCardComponent],
  template: '<app-user-card />',
})
export class DashboardComponent {}
""",
    )
    _write_component_test(
        project,
        "DashboardComponent",
        "../src/app/dashboard/dashboard.component",
    )

    result = ValidationEngine(project_root=project).validate(
        manifest_path, mode=ValidationMode.IMPLEMENTATION
    )

    assert result.success is True
    assert not any(e.code == ErrorCode.MISSING_REQUIRED_IMPORT for e in result.errors)


def test_angular_lazy_route_dynamic_import_satisfies_required_import(project) -> None:
    manifest_path = _write_manifest(
        project / "manifests",
        "add-routes.manifest.yaml",
        """schema: "2"
goal: "Add lazy route"
files:
  create:
    - path: src/app/app.routes.ts
      artifacts:
        - kind: attribute
          name: routes
      imports:
        - src/app/admin/admin.routes
  read:
    - tests/app.routes.spec.ts
validate:
  - pytest tests/ -v
""",
    )
    _write_source(
        project,
        "src/app/app.routes.ts",
        """import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: 'admin',
    loadChildren: () => import('./admin/admin.routes').then((m) => m.ADMIN_ROUTES),
  },
];
""",
    )
    _write_source(
        project,
        "tests/app.routes.spec.ts",
        """import { routes } from '../src/app/app.routes';

test('routes can be referenced', () => {
  expect(routes).toBeDefined();
});
""",
    )

    result = ValidationEngine(project_root=project).validate(
        manifest_path, mode=ValidationMode.IMPLEMENTATION
    )

    assert result.success is True
    assert not any(e.code == ErrorCode.MISSING_REQUIRED_IMPORT for e in result.errors)


def test_angular_lazy_route_rejects_missing_required_import(project) -> None:
    manifest_path = _write_manifest(
        project / "manifests",
        "add-routes.manifest.yaml",
        """schema: "2"
goal: "Add lazy route"
files:
  create:
    - path: src/app/app.routes.ts
      artifacts:
        - kind: attribute
          name: routes
      imports:
        - src/app/admin/admin.routes
  read:
    - tests/app.routes.spec.ts
validate:
  - pytest tests/ -v
""",
    )
    _write_source(
        project,
        "src/app/app.routes.ts",
        """import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: 'admin', component: AdminShellComponent },
];
""",
    )
    _write_source(
        project,
        "tests/app.routes.spec.ts",
        """import { routes } from '../src/app/app.routes';

test('routes can be referenced', () => {
  expect(routes).toBeDefined();
});
""",
    )

    result = ValidationEngine(project_root=project).validate(
        manifest_path, mode=ValidationMode.IMPLEMENTATION
    )

    assert any(e.code == ErrorCode.MISSING_REQUIRED_IMPORT for e in result.errors)


def test_angular_package_import_does_not_satisfy_project_local_required_import(
    project,
) -> None:
    manifest_path = _write_manifest(
        project / "manifests",
        "add-widget.manifest.yaml",
        """schema: "2"
goal: "Add widget"
files:
  create:
    - path: src/app/widget/widget.component.ts
      artifacts:
        - kind: class
          name: WidgetComponent
      imports:
        - src/app/core
  read:
    - tests/widget.component.spec.ts
validate:
  - pytest tests/ -v
""",
    )
    _write_source(
        project,
        "src/app/widget/widget.component.ts",
        """import { Component } from '@angular/core';

@Component({
  selector: 'app-widget',
  template: '<span></span>',
})
export class WidgetComponent {}
""",
    )
    _write_source(
        project,
        "tests/widget.component.spec.ts",
        """import { WidgetComponent } from '../src/app/widget/widget.component';

test('widget can be referenced', () => {
  expect(WidgetComponent).toBeDefined();
});
""",
    )

    result = ValidationEngine(project_root=project).validate(
        manifest_path, mode=ValidationMode.IMPLEMENTATION
    )

    assert any(e.code == ErrorCode.MISSING_REQUIRED_IMPORT for e in result.errors)
