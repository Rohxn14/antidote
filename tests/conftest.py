# tests/conftest.py
"""Every test gets a fresh graph named `antidote_test`, separate from the demo
graph. It is deleted before and after each test, together with any preview or
what-if copies made from it."""
import os

import pytest

# Tests never call a real model: with an empty key (which .env loading does not
# override), a call that slipped past a stub fails instead of spending tokens.
os.environ["LLM_API_KEY"] = ""

from app.db import drop_graph, get_db  # noqa: E402
from app.schema import ensure_schema  # noqa: E402

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
