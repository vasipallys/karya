"""Process-wide checkpointer registry so the app can swap in a durable saver.

The API lifespan installs an AsyncSqliteSaver when the optional
langgraph-checkpoint-sqlite dependency is available; tests and bare imports
fall back to an in-memory saver.
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

_checkpointer: BaseCheckpointSaver | None = None


def set_checkpointer(checkpointer: BaseCheckpointSaver | None) -> None:
    global _checkpointer
    _checkpointer = checkpointer


def get_checkpointer() -> BaseCheckpointSaver:
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = MemorySaver()
    return _checkpointer
