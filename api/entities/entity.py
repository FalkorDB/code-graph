from typing import Callable, Self
from tree_sitter import Node

class Symbol:
    def __init__(self, symbol: Node):
        self.symbol = symbol
        self.resolved_symbol = set()

    def add_resolve_symbol(self, resolved_symbol):
        self.resolved_symbol.add(resolved_symbol)

class Entity:
    def __init__(self, node: Node):
        self.node = node
        self.symbols: dict[str, list[Symbol]] = {}
        self.children: dict[Node, Self] = {}

    def add_symbol(self, key: str, symbol: Node):
        if key not in self.symbols:
            self.symbols[key] = []
        self.symbols[key].append(Symbol(symbol))

    def add_child(self, child: Self):
        child.parent = self
        self.children[child.node] = child

    def resolved_symbol(self, f: Callable[[str, Node], list[Self]]):
        for key, symbols in self.symbols.items():
            for symbol in symbols:
                for resolved_symbol in f(key, symbol.symbol):
                    symbol.add_resolve_symbol(resolved_symbol)