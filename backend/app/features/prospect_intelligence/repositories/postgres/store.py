"""Shared PostgreSQL engine lifecycle for prospect repositories."""

from sqlalchemy import Engine, create_engine

from app.platform.config.settings import Settings


class PostgresProspectStore:
    """Own one thread-safe sync engine shared by the feature repositories."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @classmethod
    def from_settings(cls, settings: Settings) -> "PostgresProspectStore":
        return cls(
            create_engine(
                settings.database_url.get_secret_value(),
                pool_pre_ping=True,
                connect_args={
                    "connect_timeout": settings.database_connect_timeout_seconds,
                    "options": (f"-c statement_timeout={settings.database_statement_timeout_ms}"),
                },
            )
        )

    def close(self) -> None:
        self.engine.dispose()
