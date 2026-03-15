from pathlib import Path
from tree_sitter import Node, Tree

from api.entities.entity import Entity


class File:
    """
    Represents a file with basic properties like path, name, and extension.
    """

    def __init__(self, path: Path, tree: Tree) -> None:
        """
        Initialize a File object.

        Args:
            path (Path): The full path to the file.
            tree (Tree): The parsed AST of the file content.
        """

        self.path = path
        self.tree = tree
        self.entities: dict[Node, Entity] = {}

    def add_entity(self, entity: Entity):
        entity.parent = self
        self.entities[entity.node] = entity

    def __str__(self) -> str:
        return f"path: {self.path}"

    def __eq__(self, other) -> bool:
        if not isinstance(other, File):
            return False

        return self.path == other.path

