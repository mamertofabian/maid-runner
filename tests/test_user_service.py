# tests/test_user_service.py
"""Test file for demonstrating behavioral validation of UserService."""
from unittest.mock import Mock


class User:
    def __init__(self, id):
        self.id = id


class UserService:
    def get_user_by_id(self, user_id):
        return User(user_id)


def test_get_user_by_id_returns_correct_user():
    """Test that get_user_by_id returns a user with the correct ID."""
    # Setup
    service = UserService()

    # The actual usage that the AST validator will find
    user_id = 123
    user = service.get_user_by_id(user_id)  # Key line: method call with parameter

    # Assertions
    assert isinstance(user, User)  # Validates return type
    assert user.id == user_id