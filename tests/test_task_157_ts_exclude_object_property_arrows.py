"""Tests for task-157: Exclude object property arrow functions from found_functions.

Object property arrow functions like queryFn, mutationFn, and onSuccess in React Query
are anonymous functions assigned to object properties, not public function declarations.
They should not be extracted as artifacts.
"""

import os
import tempfile

from maid_runner.validators.typescript_validator import TypeScriptValidator


class TestExtractArrowFunctionsMethod:
    """Direct tests for _extract_arrow_functions method behavior."""

    def test_extract_arrow_functions_excludes_object_properties(self):
        """_extract_arrow_functions should not extract object property arrow functions."""
        code = b"""
const config = {
  queryFn: async () => { return data; },
  onSuccess: () => console.log('done')
};

const myFunction = () => { return 'hello'; };
"""
        validator = TypeScriptValidator()
        tree = validator.ts_parser.parse(code)

        # Call _extract_arrow_functions directly
        functions = validator._extract_arrow_functions(tree, code)

        # Top-level arrow function should be extracted
        assert "myFunction" in functions
        # Object property arrow functions should NOT be extracted
        assert "queryFn" not in functions
        assert "onSuccess" not in functions

    def test_extract_arrow_functions_includes_class_properties(self):
        """_extract_arrow_functions should extract class property arrow functions."""
        code = b"""
class Service {
  handler = (data) => { return data; };
}
"""
        validator = TypeScriptValidator()
        tree = validator.ts_parser.parse(code)

        # Call _extract_arrow_functions directly
        functions = validator._extract_arrow_functions(tree, code)

        # Class property arrow functions should be extracted
        assert "handler" in functions

    def test_extract_arrow_functions_excludes_nested_object_properties(self):
        """_extract_arrow_functions should not extract nested object property arrows."""
        code = b"""
const api = {
  endpoints: {
    onRequest: async (req) => req,
    onResponse: (res) => res.data
  }
};
"""
        validator = TypeScriptValidator()
        tree = validator.ts_parser.parse(code)

        # Call _extract_arrow_functions directly
        functions = validator._extract_arrow_functions(tree, code)

        # Nested object property arrow functions should NOT be extracted
        assert "onRequest" not in functions
        assert "onResponse" not in functions


class TestObjectPropertyArrowFunctionsExcluded:
    """Test that object property arrow functions are NOT extracted as functions."""

    def test_query_fn_not_extracted_as_function(self):
        """queryFn in useQuery options should not be extracted as a function."""
        code = """
export function useOrganisations(tenantId?: string) {
  return useQuery({
    queryKey: queryKeys.organisations(tenantId),
    queryFn: async () => {
      const { data, error } = await query;
      if (error) throw error;
      return data;
    },
    staleTime: 5 * 60 * 1000,
  });
}
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                # useOrganisations IS a function declaration
                assert "useOrganisations" in artifacts["found_functions"]
                # queryFn is NOT a function declaration - it's an object property
                assert "queryFn" not in artifacts["found_functions"]
            finally:
                os.unlink(f.name)

    def test_mutation_fn_not_extracted_as_function(self):
        """mutationFn in useMutation options should not be extracted as a function."""
        code = """
export function useCreateUser() {
  return useMutation({
    mutationFn: async (userData: UserData) => {
      const response = await api.post('/users', userData);
      return response.data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
    onError: (error) => {
      console.error('Failed to create user:', error);
    }
  });
}
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                # useCreateUser IS a function declaration
                assert "useCreateUser" in artifacts["found_functions"]
                # These are NOT function declarations - they're object properties
                assert "mutationFn" not in artifacts["found_functions"]
                assert "onSuccess" not in artifacts["found_functions"]
                assert "onError" not in artifacts["found_functions"]
            finally:
                os.unlink(f.name)

    def test_nested_object_arrow_functions_not_extracted(self):
        """Arrow functions in nested objects should not be extracted."""
        code = """
const config = {
  api: {
    onRequest: async (request) => {
      return request;
    },
    onResponse: (response) => {
      return response.data;
    }
  },
  handlers: {
    onClick: () => console.log('clicked'),
    onSubmit: async (data) => await saveData(data)
  }
};
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                # None of these should be extracted as functions
                assert "onRequest" not in artifacts["found_functions"]
                assert "onResponse" not in artifacts["found_functions"]
                assert "onClick" not in artifacts["found_functions"]
                assert "onSubmit" not in artifacts["found_functions"]
            finally:
                os.unlink(f.name)

    def test_react_component_event_handlers_not_extracted(self):
        """Event handler arrow functions in JSX should not be extracted."""
        code = """
const Button = ({ label }: Props) => {
  const config = {
    onClick: () => console.log('clicked'),
    onHover: (e: MouseEvent) => setHovered(true)
  };
  return <button {...config}>{label}</button>;
};
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsx", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                # Button IS a function (arrow function assigned to const)
                assert "Button" in artifacts["found_functions"]
                # onClick and onHover are NOT functions - they're object properties
                assert "onClick" not in artifacts["found_functions"]
                assert "onHover" not in artifacts["found_functions"]
            finally:
                os.unlink(f.name)


class TestTopLevelArrowFunctionsStillExtracted:
    """Verify that top-level arrow functions ARE still extracted."""

    def test_const_arrow_function_extracted(self):
        """Arrow functions assigned to const variables should be extracted."""
        code = """
export const fetchUsers = async () => {
  const response = await fetch('/api/users');
  return response.json();
};

export const processData = (data: Data[]) => {
  return data.map(item => item.value);
};
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                # These ARE function declarations (arrow functions assigned to const)
                assert "fetchUsers" in artifacts["found_functions"]
                assert "processData" in artifacts["found_functions"]
            finally:
                os.unlink(f.name)

    def test_let_arrow_function_extracted(self):
        """Arrow functions assigned to let variables should be extracted."""
        code = """
let handler = (event: Event) => {
  console.log(event);
};
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                assert "handler" in artifacts["found_functions"]
            finally:
                os.unlink(f.name)


class TestClassPropertyArrowFunctionsStillExtracted:
    """Verify that class property arrow functions ARE still extracted."""

    def test_public_class_arrow_property_extracted(self):
        """Public class property arrow functions should be extracted."""
        code = """
class UserService {
  fetchUser = async (id: string) => {
    return await api.get(`/users/${id}`);
  };

  processUser = (user: User) => {
    return { ...user, processed: true };
  };
}
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                # Class property arrow functions ARE extracted
                assert "fetchUser" in artifacts["found_functions"]
                assert "processUser" in artifacts["found_functions"]
            finally:
                os.unlink(f.name)

    def test_private_class_arrow_property_not_extracted(self):
        """Private class property arrow functions should not be extracted."""
        code = """
class UserService {
  private internalHelper = () => {
    return 'internal';
  };

  public publicMethod = () => {
    return this.internalHelper();
  };
}
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                # Public class property arrow function IS extracted
                assert "publicMethod" in artifacts["found_functions"]
                # Private class property arrow function is NOT extracted
                assert "internalHelper" not in artifacts["found_functions"]
            finally:
                os.unlink(f.name)


class TestMixedScenarios:
    """Test mixed scenarios with both object properties and real functions."""

    def test_react_query_hook_with_helper_functions(self):
        """Real-world scenario: React Query hook with helper functions."""
        code = """
const transformData = (data: RawData[]) => {
  return data.map(item => ({ ...item, transformed: true }));
};

export function useOrganisations(tenantId?: string) {
  return useQuery({
    queryKey: ['organisations', tenantId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('organisations')
        .select('*');
      if (error) throw error;
      return transformData(data);
    },
    staleTime: 5 * 60 * 1000,
  });
}

export function useMutateOrganisation() {
  return useMutation({
    mutationFn: async (org: Organisation) => {
      const { data, error } = await supabase
        .from('organisations')
        .upsert(org);
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['organisations'] });
    }
  });
}
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                # Real functions should be extracted
                assert "transformData" in artifacts["found_functions"]
                assert "useOrganisations" in artifacts["found_functions"]
                assert "useMutateOrganisation" in artifacts["found_functions"]
                # Object property arrow functions should NOT be extracted
                assert "queryFn" not in artifacts["found_functions"]
                assert "mutationFn" not in artifacts["found_functions"]
                assert "onSuccess" not in artifacts["found_functions"]
            finally:
                os.unlink(f.name)

    def test_vitest_describe_callbacks_not_extracted(self):
        """Vitest/Jest describe/it callbacks should not be extracted as functions."""
        code = """
import { describe, it, expect } from 'vitest';

describe('MyComponent', () => {
  it('should render', () => {
    expect(true).toBe(true);
  });
});
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                # The callbacks are anonymous - no named functions to extract
                # (describe and it are function calls, not declarations)
                # Just verify no spurious functions are extracted
                found = artifacts["found_functions"]
                # Should not have random object properties as functions
                assert "queryFn" not in found
                assert "mutationFn" not in found
            finally:
                os.unlink(f.name)
