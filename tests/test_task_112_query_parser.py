"""Behavioral tests for Task 112: Query Parser.

Tests the QueryType enum, QueryIntent dataclass, and QueryParser class
for parsing natural language-style graph queries.
"""

# Import artifacts from the module under test
from maid_runner.graph.query import (
    QueryType,
    QueryIntent,
    QueryParser,
)


class TestQueryTypeEnum:
    """Test QueryType enum values exist and are distinct."""

    def test_find_definition_value_exists(self):
        """QueryType has FIND_DEFINITION value."""
        assert hasattr(QueryType, "FIND_DEFINITION")
        assert QueryType.FIND_DEFINITION is not None

    def test_find_dependents_value_exists(self):
        """QueryType has FIND_DEPENDENTS value."""
        assert hasattr(QueryType, "FIND_DEPENDENTS")
        assert QueryType.FIND_DEPENDENTS is not None

    def test_find_dependencies_value_exists(self):
        """QueryType has FIND_DEPENDENCIES value."""
        assert hasattr(QueryType, "FIND_DEPENDENCIES")
        assert QueryType.FIND_DEPENDENCIES is not None

    def test_find_impact_value_exists(self):
        """QueryType has FIND_IMPACT value."""
        assert hasattr(QueryType, "FIND_IMPACT")
        assert QueryType.FIND_IMPACT is not None

    def test_find_cycles_value_exists(self):
        """QueryType has FIND_CYCLES value."""
        assert hasattr(QueryType, "FIND_CYCLES")
        assert QueryType.FIND_CYCLES is not None

    def test_list_artifacts_value_exists(self):
        """QueryType has LIST_ARTIFACTS value."""
        assert hasattr(QueryType, "LIST_ARTIFACTS")
        assert QueryType.LIST_ARTIFACTS is not None

    def test_all_values_are_distinct(self):
        """All QueryType enum values are distinct from each other."""
        values = [
            QueryType.FIND_DEFINITION,
            QueryType.FIND_DEPENDENTS,
            QueryType.FIND_DEPENDENCIES,
            QueryType.FIND_IMPACT,
            QueryType.FIND_CYCLES,
            QueryType.LIST_ARTIFACTS,
        ]
        # Check all values are unique
        assert len(values) == len(set(values))


class TestQueryIntentDataclass:
    """Test QueryIntent dataclass creation and attribute access."""

    def test_creation_with_all_attributes(self):
        """QueryIntent can be created with query_type, target, and original_query."""
        intent = QueryIntent(
            query_type=QueryType.FIND_DEFINITION,
            target="MyClass",
            original_query="What defines MyClass?",
        )
        assert intent is not None

    def test_query_type_attribute_accessible(self):
        """QueryIntent.query_type attribute is accessible and correct."""
        intent = QueryIntent(
            query_type=QueryType.FIND_DEPENDENTS,
            target="some_function",
            original_query="What depends on some_function?",
        )
        assert intent.query_type == QueryType.FIND_DEPENDENTS

    def test_target_attribute_accessible(self):
        """QueryIntent.target attribute is accessible and correct."""
        intent = QueryIntent(
            query_type=QueryType.FIND_DEFINITION,
            target="TargetClass",
            original_query="What defines TargetClass?",
        )
        assert intent.target == "TargetClass"

    def test_original_query_attribute_accessible(self):
        """QueryIntent.original_query attribute is accessible and correct."""
        original = "What does MyModule depend on?"
        intent = QueryIntent(
            query_type=QueryType.FIND_DEPENDENCIES,
            target="MyModule",
            original_query=original,
        )
        assert intent.original_query == original

    def test_target_can_be_none(self):
        """QueryIntent.target can be None for queries without a target."""
        intent = QueryIntent(
            query_type=QueryType.FIND_CYCLES,
            target=None,
            original_query="Find circular dependencies",
        )
        assert intent.target is None


class TestQueryParserClass:
    """Test QueryParser class instantiation."""

    def test_can_instantiate(self):
        """QueryParser can be instantiated."""
        parser = QueryParser()
        assert parser is not None

    def test_has_parse_method(self):
        """QueryParser has a parse method."""
        parser = QueryParser()
        assert hasattr(parser, "parse")
        assert callable(parser.parse)

    def test_has_extract_target_method(self):
        """QueryParser has a _extract_target method."""
        parser = QueryParser()
        assert hasattr(parser, "_extract_target")
        assert callable(parser._extract_target)

    def test_has_determine_query_type_method(self):
        """QueryParser has a _determine_query_type method."""
        parser = QueryParser()
        assert hasattr(parser, "_determine_query_type")
        assert callable(parser._determine_query_type)


class TestQueryParserParse:
    """Test QueryParser.parse method behavior."""

    def test_parse_returns_query_intent(self):
        """parse() returns a QueryIntent object."""
        parser = QueryParser()
        result = parser.parse("What defines MyClass?")
        assert isinstance(result, QueryIntent)

    def test_parse_what_defines_as_find_definition(self):
        """parse() interprets 'What defines X?' as FIND_DEFINITION."""
        parser = QueryParser()
        result = parser.parse("What defines MyClass?")
        assert result.query_type == QueryType.FIND_DEFINITION

    def test_parse_what_depends_on_as_find_dependents(self):
        """parse() interprets 'What depends on X?' as FIND_DEPENDENTS."""
        parser = QueryParser()
        result = parser.parse("What depends on my_function?")
        assert result.query_type == QueryType.FIND_DEPENDENTS

    def test_parse_what_does_depend_on_as_find_dependencies(self):
        """parse() interprets 'What does X depend on?' as FIND_DEPENDENCIES."""
        parser = QueryParser()
        result = parser.parse("What does MyModule depend on?")
        assert result.query_type == QueryType.FIND_DEPENDENCIES

    def test_parse_what_would_break_as_find_impact(self):
        """parse() interprets 'What would break if I change X?' as FIND_IMPACT."""
        parser = QueryParser()
        result = parser.parse("What would break if I change validate_manifest?")
        assert result.query_type == QueryType.FIND_IMPACT

    def test_parse_find_circular_as_find_cycles(self):
        """parse() interprets 'Find circular dependencies' as FIND_CYCLES."""
        parser = QueryParser()
        result = parser.parse("Find circular dependencies")
        assert result.query_type == QueryType.FIND_CYCLES

    def test_parse_show_all_artifacts_as_list_artifacts(self):
        """parse() interprets 'Show all artifacts in module X' as LIST_ARTIFACTS."""
        parser = QueryParser()
        result = parser.parse("Show all artifacts in module graph")
        assert result.query_type == QueryType.LIST_ARTIFACTS

    def test_parse_extracts_target_correctly(self):
        """parse() extracts target name from the query."""
        parser = QueryParser()
        result = parser.parse("What defines MyTargetClass?")
        assert result.target == "MyTargetClass"

    def test_parse_stores_original_query(self):
        """parse() stores the original query string."""
        parser = QueryParser()
        query = "What depends on some_artifact?"
        result = parser.parse(query)
        assert result.original_query == query

    def test_parse_handles_case_insensitivity(self):
        """parse() handles queries case-insensitively."""
        parser = QueryParser()
        result_lower = parser.parse("what defines myclass?")
        result_upper = parser.parse("WHAT DEFINES myclass?")
        result_mixed = parser.parse("What Defines myclass?")

        assert result_lower.query_type == QueryType.FIND_DEFINITION
        assert result_upper.query_type == QueryType.FIND_DEFINITION
        assert result_mixed.query_type == QueryType.FIND_DEFINITION


class TestQueryParserExtractTarget:
    """Test QueryParser._extract_target method behavior."""

    def test_extracts_target_from_what_defines(self):
        """_extract_target extracts target from 'What defines X?' pattern."""
        parser = QueryParser()
        result = parser._extract_target("What defines MyClass?")
        assert result == "MyClass"

    def test_extracts_target_from_what_depends_on(self):
        """_extract_target extracts target from 'What depends on X?' pattern."""
        parser = QueryParser()
        result = parser._extract_target("What depends on my_function?")
        assert result == "my_function"

    def test_extracts_target_from_what_does_depend_on(self):
        """_extract_target extracts target from 'What does X depend on?' pattern."""
        parser = QueryParser()
        result = parser._extract_target("What does MyModule depend on?")
        assert result == "MyModule"

    def test_extracts_target_from_show_all_artifacts(self):
        """_extract_target extracts target from 'Show all artifacts in module X' pattern."""
        parser = QueryParser()
        result = parser._extract_target("Show all artifacts in module graph")
        assert result == "graph"

    def test_returns_none_when_no_target(self):
        """_extract_target returns None when query has no target."""
        parser = QueryParser()
        result = parser._extract_target("Find circular dependencies")
        assert result is None

    def test_extracts_quoted_target(self):
        """_extract_target extracts target from quoted strings."""
        parser = QueryParser()
        result = parser._extract_target('What defines "MyClass"?')
        assert result == "MyClass"

    def test_extracts_target_with_underscores(self):
        """_extract_target correctly extracts targets with underscores."""
        parser = QueryParser()
        result = parser._extract_target("What depends on my_long_function_name?")
        assert result == "my_long_function_name"


class TestQueryParserDetermineQueryType:
    """Test QueryParser._determine_query_type method behavior."""

    def test_determines_find_definition_type(self):
        """_determine_query_type returns FIND_DEFINITION for 'defines' queries."""
        parser = QueryParser()
        result = parser._determine_query_type("What defines MyClass?")
        assert result == QueryType.FIND_DEFINITION

    def test_determines_find_dependents_type(self):
        """_determine_query_type returns FIND_DEPENDENTS for 'depends on' queries."""
        parser = QueryParser()
        result = parser._determine_query_type("What depends on MyClass?")
        assert result == QueryType.FIND_DEPENDENTS

    def test_determines_find_dependencies_type(self):
        """_determine_query_type returns FIND_DEPENDENCIES for 'depend on' queries."""
        parser = QueryParser()
        result = parser._determine_query_type("What does MyClass depend on?")
        assert result == QueryType.FIND_DEPENDENCIES

    def test_determines_find_impact_type(self):
        """_determine_query_type returns FIND_IMPACT for 'break' queries."""
        parser = QueryParser()
        result = parser._determine_query_type("What would break if I change X?")
        assert result == QueryType.FIND_IMPACT

    def test_determines_find_cycles_type(self):
        """_determine_query_type returns FIND_CYCLES for 'circular' queries."""
        parser = QueryParser()
        result = parser._determine_query_type("Find circular dependencies")
        assert result == QueryType.FIND_CYCLES

    def test_determines_list_artifacts_type(self):
        """_determine_query_type returns LIST_ARTIFACTS for 'show all' queries."""
        parser = QueryParser()
        result = parser._determine_query_type("Show all artifacts in module X")
        assert result == QueryType.LIST_ARTIFACTS

    def test_handles_phrasing_variation_definition(self):
        """_determine_query_type handles variations like 'where is X defined'."""
        parser = QueryParser()
        result = parser._determine_query_type("Where is MyClass defined?")
        assert result == QueryType.FIND_DEFINITION

    def test_handles_phrasing_variation_cycles(self):
        """_determine_query_type handles variations like 'detect cycles'."""
        parser = QueryParser()
        result = parser._determine_query_type("Detect cycles in the graph")
        assert result == QueryType.FIND_CYCLES


class TestQueryParserIntegration:
    """Integration tests for full query parsing workflow."""

    def test_full_parse_workflow_find_definition(self):
        """Full parse workflow for FIND_DEFINITION query."""
        parser = QueryParser()
        query = "What defines KnowledgeGraph?"
        result = parser.parse(query)

        assert result.query_type == QueryType.FIND_DEFINITION
        assert result.target == "KnowledgeGraph"
        assert result.original_query == query

    def test_full_parse_workflow_find_dependents(self):
        """Full parse workflow for FIND_DEPENDENTS query."""
        parser = QueryParser()
        query = "What depends on find_nodes_by_type?"
        result = parser.parse(query)

        assert result.query_type == QueryType.FIND_DEPENDENTS
        assert result.target == "find_nodes_by_type"
        assert result.original_query == query

    def test_full_parse_workflow_find_cycles(self):
        """Full parse workflow for FIND_CYCLES query (no target)."""
        parser = QueryParser()
        query = "Find circular dependencies"
        result = parser.parse(query)

        assert result.query_type == QueryType.FIND_CYCLES
        assert result.target is None
        assert result.original_query == query

    def test_full_parse_workflow_list_artifacts(self):
        """Full parse workflow for LIST_ARTIFACTS query."""
        parser = QueryParser()
        query = "Show all artifacts in module validators"
        result = parser.parse(query)

        assert result.query_type == QueryType.LIST_ARTIFACTS
        assert result.target == "validators"
        assert result.original_query == query
