"""Framework-independent identifier value objects."""

from typing import NewType
from uuid import UUID

RunId = NewType("RunId", UUID)
UserId = NewType("UserId", UUID)
