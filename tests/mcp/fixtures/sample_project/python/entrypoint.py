"""Entrypoint for the MCP test fixture project.

Call graph (must match ``expected.yaml``):

    entrypoint() -> service() -> repo() -> db()
"""

from .service import service


def entrypoint() -> str:
    """Top of the canonical call chain used by every MCP integration test."""
    return service()


if __name__ == "__main__":
    entrypoint()
