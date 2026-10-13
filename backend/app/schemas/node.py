from pydantic import BaseModel, Field
from typing import Literal

from app.models.node import NodeRole
from app.schemas.tunnel import AmneziaWGApplyResult, TunnelRead


class NodeBase(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    role: NodeRole
    host: str = Field(min_length=2, max_length=255)
    ssh_user: str | None = Field(default=None, max_length=80)
    ssh_port: int = Field(default=22, ge=1, le=65535)


class NodeCreate(NodeBase):
    uplink_type: Literal["none", "wireguard", "amneziawg"] = "none"


class NodeUpdate(NodeBase):
    pass


class NodeRead(NodeBase):
    id: int

    model_config = {"from_attributes": True}


class NodeCreateResult(BaseModel):
    node: NodeRead
    created_tunnel: TunnelRead | None = None
    apply_result: AmneziaWGApplyResult | None = None
    apply_error: str | None = None
