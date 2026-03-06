from falkordb import Node, Edge, Path

def encode_node(n: Node) -> dict:
    n.labels.remove('Searchable')
    return vars(n)

def encode_edge(e: Edge) -> dict:
    return vars(e)

def encode_path(p: Path) -> dict:
    return {
            'nodes': [encode_node(n) for n in p.nodes()],
            'edges': [encode_edge(e) for e in p.edges()]
            }

def encode_graph_entity(e) -> dict:
    if isinstance(e, Node):
        return encode_node(e)
    elif isinstance(e, Edge):
        return encode_edge(e)
    elif isinstance(e, Path):
        return encode_path(e)
    else:
        raise Exception("Unable to encode graph entity, unknown graph entity type: {type(e)}")

