"""Lifespan-owned PostgreSQL checkpointer and cross-thread store."""

from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore
from sqlalchemy.engine import make_url


def psycopg_connection_string(sqlalchemy_url: str) -> str:
    """Translate SQLAlchemy's driver URL into the URI expected by psycopg."""

    url = make_url(sqlalchemy_url)
    if url.get_backend_name() != "postgresql":
        raise ValueError("LangGraph persistence requires PostgreSQL")
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


class PostgresAgentRuntime:
    """Initialize and own LangGraph persistence for the application lifespan."""

    def __init__(self, connection_string: str) -> None:
        self._connection_string = psycopg_connection_string(connection_string)
        self._saver_context: AbstractAsyncContextManager[AsyncPostgresSaver] | None = None
        self._store_context: AbstractAsyncContextManager[AsyncPostgresStore] | None = None
        self.checkpointer: AsyncPostgresSaver | None = None
        self.store: AsyncPostgresStore | None = None

    async def start(self) -> None:
        if self.checkpointer is not None:
            return
        saver_context = AsyncPostgresSaver.from_conn_string(self._connection_string)
        self.checkpointer = await saver_context.__aenter__()
        self._saver_context = saver_context
        try:
            await self.checkpointer.setup()
            store_context = AsyncPostgresStore.from_conn_string(self._connection_string)
            self.store = await store_context.__aenter__()
            self._store_context = store_context
            await self.store.setup()
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        try:
            if self._store_context is not None:
                await self._store_context.__aexit__(None, None, None)
        finally:
            if self._saver_context is not None:
                await self._saver_context.__aexit__(None, None, None)
            self.store = None
            self.checkpointer = None
            self._store_context = None
            self._saver_context = None


@asynccontextmanager
async def postgres_checkpointer(connection_string: str) -> AsyncGenerator[AsyncPostgresSaver]:
    """Compatibility helper that initializes checkpoint tables before yielding."""

    runtime = PostgresAgentRuntime(connection_string)
    await runtime.start()
    if runtime.checkpointer is None:
        raise RuntimeError("checkpointer failed to initialize")
    try:
        yield runtime.checkpointer
    finally:
        await runtime.close()
