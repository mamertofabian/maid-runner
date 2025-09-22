# tests/test_processor.py
"""Test file demonstrating missing parameter usage (for testing failures)."""


# Simulate an import (in real tests, this would be from src.processor import process_data)
class ProcessorModule:
    @staticmethod
    def process_data(input_data, options=None):
        """Function that processes data."""
        return {"result": input_data}


processor = ProcessorModule()


def test_process_data():
    """Test that only uses one parameter, missing 'options'."""
    # Missing 'options' argument - this should fail behavioral validation
    # Using function call that behavioral validator will detect
    result = processor.process_data(input_data=[1, 2, 3])
    assert result is not None