from maid_runner.validators.typescript_validator import TypeScriptValidator

# =============================================================================
# SECTION 13: JSX/TSX Support
# =============================================================================


class TestJSXTSXSupport:
    """Test JSX/TSX file handling for React components."""

    def test_react_class_component(self, tmp_path):
        """Must detect React class components."""
        test_file = tmp_path / "Component.tsx"
        test_file.write_text(
            """
class MyComponent extends React.Component {
    render() {
        return <div>Hello</div>;
    }
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "MyComponent" in result["found_classes"]
        assert "MyComponent" in result["found_methods"]
        assert "render" in result["found_methods"]["MyComponent"]

    def test_react_functional_component(self, tmp_path):
        """Must detect React functional components."""
        test_file = tmp_path / "Component.tsx"
        test_file.write_text(
            """
const MyComponent = () => {
    return <div>Hello</div>;
};
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "MyComponent" in result["found_functions"]

    def test_react_functional_component_with_props(self, tmp_path):
        """Must detect React functional components with props."""
        test_file = tmp_path / "Component.tsx"
        test_file.write_text(
            """
const Greeting = (props: { name: string }) => {
    return <div>Hello {props.name}</div>;
};
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Greeting" in result["found_functions"]

    def test_react_component_with_hooks(self, tmp_path):
        """Must detect React components using hooks."""
        test_file = tmp_path / "Component.tsx"
        test_file.write_text(
            """
const Counter = () => {
    const [count, setCount] = useState(0);
    return <button onClick={() => setCount(count + 1)}>{count}</button>;
};
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Counter" in result["found_functions"]
