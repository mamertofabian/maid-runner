"""Tests for maid_runner.core._type_compare - type normalization and comparison."""

import pytest

from maid_runner.core._type_compare import normalize_type, types_match


class TestNormalizeType:
    """Golden tests from 15-golden-tests.md section 5.1."""

    @pytest.mark.parametrize(
        "input_type,expected",
        [
            ("Optional[str]", "Union[None, str]"),
            ("str | None", "Union[None, str]"),
            ("Union[str, int]", "Union[int, str]"),
            ("Union[int, str, None]", "Union[None, int, str]"),
            ("Dict[str, int]", "Dict[str, int]"),
            ("Dict[str,int]", "Dict[str, int]"),
            ("List[ str ]", "List[str]"),
            ("Optional[Dict[str, int]]", "Union[Dict[str, int], None]"),
        ],
    )
    def test_normalization_rules(self, input_type, expected):
        assert normalize_type(input_type) == expected

    def test_simple_type_unchanged(self):
        assert normalize_type("str") == "str"
        assert normalize_type("int") == "int"

    def test_none_input(self):
        assert normalize_type(None) is None

    def test_empty_string(self):
        assert normalize_type("") == ""

    def test_whitespace_stripped(self):
        assert normalize_type("  str  ") == "str"

    def test_pep585_lowercase(self):
        # PEP 585: list[str] normalizes with lowercase preserved
        assert normalize_type("list[str]") == "list[str]"
        assert normalize_type("dict[str, int]") == "dict[str, int]"


class TestTypesMatch:
    """Golden tests from 15-golden-tests.md section 5.2."""

    @pytest.mark.parametrize(
        "manifest_type,impl_type,expected",
        [
            ("str", "str", True),
            ("Optional[str]", "str | None", True),
            ("Optional[str]", "Union[str, None]", True),
            ("Dict[str, int]", "Dict[str,int]", True),
            ("int", "str", False),
            ("Optional[str]", "str", False),
        ],
    )
    def test_comparison_cases(self, manifest_type, impl_type, expected):
        assert types_match(manifest_type, impl_type) is expected

    def test_none_manifest_matches_anything(self):
        """None (not specified) -> any type is acceptable."""
        assert types_match(None, "str") is True
        assert types_match(None, "int") is True
        assert types_match(None, None) is True

    def test_both_none(self):
        assert types_match(None, None) is True

    def test_manifest_specified_impl_none(self):
        """Manifest specifies type but impl doesn't -> mismatch."""
        assert types_match("str", None) is False

    def test_pep585_equivalence(self):
        """list[str] should match List[str] (PEP 585)."""
        assert types_match("list[str]", "List[str]") is True
        assert types_match("dict[str, int]", "Dict[str, int]") is True
        assert types_match("tuple[int, ...]", "Tuple[int, ...]") is True
        assert types_match("set[str]", "Set[str]") is True
