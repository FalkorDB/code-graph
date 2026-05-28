"""Bottom of the canonical call chain."""


def db() -> str:
    """Leaf function — entrypoint -> service -> repo -> db."""
    return "db"
