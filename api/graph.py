import re
import time
from typing import Optional
from falkordb import Path, Node, QueryResult
from .db import create_async_falkordb, create_falkordb
from .entities import File, encode_edge, encode_node

# Configure the logger
import logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(filename)s - %(asctime)s - %(levelname)s - %(message)s')


# ---------------------------------------------------------------------------
# Branch-aware graph naming (T17)
#
# Each indexed (project, branch) pair gets its own FalkorDB graph so that
# concurrent agents indexing the same repo on different branches do not
# overwrite each other. The format is::
#
#     code:{project_name}:{branch}
#
# When ``branch`` is omitted it defaults to ``_default`` — that is also the
# name the one-shot migration uses when promoting legacy ``{project_name}``
# graphs into the new namespace.
# ---------------------------------------------------------------------------

DEFAULT_BRANCH = "_default"
_GRAPH_NAME_RE = re.compile(r"^code:(?P<project>[^:]+):(?P<branch>.+)$")


def compose_graph_name(project_name: str, branch: Optional[str] = None) -> str:
    """Compose the FalkorDB graph name for a (project, branch) pair.

    Args:
        project_name: The repository / project name (typically the
            directory basename).
        branch: Branch name. ``None`` is treated as :data:`DEFAULT_BRANCH`.

    Returns:
        ``"code:{project_name}:{branch}"``.
    """

    if branch is None or branch == "":
        branch = DEFAULT_BRANCH
    return f"code:{project_name}:{branch}"


def parse_graph_name(graph_name: str) -> Optional[tuple[str, str]]:
    """Inverse of :func:`compose_graph_name`.

    Returns ``(project, branch)`` if ``graph_name`` follows the new
    ``code:{project}:{branch}`` format, otherwise ``None`` so callers can
    treat it as a legacy / unrelated graph.
    """

    m = _GRAPH_NAME_RE.match(graph_name)
    if not m:
        return None
    return m.group("project"), m.group("branch")


def graph_exists(name: str):
    db = create_falkordb()

    return name in db.list_graphs()


def _is_internal_suffix(graph_name: str) -> bool:
    """Internal helper graph suffixes that should never be listed as repos."""
    return graph_name.endswith('_git') or graph_name.endswith('_schema') or graph_name.endswith('_tmp')


def get_repos() -> list[dict]:
    """
        List processed (project, branch) pairs.

        Returns a list of ``{"project": ..., "branch": ..., "graph": ...}``
        dicts for every graph that matches the new ``code:{project}:{branch}``
        format. Legacy graphs (created before T17) are returned with
        ``branch == DEFAULT_BRANCH`` so callers can keep treating them as a
        single graph until the migration is run.
    """

    db = create_falkordb()

    repos = []
    for g in db.list_graphs():
        parsed = parse_graph_name(g)
        if parsed is None:
            # Legacy graph (pre-T17) or internal helper graph: skip when
            # the bare name carries an internal suffix; otherwise synthesize
            # a virtual entry so it stays discoverable.
            if _is_internal_suffix(g):
                continue
            repos.append({"project": g, "branch": DEFAULT_BRANCH, "graph": g})
        else:
            project, branch = parsed
            # Hide per-branch internal companion graphs (e.g. ``branch_git``,
            # ``branch_schema``, ``branch_tmp``); their suffix lives on the
            # branch component, so check that explicitly.
            if _is_internal_suffix(branch):
                continue
            repos.append({"project": project, "branch": branch, "graph": g})
    return repos

class Graph():
    """
    Represents a connection to a graph database using FalkorDB.

    The underlying graph is named ``code:{project_name}:{branch}`` so that
    concurrent agents working on different branches of the same repo do
    not corrupt each other's data (see T17, issue #651).

    For backwards compatibility ``name`` may be either a bare project name
    (``"falkordb"``) or a fully composed graph name (``"code:falkordb:main"``);
    in the former case the composition is performed automatically using
    ``branch`` (default :data:`DEFAULT_BRANCH`).
    """

    def __init__(self, name: str, branch: Optional[str] = None) -> None:
        # Accept either an already-composed graph name or a bare project
        # name + branch. ``parse_graph_name`` returns ``None`` for legacy /
        # bare names, signalling that we need to compose.
        parsed = parse_graph_name(name)
        if parsed is not None:
            self.project, self.branch = parsed
            self.name = name
        else:
            self.project = name
            # Normalize empty / None to DEFAULT_BRANCH so the stored
            # branch matches the key actually used by compose_graph_name.
            self.branch = branch or DEFAULT_BRANCH
            self.db = create_falkordb()
            # Legacy (pre-T17) graphs are stored under the bare project
            # name. Prefer that existing graph over composing a new,
            # empty ``code:{project}:{branch}`` key out from under it.
            if branch in (None, "", DEFAULT_BRANCH) and name in self.db.list_graphs():
                self.name = name
            else:
                self.name = compose_graph_name(self.project, self.branch)

        if not hasattr(self, "db"):
            self.db = create_falkordb()
        self.g = self.db.select_graph(self.name)

        # Initialize the backlog as disabled by default
        self.backlog = None

        # create indicies

        # index File path, name and ext fields
        try:
            self.g.create_node_range_index("File", "name", "ext")
        except Exception:
            pass

        # index Function using full-text search
        try:
            self.g.create_node_fulltext_index("Searchable", "name")
        except Exception:
            pass

    @classmethod
    def from_raw_name(cls, raw_name: str) -> "Graph":
        """Construct a :class:`Graph` from an already-composed (or raw) name.

        Used by :meth:`clone` and the migration helper, where the caller
        already knows the final FalkorDB key. Bypasses
        :func:`compose_graph_name`.
        """

        obj = cls.__new__(cls)
        obj.name = raw_name
        parsed = parse_graph_name(raw_name)
        if parsed is None:
            obj.project = raw_name
            obj.branch = DEFAULT_BRANCH
        else:
            obj.project, obj.branch = parsed
        obj.db = create_falkordb()
        obj.g = obj.db.select_graph(raw_name)
        obj.backlog = None
        return obj

    def clone(self, clone: str) -> "Graph":
        """
        Create a copy of the graph under the name clone (raw FalkorDB key).

        Returns:
            a new instance of Graph
        """

        # Make sure key clone isn't already exists
        if self.db.connection.exists(clone):
            raise Exception(f"Can not create clone, key: {clone} already exists.")

        self.g.copy(clone)

        # Wait for the clone to become available
        while not self.db.connection.exists(clone):
            # TODO: add a waiting limit
            time.sleep(1)

        return Graph.from_raw_name(clone)


    def delete(self) -> None:
        """
        Delete graph
        """
        self.g.delete()

    def enable_backlog(self) -> None:
        """
        Enables the backlog by initializing an empty list.
        """

        self.backlog = {'queries': [], 'params': []}
        logging.debug("Backlog enabled")

    def disable_backlog(self) -> None:
        """
        Disables the backlog by setting it to None.
        """

        self.backlog = None
        logging.debug("Backlog disabled")

    def clear_backlog(self) -> tuple[list[str], list[dict]]:
        """
        Clears and returns the backlog of queries and parameters.

        Returns:
            tuple[list[str], list[dict]]: A tuple containing two lists:
            - The first list contains the backlog of queries.
            - The second list contains the backlog of query parameters.
        """

        res = [], []  # Default return value

        if self.backlog:
            params  = self.backlog['params']
            queries = self.backlog['queries']

            # Clear backlog
            self.backlog = {'queries': [], 'params': []}

            logging.debug(f"Backlog queries: {queries}")
            logging.debug(f"Backlog params: {params}")

            # Set return value
            res = queries, params

        logging.debug("Backlog cleared")

        return res


    def _query(self, q: str, params: Optional[dict] = None) -> QueryResult:
        """
        Executes a query on the graph database and logs changes to the backlog if any.

        Args:
            q (str): The query string to execute.
            params (dict): The parameters for the query.

        Returns:
            QueryResult: The result of the query execution.
        """

        result_set = self.g.query(q, params)

        if self.backlog is not None:
            # Check if any change occurred in the query results
            change_detected = any(
                getattr(result_set, attr) > 0
                for attr in [
                    'relationships_deleted', 'nodes_deleted', 'labels_added',
                    'labels_removed', 'nodes_created', 'properties_set',
                    'properties_removed', 'relationships_created'
                ]
            )
            logging.info(f"change_detected: {change_detected}")

            # Append the query and parameters to the backlog if changes occurred
            if change_detected:
                logging.debug(f"logging queries: {q}")
                logging.debug(f"logging params: {params}")
                self.backlog['queries'].append(q)
                self.backlog['params'].append(params)

        return result_set

    def get_sub_graph(self, limit: int) -> dict:

        q = """MATCH (src)
                   OPTIONAL MATCH (src)-[e]->(dest)
                   RETURN src, e, dest
                   LIMIT $limit"""

        sub_graph = {'nodes': [], 'edges': [] }

        result_set = self._query(q, {'limit': limit}).result_set
        for row in result_set:
            src  = row[0]
            e    = row[1]
            dest = row[2]

            sub_graph['nodes'].append(encode_node(src))

            if e is not None:
                sub_graph['edges'].append(encode_edge(e))
                sub_graph['nodes'].append(encode_node(dest))

        return sub_graph


    def get_neighbors(self, node_ids: list[int], rel: Optional[str] = None, lbl: Optional[str] = None) -> dict[str, list[dict]]:
        """
        Fetch the neighbors of a given nodes in the graph based on relationship type and/or label.

        Args:
            node_ids (List[int]): The IDs of the source nodes.
            rel (str, optional): The type of relationship to filter by. Defaults to None.
            lbl (str, optional): The label of the destination node to filter by. Defaults to None.

        Returns:
            dict: A dictionary with lists of 'nodes' and 'edges' for the neighbors.
        """

        # Validate inputs
        if not all(isinstance(node_id, int) for node_id in node_ids):
            raise ValueError("node_ids must be an integer list")

        # Build relationship and label query parts
        rel_query = f":{rel}" if rel else ""
        lbl_query = f":{lbl}" if lbl else ""

        # Parameterized Cypher query to find neighbors
        query = f"""
            MATCH (n)-[e{rel_query}]->(dest{lbl_query})
            WHERE ID(n) IN $node_ids
            RETURN e, dest
        """

        # Initialize the neighbors structure
        neighbors = {'nodes': [], 'edges': []}

        try:
            # Execute the graph query with node_id parameter
            result_set = self._query(query, {'node_ids': node_ids}).result_set

            # Iterate over the result set and process nodes and edges
            for edge, destination_node in result_set:
                neighbors['nodes'].append(encode_node(destination_node))
                neighbors['edges'].append(encode_edge(edge))

            return neighbors

        except Exception as e:
            logging.error(f"Error fetching neighbors for node {node_ids}: {e}")
            return {'nodes': [], 'edges': []}

    def add_entity(self, label: str, name: str, doc: str, path: str, src_start: int, src_end: int, props: dict) -> int:
        """
        Adds a node to the graph database.

        Args:
        """

        q = f"""MERGE (c:{label}:Searchable {{name: $name, path: $path, src_start: $src_start,
                               src_end: $src_end}})
               SET c.doc = $doc
               SET c += $props
               RETURN c"""

        params = {
            'doc': doc,
            'name': name,
            'path': path,
            'src_start': src_start,
            'src_end': src_end,
            'props': props
        }

        res  = self._query(q, params)
        node = res.result_set[0][0]
        return node.id

    def get_class_by_name(self, class_name: str) -> Optional[Node]:
        q = "MATCH (c:Class) WHERE c.name = $name RETURN c LIMIT 1"
        res = self._query(q, {'name': class_name}).result_set

        if len(res) == 0:
            return None

        return res[0][0]

    def get_class(self, class_id: int) -> Optional[Node]:
        q = """MATCH (c:Class)
               WHERE ID(c) = $class_id
               RETURN c"""
        
        res = self._query(q, {'class_id': class_id})

        if len(res.result_set) == 0:
            return None

        return res.result_set[0][0]

    # set functions metadata
    def set_functions_metadata(self, ids: list[int], metadata: list[dict]) -> None:
        assert(len(ids) == len(metadata))

        # TODO: Match (f:Function)
        q = """UNWIND range(0, size($ids)) as i
               WITH $ids[i] AS id, $values[i] AS v
               MATCH (f)
               WHERE ID(f) = id
               SET f += v
               RETURN f"""
        
        params = {'ids': ids, 'values': metadata}

        self._query(q, params)

    # get all functions defined by file
    def get_functions_in_file(self, path: str, name: str, ext: str) -> list[Node]:
        q = """MATCH (f:File {path: $path, name: $name, ext: $ext})
               MATCH (f)-[:DEFINES]->(func:Function)
               RETURN collect(func)"""

        params = {'path': path, 'name': name, 'ext': ext}
        return self._query(q, params).result_set[0][0]

    def get_function_by_name(self, name: str) -> Optional[Node]:
        q = "MATCH (f:Function) WHERE f.name = $name RETURN f LIMIT 1"
        res = self._query(q, {'name': name}).result_set

        if len(res) == 0:
            return None

        return res[0][0]

    def prefix_search(self, prefix: str, limit: int = 10) -> str:
        """
        Search for entities by prefix using a full-text search on the graph.
        The number of results is bounded by ``limit`` (default 10). Each node's
        name and labels are retrieved, and the results are sorted based on their labels.

        Args:
            prefix (str): The prefix string to search for in the graph database.
            limit (int): Maximum number of nodes to return (default 10).

        Returns:
            str: A list of entity names and corresponding labels, sorted by label.
                 If no results are found or an error occurs, an empty list is returned.
        """

        # Append a wildcard '*' to the prefix for full-text search.
        search_prefix = f"{prefix}*"

        # Cypher query to perform full-text search, bounding the result at $limit.
        # The 'CALL db.idx.fulltext.queryNodes' method searches for nodes labeled 'Searchable'
        # that match the given prefix, collects the nodes, and returns the result.
        query = """
            CALL db.idx.fulltext.queryNodes('Searchable', $prefix)
            YIELD node
            WITH node
            RETURN node
            LIMIT $limit
        """

        # Execute the query using the provided graph database connection.
        result_set = self._query(query, {'prefix': search_prefix, 'limit': int(limit)}).result_set

        completions = [encode_node(row[0]) for row in result_set]

        return completions


    def get_function(self, func_id: int) -> Optional[Node]:
        q = """MATCH (f:Function)
               WHERE ID(f) = $func_id
               RETURN f"""
        
        res = self._query(q, {'func_id': func_id})

        if len(res.result_set) == 0:
            return None

        return res.result_set[0][0]

    def function_calls(self, func_id: int) -> list[Node]:
        q = """MATCH (f:Function)
               WHERE ID(f) = $func_id
               MATCH (f)-[:CALLS]->(callee)
               RETURN collect(callee)"""

        res = self._query(q, {'func_id': func_id})

        return res.result_set[0][0]
    
    def function_called_by(self, func_id: int) -> list[Node]:
        q = """MATCH (f:Function)
               WHERE ID(f) = $func_id
               MATCH (caller)-[:CALLS]->(f)
               RETURN collect(caller)"""

        res = self._query(q, {'func_id': func_id})

        return res.result_set[0][0]

    def add_file(self, file: File) -> None:
        """
        Add a file node to the graph database.

        Args:
            file (File): The file.
        """

        q = """MERGE (f:File:Searchable {path: $path, name: $name, ext: $ext})
               RETURN f"""
        params = {'path': str(file.path), 'name': file.path.name, 'ext': file.path.suffix}

        res     = self._query(q, params)
        node    = res.result_set[0][0]
        file.id = node.id

    def delete_files(self, files: list[Path]) -> tuple[str, dict, list[int]]:
        """
        Deletes file(s) from the graph in addition to any other entity
        defined in the file

        a file is defined by its path, name and extension
        files = [{'path':_, 'name': _, 'ext': _}, ...]
        """

        q = """UNWIND $files AS file
               MATCH (f:File {path: file['path'], name: file['name'], ext: file['ext']})
               OPTIONAL MATCH (f)-[:DEFINES*]->(e)
               DELETE f, e
        """

        params = {'files': [{'path': str(file_path), 'name': file_path.name, 'ext' : file_path.suffix} for file_path in files]}
        self._query(q, params)

        return None

    def get_file(self, path: str, name: str, ext: str) -> Optional[Node]:
        """
        Retrieves a File node from the graph database based on its path, name,
        and extension.

        Args:
            path (str): The file path.
            name (str): The file name.
            ext (str): The file extension.

        Returns:
            Optional[Node]: The File node if found, otherwise None.

        Example:
            file = self.get_file('/path/to/file', 'filename', '.py')
        """

        q = """MATCH (f:File {path: $path, name: $name, ext: $ext})
               RETURN f"""
        params = {'path': path, 'name': name, 'ext': ext}

        res = self._query(q, params)
        if len(res.result_set) == 0:
            return None

        return res.result_set[0][0]

    # set file code coverage
    # if file coverage is 100% set every defined function coverage to 100% aswell
    def set_file_coverage(self, path: str, name: str, ext: str, coverage: float) -> None:
        q = """MATCH (f:File {path: $path, name: $name, ext: $ext})
               SET f.coverage_precentage = $coverage
               WITH f
               WHERE $coverage = 1.0
               MATCH (f)-[:DEFINES]->(func:Function)
               SET func.coverage_precentage = 1.0"""

        params = {'path': path, 'name': name, 'ext': ext, 'coverage': coverage}

        self._query(q, params)

    def connect_entities(self, relation: str, src_id: int, dest_id: int, properties: dict = {}) -> None:
        """
        Establish a relationship between src and dest

        Args:
            src_id (int): ID of the source node.
            dest_id (int): ID of the destination node.
        """

        q = f"""MATCH (src), (dest)
                WHERE ID(src) = $src_id AND ID(dest) = $dest_id
                MERGE (src)-[e:{relation}]->(dest)
                SET e += $properties
                RETURN e"""

        params = {'src_id': src_id, 'dest_id': dest_id, "properties": properties}
        self._query(q, params)

    def derive_overrides(self, max_depth: int = 3) -> int:
        """
        Derive ``OVERRIDES`` edges from the existing class hierarchy.

        A method ``m`` on a subclass overrides method ``m2`` on an ancestor
        class when they share a name. Pure graph derivation over existing
        ``EXTENDS`` + ``DEFINES`` edges, so it is language-agnostic. The edge
        carries ``depth`` (inheritance distance) for downstream filtering.

        Args:
            max_depth (int): Maximum inheritance distance to bridge.

        Returns:
            int: Number of OVERRIDES edges after derivation.
        """

        q = f"""MATCH (sub:Class)-[x:EXTENDS*1..{int(max_depth)}]->(sup:Class)
                WHERE ID(sub) <> ID(sup)
                WITH DISTINCT sub, sup, length(x) AS depth
                MATCH (sub)-[:DEFINES]->(m:Function)
                MATCH (sup)-[:DEFINES]->(m2:Function)
                WHERE m.name = m2.name AND ID(m) <> ID(m2)
                MERGE (m)-[e:OVERRIDES]->(m2)
                ON CREATE SET e.depth = depth"""

        try:
            self._query(q)
        except Exception as exc:  # noqa: BLE001 — derivation is best-effort
            logging.warning("derive_overrides failed: %s", exc)
            return 0

        res = self._query("MATCH ()-[e:OVERRIDES]->() RETURN count(e)").result_set
        return int(res[0][0]) if res else 0

    def function_calls_function(self, caller_id: int, callee_id: int, pos: int) -> None:
        """
        Establish a 'CALLS' relationship between two function nodes.

        Args:
            caller_id (int): ID of the caller function node.
            callee_id (int): ID of the callee function node.
            pos (int): line number on which the function call is made.
        """

        q = """MATCH (caller:Function), (callee:Function)
               WHERE ID(caller) = $caller_id AND ID(callee) = $callee_id
               MERGE (caller)-[e:CALLS {pos:$pos}]->(callee)
               RETURN e"""

        params = {'caller_id': caller_id, 'callee_id': callee_id, 'pos': pos}
        self._query(q, params)

    def get_struct_by_name(self, struct_name: str) -> Optional[Node]:
        q = "MATCH (s:Struct) WHERE s.name = $name RETURN s LIMIT 1"
        res = self._query(q, {'name': struct_name}).result_set

        if len(res) == 0:
            return None

        return res[0][0]

    def get_struct(self, struct_id: int) -> Optional[Node]:
        q = """MATCH (s:Struct)
               WHERE ID(s) = $struct_id
               RETURN s"""
        
        res = self._query(q, {'struct_id': struct_id})

        if len(res.result_set) == 0:
            return None

        s = res.result_set[0][0]
        return s

    def rerun_query(self, q: str, params: dict) -> QueryResult:
        """
            Re-run a query to transition the graph from one state to another
        """

        return self._query(q, params)

    def find_paths(self, src: int, dest: int, limit: Optional[int] = None) -> list[Path]:
        """
        Find all paths between the source (src) and destination (dest) nodes.

        Args:
            src (int): The ID of the source node.
            dest (int): The ID of the destination node.
            limit (Optional[int]): When provided, bound the number of paths
                enumerated by the database with a Cypher ``LIMIT``. When ``None``
                (default) all paths are returned (legacy behavior).

        Returns:
            List[Optional[Path]]: A list of paths found between the src and dest nodes.
            Returns an empty list if no paths are found.

        Raises:
            Exception: If the query fails or the graph database returns an error.
        """

        # Define the query to match paths between src and dest nodes.
        q = """MATCH (src), (dest)
               WHERE ID(src) = $src_id AND ID(dest) = $dest_id
               WITH src, dest
               MATCH p = (src)-[:CALLS*]->(dest)
               RETURN p
           """

        params = {'src_id': src, 'dest_id': dest}
        if limit is not None:
            q += "        LIMIT $limit\n"
            params['limit'] = int(limit)

        # Perform the query with the source and destination node IDs.
        result_set = self._query(q, params).result_set

        paths = []

        # Extract paths from the query result set.
        for row in result_set:
            path  = []
            p     = row[0]
            nodes = p.nodes()
            edges = p.edges()

            for n, e in zip(nodes, edges):
                path.append(encode_node(n))
                path.append(encode_edge(e))

            # encode last node on path
            path.append(encode_node(nodes[-1]))
            paths.append(path)

        return paths

    def stats(self) -> dict:
        """
        Retrieve statistics about the graph, including the number of nodes and edges.

        Returns:
            dict: A dictionary containing:
                - 'node_count' (int): The total number of nodes in the graph.
                - 'edge_count' (int): The total number of edges in the graph.
        """

        q = "MATCH (n) RETURN count(n)"
        node_count = self._query(q).result_set[0][0]

        q = "MATCH ()-[e]->() RETURN count(e)"
        edge_count = self._query(q).result_set[0][0]

        # Return the statistics
        return {'node_count': node_count, 'edge_count': edge_count}

    def unreachable_entities(self, lbl: Optional[str], rel: Optional[str]) -> list[dict]:
        lbl = f": {lbl}" if lbl else ""
        rel = f": {rel}" if rel else ""

        q = f""" MATCH (n {lbl})
                 WHERE not ()-[{rel}]->(n)
                 RETURN n
        """

        result_set = self._query(q).result_set

        unreachables = []
        for row in result_set:
            node = row[0]
            unreachables.append(encode_node(node))

        return unreachables


# ---------------------------------------------------------------------------
# Async helpers and read-only async graph wrapper
# ---------------------------------------------------------------------------

def _async_db():
    """Create an async FalkorDB connection using environment config."""
    return create_async_falkordb()


async def async_graph_exists(name: str) -> bool:
    db = _async_db()
    try:
        graphs = await db.list_graphs()
        return name in graphs
    finally:
        await db.aclose()


async def async_get_repos() -> list[dict]:
    """List processed (project, branch) pairs (async version).

    Mirrors :func:`get_repos`; see that function for the return shape.
    """
    db = _async_db()
    try:
        repos = []
        for g in await db.list_graphs():
            parsed = parse_graph_name(g)
            if parsed is None:
                if _is_internal_suffix(g):
                    continue
                repos.append({"project": g, "branch": DEFAULT_BRANCH, "graph": g})
            else:
                project, branch = parsed
                if _is_internal_suffix(branch):
                    continue
                repos.append({"project": project, "branch": branch, "graph": g})
        return repos
    finally:
        await db.aclose()


class AsyncGraphQuery:
    """Read-only async wrapper for endpoint use.

    Uses falkordb.asyncio under the hood.  No index creation or backlog —
    indexes already exist from the sync Graph used during analysis.

    Accepts either a bare project name + branch or a fully composed graph
    name (``code:{project}:{branch}``); see :class:`Graph` for details.
    """

    def __init__(self, name: str, branch: Optional[str] = None) -> None:
        parsed = parse_graph_name(name)
        if parsed is not None:
            self.project, self.branch = parsed
            self.name = name
        else:
            self.project = name
            self.branch = branch or DEFAULT_BRANCH
            # Composition is deferred until ``graph_exists``/first query so
            # we can prefer an existing legacy (pre-T17) bare graph over
            # composing a new, empty ``code:{project}:{branch}`` key; see
            # ``_resolve_name``.
            self.name = name
            self._needs_resolution = branch in (None, "", DEFAULT_BRANCH)
        self.db = _async_db()
        self.g = self.db.select_graph(self.name)

    async def _resolve_name(self) -> None:
        """Resolve a bare project name to its actual FalkorDB graph key.

        Prefers an existing legacy graph (stored under the bare project
        name) over composing a new ``code:{project}:{branch}`` key.
        """
        if not getattr(self, "_needs_resolution", False):
            return
        self._needs_resolution = False
        graphs = await self.db.list_graphs()
        if self.name not in graphs:
            self.name = compose_graph_name(self.project, self.branch)
            self.g = self.db.select_graph(self.name)

    async def graph_exists(self) -> bool:
        """Check if this graph exists, reusing the current connection."""
        await self._resolve_name()
        graphs = await self.db.list_graphs()
        return self.name in graphs

    async def _query(self, q: str, params: Optional[dict] = None):
        return await self.g.query(q, params)

    async def get_sub_graph(self, limit: int) -> dict:
        q = """MATCH (src)
               OPTIONAL MATCH (src)-[e]->(dest)
               RETURN src, e, dest
               LIMIT $limit"""

        sub_graph = {'nodes': [], 'edges': []}
        result_set = (await self._query(q, {'limit': limit})).result_set
        for row in result_set:
            src  = row[0]
            e    = row[1]
            dest = row[2]
            sub_graph['nodes'].append(encode_node(src))
            if e is not None:
                sub_graph['edges'].append(encode_edge(e))
                sub_graph['nodes'].append(encode_node(dest))
        return sub_graph

    async def get_neighbors(self, node_ids: list[int], rel: Optional[str] = None, lbl: Optional[str] = None) -> dict:
        if not all(isinstance(node_id, int) for node_id in node_ids):
            raise ValueError("node_ids must be an integer list")

        rel_query = f":{rel}" if rel else ""
        lbl_query = f":{lbl}" if lbl else ""

        query = f"""
            MATCH (n)-[e{rel_query}]->(dest{lbl_query})
            WHERE ID(n) IN $node_ids
            RETURN e, dest
        """

        neighbors = {'nodes': [], 'edges': []}
        try:
            result_set = (await self._query(query, {'node_ids': node_ids})).result_set
            for edge, destination_node in result_set:
                neighbors['nodes'].append(encode_node(destination_node))
                neighbors['edges'].append(encode_edge(edge))
            return neighbors
        except Exception as e:
            logging.error(f"Error fetching neighbors for node {node_ids}: {e}")
            return {'nodes': [], 'edges': []}

    async def prefix_search(self, prefix: str, limit: int = 10) -> list:
        search_prefix = f"{prefix}*"
        query = """
            CALL db.idx.fulltext.queryNodes('Searchable', $prefix)
            YIELD node
            WITH node
            RETURN node
            LIMIT $limit
        """
        result_set = (await self._query(query, {'prefix': search_prefix, 'limit': int(limit)})).result_set
        return [encode_node(row[0]) for row in result_set]

    async def find_paths(self, src: int, dest: int, limit: Optional[int] = None) -> list:
        q = """MATCH (src), (dest)
               WHERE ID(src) = $src_id AND ID(dest) = $dest_id
               WITH src, dest
               MATCH p = (src)-[:CALLS*]->(dest)
               RETURN p
           """
        params = {'src_id': src, 'dest_id': dest}
        if limit is not None:
            q += "        LIMIT $limit\n"
            params['limit'] = int(limit)
        result_set = (await self._query(q, params)).result_set
        paths = []
        for row in result_set:
            path  = []
            p     = row[0]
            nodes = p.nodes()
            edges = p.edges()
            for n, e in zip(nodes, edges):
                path.append(encode_node(n))
                path.append(encode_edge(e))
            path.append(encode_node(nodes[-1]))
            paths.append(path)
        return paths

    async def stats(self) -> dict:
        q = "MATCH (n) RETURN count(n)"
        node_count = (await self._query(q)).result_set[0][0]

        q = "MATCH ()-[e]->() RETURN count(e)"
        edge_count = (await self._query(q)).result_set[0][0]

        return {'node_count': node_count, 'edge_count': edge_count}

    async def close(self) -> None:
        await self.db.aclose()
