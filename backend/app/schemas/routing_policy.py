from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.routing_policy import RoutingPolicySource, RoutingPolicyTarget
from app.schemas.tunnel import TunnelRead


class RoutingPolicyUpdate(BaseModel):
    target: RoutingPolicyTarget
    target_tunnel_id: int | None = None
    direct_interface: str | None = Field(default=None, max_length=32)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_target(self) -> "RoutingPolicyUpdate":
        if self.target == RoutingPolicyTarget.tunnel and self.target_tunnel_id is None:
            raise ValueError("target_tunnel_id is required for tunnel target")
        if self.target == RoutingPolicyTarget.direct and not self.direct_interface:
            raise ValueError("direct_interface is required for direct target")
        return self


class RoutingPolicyRead(BaseModel):
    id: int
    source: RoutingPolicySource
    target: RoutingPolicyTarget
    target_tunnel_id: int | None
    direct_interface: str | None
    enabled: bool
    priority: int
    applied_at: datetime | None
    target_tunnel: TunnelRead | None = None
    resolved_interface: str | None = None

    model_config = {"from_attributes": True}


class RoutingPolicySnapshot(BaseModel):
    policies: list[RoutingPolicyRead]
    available_tunnels: list[TunnelRead]


class RoutingPolicyPreview(BaseModel):
    source: RoutingPolicySource
    resolved_interface: str | None
    commands: list[str]
    warnings: list[str] = []


class RoutingPolicyApplyResult(BaseModel):
    status: str
    message: str
    applied_users: int
    reapplied_tunnel_ids: list[int]
    warnings: list[str] = []
