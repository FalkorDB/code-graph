# Sample fixture project for the MCP test suite

This directory is consumed by `tests/mcp/conftest.py::indexed_fixture`. Every
MCP tool ticket from T4 onward asserts against the assertions declared in
`expected.yaml`.

## Canonical Python call graph

```
entrypoint() -> service() -> {UserRepo,OrderRepo}.repo() -> db()
```

Plus a small class hierarchy:

```
BaseRepo
  ├── UserRepo
  └── OrderRepo
```

## Why three languages? (deferred)

The original T3 spec called for one Java + one C# file so multilspy's
second-pass code paths would be exercised. In practice both analyzers
demand a real Maven / .NET project layout at the **root** of the indexed
tree, which would make this fixture awkward to co-host with the Python
sample. The multilingual coverage is therefore deferred to a follow-up
ticket (likely T16, which already pulls in additional languages).

T4-T8 only need Python, which this fixture covers in full.

## Stability contract

If you change this fixture, you must also update `expected.yaml`. Tests
read counts and named symbols directly from that file so the assertion
contract stays in lock-step.
