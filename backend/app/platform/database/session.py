"""Asynchronous SQLAlchemy database lifecycle."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.platform.config.settings import Settings


class Database:
    """Own the engine and session factory for one application process."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)

    @classmethod
    def from_settings(cls, settings: Settings) -> "Database":
        connect_args = {
            "connect_timeout": settings.database_connect_timeout_seconds,
            "options": f"-c statement_timeout={settings.database_statement_timeout_ms}",
        }
        engine = create_async_engine(
            settings.database_url.get_secret_value(),
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        return cls(engine)

    async def ping(self) -> bool:
        async with self.engine.connect() as connection:
            result = await connection.execute(text("SELECT 1"))
            return result.scalar_one() == 1

    async def close(self) -> None:
        await self.engine.dispose()
