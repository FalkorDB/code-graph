from typing import Callable, Self
from tree_sitter import Node


class Entity:
    def __init__(self, node: Node):
        self.node = node
        self.symbols: dict[str, list[Node]] = {}
        self.resolved_symbols: dict[str, set[Self]] = {}
        self.children: dict[Node, Self] = {}

    def add_symbol(self, key: str, symbol: Node):
        if key not in self.symbols:
            self.symbols[key] = []
        self.symbols[key].append(symbol)

    def add_resolved_symbol(self, key: str, symbol: Self):
        if key not in self.resolved_symbols:
            self.resolved_symbols[key] = set()
        self.resolved_symbols[key].add(symbol)

    def add_child(self, child: Self):
        child.parent = self
        self.children[child.node] = child

    def resolved_symbol(self, f: Callable[[str, Node], list[Self]]):
        for key, symbols in self.symbols.items():
            self.resolved_symbols[key] = set()
            for symbol in symbols:
                for resolved_symbol in f(key, symbol):
                    self.resolved_symbols[key].add(resolved_symbol)