# tests/test_factory.py
"""Test file demonstrating return type validation via isinstance."""


class Order:
    def __init__(self):
        self.items = []


def create_order():
    """Factory function that creates an Order."""
    return Order()


def test_create_order_returns_order_instance():
    """Test that validates the return type using isinstance."""
    # Call the factory function
    result = create_order()

    # This validates the return type - behavioral validator should find this
    assert isinstance(result, Order)