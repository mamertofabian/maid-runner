"""Angular snapshot companion-file tracking tests."""

from __future__ import annotations

import textwrap

from maid_runner.core.snapshot import generate_snapshot


def test_angular_component_snapshot_tracks_template_url_as_read_file(tmp_path) -> None:
    component = tmp_path / "src/app/user-card/user-card.component.ts"
    component.parent.mkdir(parents=True)
    component.write_text(
        textwrap.dedent(
            """\
            import { Component } from '@angular/core';

            @Component({
              selector: 'app-user-card',
              templateUrl: './user-card.component.html',
            })
            export class UserCardComponent {}
            """
        )
    )
    (component.parent / "user-card.component.html").write_text("<p>User</p>\n")

    manifest = generate_snapshot(component, project_root=tmp_path)

    assert manifest.files_read == ("src/app/user-card/user-card.component.html",)


def test_angular_component_snapshot_tracks_style_urls_as_read_files(tmp_path) -> None:
    component = tmp_path / "src/app/user-card/user-card.component.ts"
    component.parent.mkdir(parents=True)
    component.write_text(
        textwrap.dedent(
            """\
            import { Component } from '@angular/core';

            @Component({
              selector: 'app-user-card',
              templateUrl: './missing.html',
              styleUrl: './user-card.component.css',
              styleUrls: ['./user-card.component.scss', "../shared/card.scss"],
            })
            export class UserCardComponent {}
            """
        )
    )
    (component.parent / "user-card.component.css").write_text(":host { display: block; }\n")
    (component.parent / "user-card.component.scss").write_text(":host { color: red; }\n")
    shared = tmp_path / "src/app/shared"
    shared.mkdir()
    (shared / "card.scss").write_text(".card { padding: 1rem; }\n")

    manifest = generate_snapshot(component, project_root=tmp_path)

    assert manifest.files_read == (
        "src/app/user-card/user-card.component.css",
        "src/app/user-card/user-card.component.scss",
        "src/app/shared/card.scss",
    )


def test_angular_component_snapshot_ignores_inline_template_and_styles_for_companion_tracking(
    tmp_path,
) -> None:
    component = tmp_path / "src/app/inline/inline.component.ts"
    component.parent.mkdir(parents=True)
    component.write_text(
        textwrap.dedent(
            """\
            import { Component } from '@angular/core';

            @Component({
              selector: 'app-inline',
              template: '<p>Inline</p>',
              styles: [':host { display: block; }'],
            })
            export class InlineComponent {}
            """
        )
    )

    manifest = generate_snapshot(component, project_root=tmp_path)

    assert manifest.files_read == ()
