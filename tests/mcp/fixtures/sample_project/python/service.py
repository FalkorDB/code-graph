"""Service layer for the MCP fixture project."""

from .repo import UserRepo, OrderRepo


def service() -> str:
    """Middle of the canonical call chain: entrypoint -> service -> repo."""
    users = UserRepo()
    orders = OrderRepo()
    return users.repo() + ":" + orders.repo()
