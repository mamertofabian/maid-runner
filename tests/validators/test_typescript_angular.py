"""Angular TypeScript artifact characterization tests."""

from __future__ import annotations

from maid_runner.core.types import ArtifactKind
from maid_runner.validators.typescript import TypeScriptValidator


def test_angular_component_metadata_preserves_class_fields_and_methods() -> None:
    source = """import { Component, signal } from '@angular/core';

@Component({
  selector: 'app-user-card',
  templateUrl: './user-card.component.html',
})
export class UserCardComponent {
  readonly userId: string = '42';

  displayName(): string {
    return 'Ada';
  }
}
"""

    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/app/user-card/user-card.component.ts"
    )
    names = {artifact.name for artifact in result.artifacts}

    component = next(a for a in result.artifacts if a.name == "UserCardComponent")
    user_id = next(a for a in result.artifacts if a.name == "userId")
    display_name = next(a for a in result.artifacts if a.name == "displayName")

    assert result.errors == []
    assert component.kind == ArtifactKind.CLASS
    assert user_id.kind == ArtifactKind.ATTRIBUTE
    assert user_id.of == "UserCardComponent"
    assert user_id.type_annotation == "string"
    assert display_name.kind == ArtifactKind.METHOD
    assert display_name.of == "UserCardComponent"
    assert display_name.returns == "string"
    assert "Component" not in names


def test_angular_service_directive_and_pipe_decorators_do_not_become_artifacts() -> (
    None
):
    source = """import { Directive, Injectable, Pipe, PipeTransform } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class UserService {
  fetchUser(): User {
    return {} as User;
  }
}

@Directive({ selector: '[appHighlight]' })
export class HighlightDirective {
  enabled = true;
}

@Pipe({ name: 'initials' })
export class InitialsPipe implements PipeTransform {
  transform(value: string): string {
    return value.slice(0, 1);
  }
}
"""

    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/app/shared/angular-types.ts"
    )
    names = {artifact.name for artifact in result.artifacts}

    assert result.errors == []
    assert {"UserService", "HighlightDirective", "InitialsPipe"} <= names
    assert {"fetchUser", "enabled", "transform"} <= names
    assert {"Injectable", "Directive", "Pipe"} - names == {
        "Injectable",
        "Directive",
        "Pipe",
    }


def test_angular_signal_style_input_output_fields_remain_component_attributes() -> None:
    source = """import { Component, input, output } from '@angular/core';

@Component({
  selector: 'app-counter',
  template: '<button></button>',
})
export class CounterComponent {
  count = input.required<number>();
  label = input<string>('Count');
  changed = output<number>();
}
"""

    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/app/counter/counter.component.ts"
    )

    fields = {
        artifact.name: artifact
        for artifact in result.artifacts
        if artifact.of == "CounterComponent"
    }

    assert result.errors == []
    assert fields["count"].kind == ArtifactKind.ATTRIBUTE
    assert fields["label"].kind == ArtifactKind.ATTRIBUTE
    assert fields["changed"].kind == ArtifactKind.ATTRIBUTE
