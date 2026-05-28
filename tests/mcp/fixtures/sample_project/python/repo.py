"""Repository layer for the MCP fixture project.

Exercises a small class hierarchy: ``BaseRepo`` <- ``UserRepo`` / ``OrderRepo``.
"""

from .db import db


class BaseRepo:
    """Base class so the analyzer emits an INHERITS edge."""

    def repo(self) -> str:
        return db()


class UserRepo(BaseRepo):
    def repo(self) -> str:
        return "user:" + super().repo()


class OrderRepo(BaseRepo):
    def repo(self) -> str:
        return "order:" + super().repo()
