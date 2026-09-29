"""Small injectable fakes for platform tests."""


class FakeDatabase:
    def __init__(self, *, healthy: bool = True, raises: bool = False) -> None:
        self.healthy = healthy
        self.raises = raises
        self.ping_calls = 0
        self.closed = False

    async def ping(self) -> bool:
        self.ping_calls += 1
        if self.raises:
            raise RuntimeError("synthetic database failure")
        return self.healthy

    async def close(self) -> None:
        self.closed = True
