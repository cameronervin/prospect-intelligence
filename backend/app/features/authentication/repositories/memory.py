"""In-memory authentication repository for isolated tests."""

from ..domain.users import User


class InMemoryUserRepository:
    def __init__(self, users: tuple[User, ...] = ()) -> None:
        self._users = {user.email.casefold(): user for user in users}

    def by_email(self, email: str) -> User | None:
        return self._users.get(email.strip().casefold())

    def upsert(self, user: User) -> None:
        self._users[user.email.casefold()] = user
