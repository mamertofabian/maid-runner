"""React required-import validation characterization tests."""

from __future__ import annotations

import pytest

from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine


@pytest.fixture()
def project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "manifests").mkdir()
    (tmp_path / "tests").mkdir()
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


def test_react_testing_library_rendered_component_satisfies_behavioral_artifact(
    project,
) -> None:
    manifest_path = _write_manifest(
        project / "manifests",
        "add-button.manifest.yaml",
        """schema: "2"
goal: "Add button"
files:
  create:
    - path: src/components/Button.tsx
      artifacts:
        - kind: function
          name: Button
  read:
    - tests/button.test.tsx
validate:
  - vitest run tests/button.test.tsx
""",
    )
    _write_source(
        project,
        "tests/button.test.tsx",
        """import { render, screen } from '@testing-library/react';
import { Button } from '../src/components/Button';

test('renders button label', () => {
  render(<Button label="Save" />);
  expect(screen.getByText('Save')).toBeDefined();
});
""",
    )

    result = ValidationEngine(project_root=project).validate(
        manifest_path, mode=ValidationMode.BEHAVIORAL
    )

    assert result.success is True


def test_react_barrel_component_import_satisfies_required_import(project) -> None:
    manifest_path = _write_manifest(
        project / "manifests",
        "add-page.manifest.yaml",
        """schema: "2"
goal: "Add page"
files:
  create:
    - path: src/pages/HomePage.tsx
      artifacts:
        - kind: function
          name: HomePage
      imports:
        - src/components
  read:
    - tests/home-page.test.tsx
validate:
  - vitest run tests/home-page.test.tsx
""",
    )
    _write_source(
        project,
        "src/pages/HomePage.tsx",
        """import { Button } from '../components';

export function HomePage(): JSX.Element {
  return <Button label="Home" />;
}
""",
    )
    _write_source(
        project,
        "tests/home-page.test.tsx",
        """import { HomePage } from '../src/pages/HomePage';

test('home page can be referenced', () => {
  expect(HomePage).toBeDefined();
});
""",
    )

    result = ValidationEngine(project_root=project).validate(
        manifest_path, mode=ValidationMode.IMPLEMENTATION
    )

    assert result.success is True
    assert not any(e.code == ErrorCode.MISSING_REQUIRED_IMPORT for e in result.errors)


def test_react_lazy_dynamic_import_satisfies_required_import(project) -> None:
    manifest_path = _write_manifest(
        project / "manifests",
        "add-lazy-page.manifest.yaml",
        """schema: "2"
goal: "Add lazy page"
files:
  create:
    - path: src/routes/AppRoutes.tsx
      artifacts:
        - kind: attribute
          name: LazyDashboard
      imports:
        - src/pages/Dashboard
  read:
    - tests/app-routes.test.tsx
validate:
  - vitest run tests/app-routes.test.tsx
""",
    )
    _write_source(
        project,
        "src/routes/AppRoutes.tsx",
        """import React from 'react';

export const LazyDashboard = React.lazy(() => import('../pages/Dashboard'));
""",
    )
    _write_source(
        project,
        "tests/app-routes.test.tsx",
        """import { LazyDashboard } from '../src/routes/AppRoutes';

test('lazy dashboard can be referenced', () => {
  expect(LazyDashboard).toBeDefined();
});
""",
    )

    result = ValidationEngine(project_root=project).validate(
        manifest_path, mode=ValidationMode.IMPLEMENTATION
    )

    assert result.success is True
    assert not any(e.code == ErrorCode.MISSING_REQUIRED_IMPORT for e in result.errors)


def test_react_path_alias_component_import_satisfies_required_import(project) -> None:
    (project / "tsconfig.json").write_text(
        """{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  }
}
"""
    )
    manifest_path = _write_manifest(
        project / "manifests",
        "add-card.manifest.yaml",
        """schema: "2"
goal: "Add card"
files:
  create:
    - path: src/features/CardHost.tsx
      artifacts:
        - kind: function
          name: CardHost
      imports:
        - src/components/Card
  read:
    - tests/card-host.test.tsx
validate:
  - vitest run tests/card-host.test.tsx
""",
    )
    _write_source(
        project,
        "src/features/CardHost.tsx",
        """import { Card } from '@/components/Card';

export function CardHost(): JSX.Element {
  return <Card />;
}
""",
    )
    _write_source(
        project,
        "src/components/Card.tsx",
        """export function Card(): JSX.Element {
  return <article />;
}
""",
    )
    _write_source(
        project,
        "tests/card-host.test.tsx",
        """import { CardHost } from '../src/features/CardHost';

test('card host can be referenced', () => {
  expect(CardHost).toBeDefined();
});
""",
    )

    result = ValidationEngine(project_root=project).validate(
        manifest_path, mode=ValidationMode.IMPLEMENTATION
    )

    assert result.success is True
    assert not any(e.code == ErrorCode.MISSING_REQUIRED_IMPORT for e in result.errors)


def test_react_css_module_import_satisfies_required_style_import(project) -> None:
    manifest_path = _write_manifest(
        project / "manifests",
        "add-styled-button.manifest.yaml",
        """schema: "2"
goal: "Add styled button"
files:
  create:
    - path: src/components/Button.tsx
      artifacts:
        - kind: function
          name: Button
      imports:
        - src/components/Button.module.css
  read:
    - tests/button.test.tsx
validate:
  - vitest run tests/button.test.tsx
""",
    )
    _write_source(
        project,
        "src/components/Button.tsx",
        """import styles from './Button.module.css';

export function Button(): JSX.Element {
  return <button className={styles.root}>Save</button>;
}
""",
    )
    _write_source(
        project,
        "tests/button.test.tsx",
        """import { Button } from '../src/components/Button';

test('button can be referenced', () => {
  expect(Button).toBeDefined();
});
""",
    )

    result = ValidationEngine(project_root=project).validate(
        manifest_path, mode=ValidationMode.IMPLEMENTATION
    )

    assert result.success is True
    assert not any(e.code == ErrorCode.MISSING_REQUIRED_IMPORT for e in result.errors)


def test_react_package_import_does_not_satisfy_project_local_required_import(
    project,
) -> None:
    manifest_path = _write_manifest(
        project / "manifests",
        "add-card.manifest.yaml",
        """schema: "2"
goal: "Add card"
files:
  create:
    - path: src/components/Card.tsx
      artifacts:
        - kind: function
          name: Card
      imports:
        - src/components/Button
validate:
  - vitest run
""",
    )
    _write_source(
        project,
        "src/components/Card.tsx",
        """import React from 'react';
import { render } from '@testing-library/react';

export function Card(): JSX.Element {
  return <section>{render}</section>;
}
""",
    )

    result = ValidationEngine(project_root=project).validate(
        manifest_path, mode=ValidationMode.IMPLEMENTATION
    )

    assert any(e.code == ErrorCode.MISSING_REQUIRED_IMPORT for e in result.errors)
