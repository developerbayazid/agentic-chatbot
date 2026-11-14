"""Request and response schemas.

Every request model forbids unknown fields. That keeps identity out of reach of
the client: ``owner_id`` is derived from the verified token, and a payload that
tries to supply one is rejected rather than silently ignored (which would hide a
caller's mistake).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TokenRequest(StrictModel):
    api_key: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
