# tests/conftest.py
"""Every test gets a fresh graph named `antidote_test`, separate from the demo
graph. It is deleted before and after each test, together with any preview or
what-if copies made from it."""
import pytest

from app.db import drop_graph, get_db
from app.schema import ensure_schema

TEST_GRAPH = "antidote_test"


def _cleanup() -> None:
    for name in get_db().list_graphs():
        if name == TEST_GRAPH or name.startswith(TEST_GRAPH + "_"):
            drop_graph(name)


@pytest.fixture
def g():
    _cleanup()
    graph = get_db().select_graph(TEST_GRAPH)
    ensure_schema(graph)
    yield graph
    _cleanup()
