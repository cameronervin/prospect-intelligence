"""Strict authentication edge schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=1, max_length=256)


class SessionUserResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str
    email: str
    display_name: str
    tenant_id: str
    rep_id: str
    roles: list[Literal["sales_rep"]]


class SessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: SessionUserResponse


class TokenResponse(SessionResponse):
    expires_at: datetime
    absolute_expires_at: datetime
    access_token: str
    token_type: Literal["bearer"] = "bearer"
