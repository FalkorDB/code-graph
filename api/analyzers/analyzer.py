from pathlib import Path
from typing import Optional

from tree_sitter import Language, Node, Parser, Point
from api.entities.entity import Entity
from api.entities.file import File
from abc import ABC, abstractmethod
from multilspy import SyncLanguageServer

class AbstractAnalyzer(ABC):
    def __init__(self, language: Language) -> None:
        self.language = language
        self.parser = Parser(language)

    def find_parent(self, node: Node, parent_types: list) -> Node:
        while node and node.type not in parent_types:
            node = node.parent
        return node
    
    @abstractmethod
    def is_dependency(self, file_path: str) -> bool:
        """
        Check if the file is a dependency.

        Args:
            file_path (str): The file path.

        Returns:
            bool: True if the file is a dependency, False otherwise.
        """

        pass
    
    @abstractmethod
    def resolve_path(self, file_path: str, path: Path) -> str:
        """
        Resolve the path of the file.

        Args:
            file_path (str): The file path.
            path (Path): The path to the folder.

        Returns:
            str: The resolved path.
        """

        pass

    def resolve(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path: Path, node: Node) -> list[tuple[File, Node]]:
        try:
            locations = lsp.request_definition(str(file_path), node.start_point.row, node.start_point.column)
            return [(files[Path(self.resolve_path(location['absolutePath'], path))], files[Path(self.resolve_path(location['absolutePath'], path))].tree.root_node.descendant_for_point_range(Point(location['range']['start']['line'], location['range']['start']['character']), Point(location['range']['end']['line'], location['range']['end']['character']))) for location in locations if location and Path(self.resolve_path(location['absolutePath'], path)) in files]
        except Exception as e:
            return []
        
    @abstractmethod
    def add_dependencies(self, path: Path, files: list[Path]):
        """
        Add dependencies to the files.

        Args:
            path (Path): The path to the folder.
            files (dict[Path, File]): The files.
        """

        pass
    
    @abstractmethod
    def get_entity_label(self, node: Node) -> str:
        """
        Get the entity label from the node.

        Args:
            node (Node): The node.
        
        Returns:
            str: The entity label.
        """
        pass

    @abstractmethod
    def get_entity_name(self, node: Node) -> str:
        """
        Get the entity name from the node.

        Args:
            node (Node): The node.
        
        Returns:
            str: The entity name.
        """
        pass

    @abstractmethod
    def get_entity_docstring(self, node: Node) -> Optional[str]:
        """
        Get the entity docstring from the node.

        Args:
            node (Node): The node.

        Returns:
            Optional[str]: The entity docstring.
        """
        pass
    
    @abstractmethod
    def get_entity_types(self) -> list[str]:
        """
        Get the top level entity types for the language.

        Returns:
            list[str]: The list of top level entity types.
        """

        pass

    @abstractmethod
    def add_symbols(self, entity: Entity) -> None:
        """
        Add symbols to the entity.

        Args:
            entity (Entity): The entity to add symbols to.
        """

        pass

    @abstractmethod
    def resolve_symbol(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path: Path, key: str, symbol: Node) -> list[Entity]:
        """
        Resolve a symbol to an entity.

        Args:
            lsp (SyncLanguageServer): The language server.
            path (Path): The path to the file.
            key (str): The symbol key.
            symbol (Node): The symbol node.

        Returns:
            list[Entity]: The resolved entities.
        """

        pass

