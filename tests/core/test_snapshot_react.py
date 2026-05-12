"""React snapshot companion-file tracking tests."""

from __future__ import annotations

import textwrap

from maid_runner.core.snapshot import generate_snapshot


def test_react_component_snapshot_tracks_css_module_import_as_read_file(tmp_path) -> None:
    component = tmp_path / "src/components/Button.tsx"
    component.parent.mkdir(parents=True)
    component.write_text(
        textwrap.dedent(
            """\
            import styles from './Button.module.css';

            export function Button(): JSX.Element {
              return <button className={styles.root}>Save</button>;
            }
            """
        )
    )
    (component.parent / "Button.module.css").write_text(".root { color: red; }\n")

    manifest = generate_snapshot(component, project_root=tmp_path)

    assert manifest.files_read == ("src/components/Button.module.css",)


def test_react_component_snapshot_tracks_side_effect_stylesheet_import_as_read_file(
    tmp_path,
) -> None:
    component = tmp_path / "src/components/App.tsx"
    component.parent.mkdir(parents=True)
    component.write_text(
        textwrap.dedent(
            """\
            import './App.css';

            export function App(): JSX.Element {
              return <main />;
            }
            """
        )
    )
    (component.parent / "App.css").write_text("main { display: block; }\n")

    manifest = generate_snapshot(component, project_root=tmp_path)

    assert manifest.files_read == ("src/components/App.css",)


def test_react_component_snapshot_tracks_static_asset_import_as_read_file(tmp_path) -> None:
    component = tmp_path / "src/components/Logo.tsx"
    component.parent.mkdir(parents=True)
    component.write_text(
        textwrap.dedent(
            """\
            import logoUrl from '../assets/logo.svg';

            export function Logo(): JSX.Element {
              return <img src={logoUrl} alt="" />;
            }
            """
        )
    )
    assets = tmp_path / "src/assets"
    assets.mkdir()
    (assets / "logo.svg").write_text("<svg />\n")

    manifest = generate_snapshot(component, project_root=tmp_path)

    assert manifest.files_read == ("src/assets/logo.svg",)


def test_react_component_snapshot_ignores_package_and_missing_asset_imports(
    tmp_path,
) -> None:
    component = tmp_path / "src/components/Card.tsx"
    component.parent.mkdir(parents=True)
    component.write_text(
        textwrap.dedent(
            """\
            import React from 'react';
            import '@scope/theme/base.css';
            import missing from './missing.svg';
            import { helper } from './helper';

            export function Card(): JSX.Element {
              return <section>{helper()}</section>;
            }
            """
        )
    )
    (component.parent / "helper.ts").write_text("export function helper() { return null; }\n")

    manifest = generate_snapshot(component, project_root=tmp_path)

    assert manifest.files_read == ()
