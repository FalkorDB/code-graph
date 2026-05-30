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
        self.imports: list[Node] = []
        self.resolved_imports: set[Entity] = set()

    def add_entity(self, entity: Entity):
        entity.parent = self
        self.entities[entity.node] = entity
    
    def add_import(self, import_node: Node):
        """
        Add an import statement node to track.
        
        Args:
            import_node (Node): The import statement node.
        """
        self.imports.append(import_node)
    
    def add_resolved_import(self, resolved_entity: Entity):
        """
        Add a resolved import entity.
        
        Args:
            resolved_entity (Entity): The resolved entity that is imported.
        """
        self.resolved_imports.add(resolved_entity)

    def __str__(self) -> str:
        return f"path: {self.path}"

    def __eq__(self, other) -> bool:
        if not isinstance(other, File):
            return False

        return self.path == other.path

