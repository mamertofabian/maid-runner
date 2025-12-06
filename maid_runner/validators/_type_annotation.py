"""Private module for AST type annotation extraction."""

import ast
from typing import Optional, Any

# Type string constants for parsing and normalization
_OPTIONAL_PREFIX = "Optional["
_UNION_PREFIX = "Union["
_BRACKET_OPEN = "["
_BRACKET_CLOSE = "]"


def _validate_extraction_inputs(node: Any, annotation_attr: str) -> None:
    """Validate inputs for type annotation extraction.

    Args:
        node: Node to validate
        annotation_attr: Attribute name to validate

    Raises:
        AttributeError: If node is None (for backward compatibility)
    """
    if node is None:
        raise AttributeError("Cannot extract type annotation from None node")

    if not isinstance(node, ast.AST):
        return  # Will return None from main function

    if not annotation_attr:
        return  # Will return None from main function


def _ast_to_type_string(node: Optional[ast.AST]) -> Optional[str]:
    """
    Convert an AST node to a type string representation.

    Handles various Python type hint syntaxes including:
    - Simple types (int, str, etc.)
    - Generic types (List[str], Dict[str, int])
    - Qualified names (typing.Optional)
    - Union types (str | None in Python 3.10+)
    - Forward references (string literals)

    Args:
        node: AST node representing a type annotation

    Returns:
        String representation of the type, or None if node is None
    """
    if node is None:
        return None

    # Use safe wrapper to handle any exceptions
    return _safe_ast_conversion(node)


def _safe_ast_conversion(node: ast.AST) -> Optional[str]:
    """Safely convert AST node to string with error handling.

    Args:
        node: AST node to convert

    Returns:
        String representation or None if conversion fails
    """
    try:
        # Dispatch based on node type
        if isinstance(node, ast.Name):
            return node.id

        if isinstance(node, ast.Constant):
            return str(node.value)

        if isinstance(node, ast.Subscript):
            return _handle_subscript_node(node)

        if isinstance(node, ast.Attribute):
            return _handle_attribute_node(node)

        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return _handle_union_operator(node)

        if isinstance(node, ast.Ellipsis):
            return "..."

        # Fallback to AST unparsing if available
        return _fallback_ast_unparse(node)

    except Exception:
        # Final safety net
        return _safe_str_conversion(node)


def _handle_subscript_node(node: ast.Subscript) -> str:
    """Handle generic type subscript nodes like List[str], Dict[str, int].

    Args:
        node: Subscript AST node

    Returns:
        String representation of the generic type
    """
    base = _ast_to_type_string(node.value)

    if isinstance(node.slice, ast.Tuple):
        # Multiple type arguments like Dict[str, int]
        args = [_ast_to_type_string(elt) for elt in node.slice.elts]
        return f"{base}{_BRACKET_OPEN}{', '.join(args)}{_BRACKET_CLOSE}"
    else:
        # Single type argument like List[str]
        arg = _ast_to_type_string(node.slice)
        return f"{base}{_BRACKET_OPEN}{arg}{_BRACKET_CLOSE}"


def _handle_attribute_node(node: ast.Attribute) -> str:
    """Handle qualified name nodes like typing.Optional.

    Args:
        node: Attribute AST node

    Returns:
        String representation of the qualified name
    """
    value = _ast_to_type_string(node.value)
    return f"{value}.{node.attr}" if value else node.attr


def _handle_union_operator(node: ast.BinOp) -> str:
    """Handle Union types using | operator (Python 3.10+).

    Args:
        node: BinOp AST node with BitOr operator

    Returns:
        String representation in Union[...] format
    """
    left = _ast_to_type_string(node.left)
    right = _ast_to_type_string(node.right)
    return f"{_UNION_PREFIX}{left}, {right}{_BRACKET_CLOSE}"


def _fallback_ast_unparse(node: ast.AST) -> Optional[str]:
    """Try to unparse AST node as fallback.

    Args:
        node: AST node to unparse

    Returns:
        Unparsed string or None if unparsing fails
    """
    try:
        return ast.unparse(node)
    except (AttributeError, TypeError):
        return str(node)


def _safe_str_conversion(node: Any) -> Optional[str]:
    """Safely convert any object to string.

    Args:
        node: Object to convert

    Returns:
        String representation or None if conversion fails
    """
    try:
        return str(node)
    except Exception:
        return None


def _extract_base_class_name(base: ast.AST) -> Optional[str]:
    """Extract base class name from various AST node types.

    Handles:
    - ast.Name: Simple inheritance like class Foo(Bar)
    - ast.Attribute: Qualified names like class Foo(module.Bar)
    - ast.Subscript: Parameterized types like class Foo(Generic[T])

    Args:
        base: AST node representing a base class

    Returns:
        String name of the base class, or None if extraction fails

    Examples:
        >>> # For: class Foo(Bar)
        >>> _extract_base_class_name(ast.Name(id='Bar'))
        'Bar'

        >>> # For: class Foo(Generic[T])
        >>> _extract_base_class_name(ast.Subscript(value=ast.Name(id='Generic'), ...))
        'Generic'

        >>> # For: class Foo(typing.Generic[T])
        >>> _extract_base_class_name(ast.Subscript(value=ast.Attribute(...), ...))
        'typing.Generic'
    """
    if isinstance(base, ast.Name):
        # Simple name: class Foo(Bar)
        return base.id

    elif isinstance(base, ast.Attribute):
        # Qualified name: class Foo(module.ClassName)
        parts = []
        current = base
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))

    elif isinstance(base, ast.Subscript):
        # Parameterized type: class Foo(Generic[T]) or class Foo(List[str])
        # Extract the base type from base.value
        if isinstance(base.value, ast.Name):
            # Simple generic: Generic[T]
            return base.value.id
        elif isinstance(base.value, ast.Attribute):
            # Qualified generic: typing.Generic[T]
            return _extract_base_class_name(base.value)

    return None
