from .graph import Graph

def prefix_search(repo: str, prefix: str) -> str:
    """ Returns a list of all entities in the repository that start with the given prefix. """
    g = Graph(repo)
    return g.prefix_search(prefix)
