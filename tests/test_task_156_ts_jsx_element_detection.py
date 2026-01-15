"""Behavioral tests for task-156: JSX element detection in TypeScript behavioral validation.

Goal: Enhance TypeScript behavioral validation to detect JSX element usage
as function calls for React functional components.

When a React component is rendered as a JSX element like <Admin /> or <Admin>...</Admin>,
it should be detected as a function call in behavioral validation.
"""

import tempfile
import os
from maid_runner.validators.typescript_validator import TypeScriptValidator


def _create_temp_tsx_file(tsx_code: bytes):
    """Helper to create temporary TSX file."""
    f = tempfile.NamedTemporaryFile(suffix=".tsx", delete=False)
    f.write(tsx_code)
    f.flush()
    f.close()
    return f.name


class TestJsxElementDetectionBehavior:
    """Test that JSX elements are detected as function usage in behavioral validation."""

    def test_jsx_self_closing_element_detected_as_function_usage(self):
        """JSX self-closing elements like <Admin /> should be detected as function calls."""
        tsx_code = b"""
import { Admin } from './Admin';
import { render } from '@testing-library/react';

render(<Admin />);
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "behavioral")
            assert (
                "Admin" in artifacts["used_functions"]
            ), "JSX self-closing element <Admin /> should be detected as function usage"
        finally:
            os.unlink(filepath)

    def test_jsx_opening_element_detected_as_function_usage(self):
        """JSX opening elements like <Container>...</Container> should be detected as function calls."""
        tsx_code = b"""
import { Container } from './Container';
import { render } from '@testing-library/react';

render(<Container>Hello World</Container>);
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "behavioral")
            assert (
                "Container" in artifacts["used_functions"]
            ), "JSX opening element <Container> should be detected as function usage"
        finally:
            os.unlink(filepath)

    def test_nested_jsx_elements_all_detected(self):
        """Nested JSX elements should all be detected as function calls."""
        tsx_code = b"""
import { Layout, Header, Content } from './components';
import { render } from '@testing-library/react';

render(
    <Layout>
        <Header />
        <Content>Hello</Content>
    </Layout>
);
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "behavioral")
            assert (
                "Layout" in artifacts["used_functions"]
            ), "Parent JSX element <Layout> should be detected"
            assert (
                "Header" in artifacts["used_functions"]
            ), "Nested self-closing JSX element <Header /> should be detected"
            assert (
                "Content" in artifacts["used_functions"]
            ), "Nested JSX element <Content> should be detected"
        finally:
            os.unlink(filepath)

    def test_jsx_element_with_props_detected(self):
        """JSX elements with props should be detected as function calls."""
        tsx_code = b"""
import { Button } from './Button';
import { render } from '@testing-library/react';

render(<Button variant="primary" disabled>Click me</Button>);
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "behavioral")
            assert (
                "Button" in artifacts["used_functions"]
            ), "JSX element with props should be detected as function usage"
        finally:
            os.unlink(filepath)

    def test_jsx_fragment_children_detected(self):
        """JSX elements inside fragments should be detected."""
        tsx_code = b"""
import { ComponentA, ComponentB } from './components';
import { render } from '@testing-library/react';

render(
    <>
        <ComponentA />
        <ComponentB />
    </>
);
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "behavioral")
            assert (
                "ComponentA" in artifacts["used_functions"]
            ), "JSX element inside fragment should be detected"
            assert (
                "ComponentB" in artifacts["used_functions"]
            ), "JSX element inside fragment should be detected"
        finally:
            os.unlink(filepath)


class TestExtractJsxComponentUsageMethod:
    """Test the _extract_jsx_component_usage method directly."""

    def test_extract_jsx_component_usage_returns_set(self):
        """_extract_jsx_component_usage should return a set of component names."""
        tsx_code = b"<Admin />;"
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            result = validator._extract_jsx_component_usage(tree, source_code)
            assert isinstance(
                result, set
            ), "_extract_jsx_component_usage should return a set"
            assert "Admin" in result, "Admin should be in the extracted components"
        finally:
            os.unlink(filepath)

    def test_extract_jsx_component_usage_excludes_html_elements(self):
        """_extract_jsx_component_usage should exclude lowercase HTML elements."""
        tsx_code = b"""
<div>
    <Admin />
    <span>Hello</span>
    <UserProfile />
</div>
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            result = validator._extract_jsx_component_usage(tree, source_code)
            assert "Admin" in result, "Custom component Admin should be detected"
            assert (
                "UserProfile" in result
            ), "Custom component UserProfile should be detected"
            assert (
                "div" not in result
            ), "HTML element div should NOT be detected as component"
            assert (
                "span" not in result
            ), "HTML element span should NOT be detected as component"
        finally:
            os.unlink(filepath)

    def test_extract_jsx_component_usage_empty_file(self):
        """_extract_jsx_component_usage should return empty set for file without JSX."""
        ts_code = b"const x = 1;"
        # Use .ts extension for non-JSX file
        f = tempfile.NamedTemporaryFile(suffix=".ts", delete=False)
        f.write(ts_code)
        f.flush()
        f.close()
        filepath = f.name
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            result = validator._extract_jsx_component_usage(tree, source_code)
            assert isinstance(
                result, set
            ), "_extract_jsx_component_usage should return a set"
            assert len(result) == 0, "File without JSX should return empty set"
        finally:
            os.unlink(filepath)


class TestBehavioralValidationIntegration:
    """Test that JSX detection integrates properly with behavioral validation."""

    def test_behavioral_mode_includes_jsx_in_used_functions(self):
        """Behavioral mode should include JSX components in used_functions."""
        tsx_code = b"""
import { describe, it } from 'vitest';
import { render } from '@testing-library/react';
import { Admin } from '../src/pages/Admin';

describe('Admin', () => {
    it('should render', () => {
        render(<Admin />);
    });
});
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "behavioral")
            assert (
                "Admin" in artifacts["used_functions"]
            ), "JSX component rendered in test should be detected in behavioral mode"
        finally:
            os.unlink(filepath)

    def test_jsx_and_regular_function_calls_both_detected(self):
        """Both JSX elements and regular function calls should be detected."""
        tsx_code = b"""
import { Admin } from './Admin';
import { formatDate } from './utils';
import { render } from '@testing-library/react';

const formatted = formatDate(new Date());
render(<Admin />);
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "behavioral")
            assert (
                "formatDate" in artifacts["used_functions"]
            ), "Regular function call should be detected"
            assert (
                "Admin" in artifacts["used_functions"]
            ), "JSX component should be detected"
        finally:
            os.unlink(filepath)

    def test_dynamic_import_with_jsx_usage(self):
        """JSX usage should be detected even with dynamic imports."""
        tsx_code = b"""
import { describe, it } from 'vitest';
import { render } from '@testing-library/react';

describe('Admin', () => {
    it('should render', async () => {
        const { Admin } = await import('../src/pages/Admin');
        render(<Admin />);
    });
});
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "behavioral")
            assert (
                "Admin" in artifacts["used_functions"]
            ), "JSX component from dynamic import should be detected"
        finally:
            os.unlink(filepath)


class TestTypeofExpressionDetection:
    """Test that typeof expressions are correctly detected.

    This tests the fix for typeof detection which uses unary_expression
    with a typeof child in tree-sitter-typescript AST.
    """

    def test_typeof_in_expect_detects_function(self):
        """typeof X in expect() should detect X as a used function."""
        tsx_code = b"""
import { Dialog } from '@/components/ui/dialog';

expect(typeof Dialog).toBe('function');
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "behavioral")
            assert (
                "Dialog" in artifacts["used_functions"]
            ), "typeof Dialog should detect Dialog as a used function"
        finally:
            os.unlink(filepath)

    def test_multiple_typeof_expressions(self):
        """Multiple typeof expressions should all be detected."""
        tsx_code = b"""
import { Dialog, DialogContent, DialogHeader } from '@/components/ui/dialog';

expect(typeof Dialog).toBe('function');
expect(typeof DialogContent).toBe('function');
expect(typeof DialogHeader).toBe('function');
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "behavioral")
            assert "Dialog" in artifacts["used_functions"]
            assert "DialogContent" in artifacts["used_functions"]
            assert "DialogHeader" in artifacts["used_functions"]
        finally:
            os.unlink(filepath)

    def test_typeof_and_jsx_both_detected(self):
        """Both typeof and JSX patterns should be detected together."""
        tsx_code = b"""
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { render } from '@testing-library/react';

expect(typeof Dialog).toBe('function');
render(<DialogContent>Hello</DialogContent>);
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "behavioral")
            assert (
                "Dialog" in artifacts["used_functions"]
            ), "typeof pattern should be detected"
            assert (
                "DialogContent" in artifacts["used_functions"]
            ), "JSX pattern should be detected"
        finally:
            os.unlink(filepath)

    def test_typeof_on_member_expression_detected(self):
        """typeof on member expression like typeof result.current.refetch should detect refetch."""
        tsx_code = b"""
expect(typeof result.current.refetch).toBe('function');
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "behavioral")
            assert (
                "refetch" in artifacts["used_functions"]
            ), "typeof on member expression should detect final property"
        finally:
            os.unlink(filepath)

    def test_typeof_on_nested_member_expression_detected(self):
        """typeof on deeply nested member expression should detect final property."""
        tsx_code = b"""
expect(typeof obj.prop1.prop2.targetFunction).toBe('function');
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "behavioral")
            assert (
                "targetFunction" in artifacts["used_functions"]
            ), "typeof on nested member expression should detect final property"
        finally:
            os.unlink(filepath)


class TestTypeAnnotationUsageDetection:
    """Test that type annotations are detected as type/class usage.

    This enables behavioral validation for TypeScript types and interfaces,
    where tests verify values conform to type shapes.
    """

    def test_simple_type_annotation_detected(self):
        """Simple type annotation like `const x: MyType = ...` should be detected."""
        tsx_code = b"""
import type { ActiveChat } from './Chat';

const chat: ActiveChat = { type: 'direct' };
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "behavioral")
            assert (
                "ActiveChat" in artifacts["used_classes"]
            ), "Type annotation should be detected in used_classes"
        finally:
            os.unlink(filepath)

    def test_multiple_type_annotations_detected(self):
        """Multiple type annotations should all be detected."""
        tsx_code = b"""
import type { UserType, ChatMessage, RoomConfig } from './types';

const user: UserType = { name: 'John' };
const message: ChatMessage = { text: 'Hello' };
const config: RoomConfig = { maxUsers: 10 };
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "behavioral")
            assert "UserType" in artifacts["used_classes"]
            assert "ChatMessage" in artifacts["used_classes"]
            assert "RoomConfig" in artifacts["used_classes"]
        finally:
            os.unlink(filepath)

    def test_generic_type_annotation_detected(self):
        """Generic types like Array<Item> should detect the inner type."""
        tsx_code = b"""
import type { Task } from './types';

const tasks: Array<Task> = [];
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "behavioral")
            assert (
                "Task" in artifacts["used_classes"]
            ), "Type inside generic should be detected"
        finally:
            os.unlink(filepath)

    def test_builtin_types_excluded(self):
        """Built-in types like string, number, Array should not be detected."""
        tsx_code = b"""
const name: string = 'John';
const age: number = 30;
const items: Array<string> = [];
const data: Record<string, number> = {};
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "behavioral")
            assert "string" not in artifacts["used_classes"]
            assert "number" not in artifacts["used_classes"]
            assert "Array" not in artifacts["used_classes"]
            assert "Record" not in artifacts["used_classes"]
        finally:
            os.unlink(filepath)

    def test_union_type_annotation_detected(self):
        """Union types should detect all custom types."""
        tsx_code = b"""
import type { DirectChat, RoomChat } from './types';

const chat: DirectChat | RoomChat = { type: 'direct' };
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "behavioral")
            assert "DirectChat" in artifacts["used_classes"]
            assert "RoomChat" in artifacts["used_classes"]
        finally:
            os.unlink(filepath)

    def test_type_annotation_in_test_context(self):
        """Type annotations in test files should be detected."""
        tsx_code = b"""
import type { ActiveChat } from './Chat';
import { describe, it, expect } from 'vitest';

describe('ActiveChat type', () => {
  it('should accept direct chat shape', () => {
    const directChat: ActiveChat = {
      type: 'direct',
      recipientId: '123'
    };
    expect(directChat.type).toBe('direct');
  });
});
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "behavioral")
            assert (
                "ActiveChat" in artifacts["used_classes"]
            ), "Type annotation in test should be detected"
        finally:
            os.unlink(filepath)


class TestFactoryMethodPatternDetection:
    """Test that factory method patterns map variables to classes.

    This enables behavioral validation for singleton and factory patterns,
    where instances are obtained via static methods like getInstance() or create().
    """

    def test_singleton_get_instance_maps_variable_to_class(self):
        """const service = ClassName.getInstance() should map service to ClassName."""
        tsx_code = b"""
import { PushNotificationService } from './services';

const service = PushNotificationService.getInstance();
service.checkPlatformCompatibility();
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            mapping = validator._extract_variable_to_class_mapping(tree, source_code)
            assert (
                "service" in mapping
            ), "Variable assigned from static method should be in mapping"
            assert (
                mapping["service"] == "PushNotificationService"
            ), "service should map to PushNotificationService"
        finally:
            os.unlink(filepath)

    def test_factory_create_maps_variable_to_class(self):
        """const instance = Factory.create() should map instance to Factory."""
        tsx_code = b"""
import { UserFactory } from './factories';

const user = UserFactory.create();
user.getName();
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            mapping = validator._extract_variable_to_class_mapping(tree, source_code)
            assert (
                "user" in mapping
            ), "Variable assigned from factory method should be in mapping"
            assert mapping["user"] == "UserFactory", "user should map to UserFactory"
        finally:
            os.unlink(filepath)

    def test_method_calls_on_factory_created_instance_detected(self):
        """Method calls on factory-created instances should be detected."""
        tsx_code = b"""
import { PushNotificationService } from './services';

const service = PushNotificationService.getInstance();
service.checkPlatformCompatibility();
service.subscribe();
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "behavioral")
            assert (
                "PushNotificationService" in artifacts["used_methods"]
            ), "Class should be in used_methods"
            assert (
                "checkPlatformCompatibility"
                in artifacts["used_methods"]["PushNotificationService"]
            ), "checkPlatformCompatibility should be detected as method on PushNotificationService"
            assert (
                "subscribe" in artifacts["used_methods"]["PushNotificationService"]
            ), "subscribe should be detected as method on PushNotificationService"
        finally:
            os.unlink(filepath)

    def test_multiple_factory_patterns_detected(self):
        """Multiple factory patterns should all be detected."""
        tsx_code = b"""
import { ServiceA, ServiceB } from './services';

const a = ServiceA.getInstance();
const b = ServiceB.create();
a.methodA();
b.methodB();
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            mapping = validator._extract_variable_to_class_mapping(tree, source_code)
            assert mapping.get("a") == "ServiceA"
            assert mapping.get("b") == "ServiceB"
        finally:
            os.unlink(filepath)

    def test_lowercase_static_methods_not_detected_as_classes(self):
        """Static methods on lowercase objects should not map to classes."""
        tsx_code = b"""
const result = utils.doSomething();
"""
        filepath = _create_temp_tsx_file(tsx_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            mapping = validator._extract_variable_to_class_mapping(tree, source_code)
            assert (
                "result" not in mapping
            ), "lowercase object method calls should not map to classes"
        finally:
            os.unlink(filepath)
