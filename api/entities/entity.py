from typing import Callable, Self
from tree_sitter import Node


# Resolution confidence ranking. A callee reached by several symbols (or by both
# the exact and the name-based fallback path) keeps its highest-confidence tag:
# an exact static resolution must never be downgraded to a name-based guess.
_RESOLUTION_RANK = {"static_name": 0, "lsp": 1, "static_exact": 2}


def _resolution_rank(resolution: str) -> int:
    return _RESOLUTION_RANK.get(resolution, _RESOLUTION_RANK["lsp"])


class Entity:
    def __init__(self, node: Node):
        self.node = node
        self.symbols: dict[str, list[Node]] = {}
        # callee entity -> resolution kind ('static_exact' | 'lsp' | 'static_name')
        self.resolved_symbols: dict[str, dict[Self, str]] = {}
        self.children: dict[Node, Self] = {}

    def add_symbol(self, key: str, symbol: Node):
        if key not in self.symbols:
            self.symbols[key] = []
        self.symbols[key].append(symbol)

    def add_resolved_symbol(self, key: str, symbol: Self, resolution: str = "lsp"):
        bucket = self.resolved_symbols.setdefault(key, {})
        self._record(bucket, symbol, resolution)

    def add_child(self, child: Self):
        child.parent = self
        self.children[child.node] = child

    @staticmethod
    def _record(bucket: dict, symbol: Self, resolution: str) -> None:
        existing = bucket.get(symbol)
        if existing is None or _resolution_rank(resolution) > _resolution_rank(existing):
            bucket[symbol] = resolution

    def resolved_symbol(self, f: Callable[[str, Node], list]):
        for key, symbols in self.symbols.items():
            bucket: dict[Self, str] = {}
            self.resolved_symbols[key] = bucket
            for symbol in symbols:
                for item in f(key, symbol):
                    # Resolvers may return either a bare entity (legacy LSP/jedi
                    # path) or an ``(entity, resolution)`` tuple (static
                    # tree-sitter resolver). Normalize both shapes centrally.
                    if isinstance(item, tuple):
                        resolved, resolution = item
                    else:
                        resolved, resolution = item, "lsp"
                    self._record(bucket, resolved, resolution)