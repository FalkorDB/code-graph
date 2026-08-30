import importlib.util
import sys
import os
import pytest
from falkordb import Node

# Import entity_encoder directly without triggering api/__init__.py
_spec = importlib.util.spec_from_file_location(
    "entity_encoder",
    os.path.join(os.path.dirname(__file__), "..", "api", "entities", "entity_encoder.py"),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
encode_node = _mod.encode_node


def make_node(labels, props=None):
    return Node(node_id=1, alias="n", labels=labels, properties=props or {})


def test_encode_node_removes_searchable():
    n = make_node(['File', 'Searchable'])
    result = encode_node(n)
    assert 'Searchable' not in result['labels']
    assert 'File' in result['labels']


def test_encode_node_does_not_mutate_original():
    n = make_node(['File', 'Searchable'])
    encode_node(n)
    assert 'Searchable' in n.labels


def test_encode_node_twice_does_not_raise():
    n = make_node(['File', 'Searchable'])
    encode_node(n)
    # Second call must not raise ValueError
    result = encode_node(n)
    assert 'Searchable' not in result['labels']


def test_encode_node_without_searchable():
    n = make_node(['Class'])
    result = encode_node(n)
    assert result['labels'] == ['Class']
