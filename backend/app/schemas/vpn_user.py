from datetime import datetime

from pydantic import BaseModel, Field


class VpnUserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    enabled: bool = True


class VpnUserUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    enabled: bool = True


class VpnUserRead(BaseModel):
    id: int
    name: str
    client_ip: str
    public_key: str
    enabled: bool
    applied_at: datetime | None
    latest_handshake: int | None = None
    latest_handshake_at: datetime | None = None

    model_config = {"from_attributes": True}


class VpnUserApplyResult(BaseModel):
    status: str
    message: str
    applied_users: int


class VpnUserConfig(BaseModel):
    user_id: int
    name: str
    filename: str
    config: str


class VpnBypassDomainsUpdate(BaseModel):
    domains: list[str] = Field(min_length=1, max_length=200)
