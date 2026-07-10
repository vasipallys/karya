"""Shared test hygiene.

TestClient-based tests run the API lifespan, which installs a durable
AsyncSqliteSaver checkpointer process-wide and clears the cached estimation
graph. Left in place, that saver's connection/thread leaks into later tests that
run the graph directly (e.g. the offline mock-LLM tests), raising
"threads can only be started once". Resetting after every test keeps the graph
on the default in-memory saver.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_estimation_graph():
    yield
    try:
        from backend.graph.build import get_estimation_graph
        from backend.graph.checkpoint import set_checkpointer

        set_checkpointer(None)
        get_estimation_graph.cache_clear()
    except Exception:
        pass
