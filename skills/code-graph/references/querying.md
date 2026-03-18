# Code Graph — Querying Reference

## JSON Structures

### Node

```json
{
  "id": 42,
  "labels": ["Function"],
  "properties": {
    "name": "analyze_sources",
    "path": "api/project.py",
    "src_start": 79,
    "src_end": 94,
    "doc": "..."
  }
}
```

### Edge

```json
{
  "id": 10,
  "relation": "CALLS",
  "src_node": 42,
  "dest_node": 55,
  "properties": {
    "pos": 83
  }
}
```

### Neighbors response

```json
{
  "repo": "code-graph",
  "nodes": [ /* node objects */ ],
  "edges": [ /* edge objects */ ]
}
```

### Paths response

```json
{
  "repo": "code-graph",
  "paths": [
    [ node, edge, node, edge, node ]
  ]
}
```

Each path is an alternating array of node and edge objects.

## Common Query Patterns

### "What does function X call?"

```bash
cgraph search X
# note the id from results, e.g. 42
cgraph neighbors 42 --rel CALLS
```

### "Who calls function X?"

The graph stores directed edges `(caller)-[:CALLS]->(callee)`. To find callers, search for the function, then look for *incoming* CALLS edges. Since `neighbors` follows outgoing edges, use `find_paths` or search for likely callers and check their CALLS neighbors.

### "What does class Y define?"

```bash
cgraph search Y
# note the id, e.g. 55
cgraph neighbors 55 --rel DEFINES
```

### "Trace path from function A to function B"

```bash
cgraph search A
# note id, e.g. 10
cgraph search B
# note id, e.g. 99
cgraph paths 10 99
```

### "What are the stats for this repo?"

```bash
cgraph info --repo my-project
```

## Search Workflow

1. **Search** — find entities by name prefix → get node IDs
2. **Neighbors** — explore connections from those nodes
3. **Paths** — trace call chains between specific nodes
4. **Read source** — use `path`, `src_start`, `src_end` from node properties to read the actual code
