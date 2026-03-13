from .graph import Graph, AsyncGraphQuery


def prefix_search(repo: str, prefix: str) -> str:
    """ Returns a list of all entities in the repository that start with the given prefix. """
    g = Graph(repo)
    return g.prefix_search(prefix)


async def async_prefix_search(repo: str, prefix: str) -> list:
    """Async version of prefix_search using AsyncGraphQuery."""
    g = AsyncGraphQuery(repo)
    try:
        return await g.prefix_search(prefix)
    finally:
        await g.close()
