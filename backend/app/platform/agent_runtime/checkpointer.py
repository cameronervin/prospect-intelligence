"""Injectable PostgreSQL checkpointer construction.

This module does not call ``setup``. A future agent feature must explicitly own
checkpoint schema creation and migration policy.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


@asynccontextmanager
async def postgres_checkpointer(connection_string: str) -> AsyncGenerator[AsyncPostgresSaver]:
    """Yield a connected saver without creating checkpoint tables."""

    async with AsyncPostgresSaver.from_conn_string(connection_string) as saver:
        yield saver
