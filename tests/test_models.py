# tests/test_models.py
"""Test file demonstrating class instantiation for behavioral validation."""


class User:
    def __init__(self, name, email):
        self.name = name
        self.email = email


class Product:
    def __init__(self, sku, price):
        self.sku = sku
        self.price = price


def test_create_models():
    """Test that instantiates the expected classes."""
    # Class instantiations that behavioral validator should find
    user = User(name="Alice", email="alice@example.com")
    product = Product(sku="ABC123", price=99.99)

    assert user.name == "Alice"
    assert product.sku == "ABC123"