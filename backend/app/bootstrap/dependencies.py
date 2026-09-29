"""Concrete application dependency construction."""

from dataclasses import dataclass
from typing import Protocol

from app.platform.config.settings import Settings
from app.platform.database.session import Database


class DatabaseLifecycle(Protocol):
    """Database behavior required by application lifecycle and readiness."""

    async def ping(self) -> bool: ...

    async def close(self) -> None: ...


@dataclass(slots=True)
class Container:
    """Application dependencies and lifecycle state."""

    settings: Settings
    database: DatabaseLifecycle
    started: bool = False

    async def is_ready(self) -> bool:
        if not self.started:
            return False
        try:
            return await self.database.ping()
        except Exception:
            return False

    async def close(self) -> None:
        self.started = False
        await self.database.close()


def build_container(settings: Settings) -> Container:
    """Build production dependencies without performing network I/O."""

    return Container(settings=settings, database=Database.from_settings(settings))
