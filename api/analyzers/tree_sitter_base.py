"""Shared base class for tree-sitter-backed analyzers."""

from pathlib import Path
from typing import Optional

from multilspy import SyncLanguageServer
from tree_sitter import Node

from api.entities.entity import Entity
from api.entities.file import File

from .analyzer import AbstractAnalyzer


class TreeSitterAnalyzer(AbstractAnalyzer):
    """Base implementation for analyzers that use tree-sitter plus LSP resolution.

    Subclasses declare the node types they treat as graph entities and the symbol
    keys that resolve to type or callable definitions. Language-specific AST
    normalization can be implemented by overriding the target-extraction hooks.
    """

    entity_node_types: dict[str, str] = {}
    type_definition_node_types: tuple[str, ...] = ()
    callable_definition_node_types: tuple[str, ...] = ()
    callable_exclude_node_types: tuple[str, ...] = ()
    type_resolution_keys: tuple[str, ...] = ()
    method_resolution_keys: tuple[str, ...] = ()

    def resolve_path(self, file_path: str, path: Path) -> str:
        """Resolve an LSP path into the key used by the analyzed file map."""
        return file_path

    def get_entity_types(self) -> list[str]:
        """Return the tree-sitter node types recognized as graph entities."""
        return list(self.entity_node_types.keys())

    def get_entity_label(self, node: Node) -> str:
        """Return the graph label for an entity node declared by the subclass."""
        try:
            return self.entity_node_types[node.type]
        except KeyError as exc:
            raise ValueError(f"Unknown entity type: {node.type}") from exc

    def resolve_symbol(
        self,
        files: dict[Path, File],
        lsp: SyncLanguageServer,
        file_path: Path,
        path: Path,
        key: str,
        symbol: Node,
    ) -> list:
        """Dispatch a captured symbol to type or callable resolution.

        Returns bare ``Entity`` objects for type resolution and
        ``(Entity, resolution)`` tuples for callable resolution; callers
        normalize both shapes (see ``Entity.resolved_symbol``).
        """
        if key in self.type_resolution_keys:
            return self.resolve_type(files, lsp, file_path, path, symbol)
        if key in self.method_resolution_keys:
            return self.resolve_method(files, lsp, file_path, path, symbol)
        raise ValueError(f"Unknown key {key}")

    def _extract_call_target(self, node: Node) -> Optional[Node]:
        """Normalize a call symbol before resolving it to a callable definition."""
        return node

    def _extract_type_target(self, node: Node) -> Optional[Node]:
        """Normalize a type symbol before resolving it to a type definition."""
        return node

    def resolve_type(
        self,
        files: dict[Path, File],
        lsp: SyncLanguageServer,
        file_path: Path,
        path: Path,
        node: Node,
    ) -> list[Entity]:
        """Resolve a type reference to matching type-definition entities."""
        res = []
        target = self._extract_type_target(node)
        if target is None:
            return res
        # ``resolve`` may yield 2-tuples (LSP/jedi) or 3-tuples (static
        # resolver, carrying a resolution kind). Type edges ignore the
        # resolution kind, so unpack tolerantly.
        for file, resolved_node, *_ in self.resolve(files, lsp, file_path, path, target):
            type_dec = self.find_parent(resolved_node, self.type_definition_node_types)
            if type_dec in file.entities:
                res.append(file.entities[type_dec])
        return res

    def resolve_method(
        self,
        files: dict[Path, File],
        lsp: SyncLanguageServer,
        file_path: Path,
        path: Path,
        node: Node,
    ) -> list[tuple[Entity, str]]:
        """Resolve a call reference to matching callable-definition entities.

        Returns ``(entity, resolution)`` pairs. ``resolution`` is the kind
        reported by the resolver (``static_exact`` / ``static_name`` for the
        static tree-sitter resolver) and defaults to ``"lsp"`` for resolvers
        that yield bare ``(file, node)`` pairs.
        """
        res = []
        target = self._extract_call_target(node)
        if target is None:
            return res
        for file, resolved_node, *rest in self.resolve(files, lsp, file_path, path, target):
            resolution = rest[0] if rest else "lsp"
            method_dec = self.find_parent(resolved_node, self.callable_definition_node_types)
            if method_dec and method_dec.type in self.callable_exclude_node_types:
                continue
            if method_dec in file.entities:
                res.append((file.entities[method_dec], resolution))
        return res
